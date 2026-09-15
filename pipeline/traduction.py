"""Traduction anglaise des articles de l'édition.

Chaque article publié reçoit un champ « en » (titre, chapeau, corps) que l'application affiche
quand la langue choisie est l'anglais. Les articles partent par lots, car les quotas gratuits
comptent les requêtes et non les mots, et d'abord vers les modèles légers de la cascade. Une
traduction qui perd un nombre de l'original est refusée : l'article reste en français seulement.

Usage :
    python traduction.py                    # traduit la dernière édition publiée dans docs/
    python traduction.py --date 2026-09-14  # une édition précise
    python traduction.py --factice          # sans clé : faux modèle, pour tester la mécanique
"""

from __future__ import annotations

import argparse
import json
import logging
import re

import communs as c
import publie
from llm import AucunFournisseur, Cascade
from redaction import ILLISIBLES, extraire_json

log = logging.getLogger("traduction")

MOTS_PAR_LOT = 900  # un gros lot échoue plus souvent (JSON illisible) et fait tout recommencer
JETONS_LOT = 12000
INTERTITRE_FR = "## Ce que disent les sources"
INTERTITRE_EN = "## What the sources say"

CONSIGNES = """Tu traduis en anglais des articles d'un quotidien francophone.

- Traduis fidèlement : n'ajoute, ne retire et ne résume rien.
- Anglais courant et neutre, en phrases courtes comme l'original.
- Garde tous les nombres, en chiffres quand l'original les écrit en chiffres. Heures sur 24 heures (14:30).
- Garde les noms propres. Traduis le nom d'une institution quand un usage anglais existe.
- Garde les paragraphes : une ligne vide entre deux paragraphes, comme dans l'original.
- La ligne « ## Ce que disent les sources » devient « ## What the sources say ».

SORTIE
JSON strict, sans balises de code : {"articles": [{"id", "titre", "chapeau", "corps"}]},
un objet par article reçu, avec le même « id »."""


def lots(articles: list[dict], mots_max: int = MOTS_PAR_LOT) -> list[list[dict]]:
    """Articles regroupés par lots d'environ mots_max mots ; un article trop long forme son propre lot."""
    resultat, courant, total = [], [], 0
    for article in articles:
        mots = c.compter_mots(f"{article['titre']} {article['chapeau']} {article['corps']}")
        if courant and total + mots > mots_max:
            resultat.append(courant)
            courant, total = [], 0
        courant.append(article)
        total += mots
    if courant:
        resultat.append(courant)
    return resultat


def message(lot: list[dict]) -> str:
    donnees = [{"id": a["id"], "titre": a["titre"], "chapeau": a["chapeau"], "corps": a["corps"]} for a in lot]
    return "ARTICLES À TRADUIRE\n" + json.dumps({"articles": donnees}, ensure_ascii=False, indent=1)


# Séparateur de milliers (30 000, 30,000) : retiré pour comparer les nombres des deux langues.
_MILLIERS = re.compile("(?<=\\d)[ ,  ](?=\\d{3}(?!\\d))")


def nombres(texte: str) -> set[str]:
    return set(re.findall(r"\d+", _MILLIERS.sub("", texte)))


def normaliser(traduction: dict) -> dict:
    corps = str(traduction.get("corps") or "").strip()
    corps = re.sub(r"(?mi)^[ \t]*#*[ \t]*what (?:the )?sources say[ \t]*:?[ \t]*$", INTERTITRE_EN, corps)
    paragraphes = [bloc.strip() for bloc in re.split(r"\n\s*\n", corps) if bloc.strip()]
    return {
        "titre": " ".join(str(traduction.get("titre") or "").split()).rstrip("."),
        "chapeau": " ".join(str(traduction.get("chapeau") or "").split()),
        "corps": "\n\n".join(p if p.startswith("## ") else " ".join(p.split()) for p in paragraphes),
    }


def erreurs(original: dict, traduction: dict) -> list[str]:
    liste = [f"champ « {champ} » vide" for champ in ("titre", "chapeau", "corps")
             if str(original.get(champ) or "").strip() and not str(traduction.get(champ) or "").strip()]
    source = f"{original['titre']} {original['chapeau']} {original['corps']}"
    cible = f"{traduction.get('titre', '')} {traduction.get('chapeau', '')} {traduction.get('corps', '')}"
    perdus = sorted(nombres(source) - nombres(cible))
    if perdus:
        liste.append("nombres perdus : " + ", ".join(perdus[:5]))
    if (INTERTITRE_FR in original["corps"]) != (INTERTITRE_EN in str(traduction.get("corps") or "")):
        liste.append("intertitre « Ce que disent les sources » perdu ou ajouté")
    return liste


def traduire_lot(lot: list[dict], cascade: Cascade, preferes: tuple[str, ...]) -> list[dict]:
    """Traduit un lot sur place (champ « en »). Renvoie les articles restés sans traduction."""
    reponse = cascade.completer(CONSIGNES, message(lot), max_tokens=JETONS_LOT, preferes=preferes)
    try:
        brut = extraire_json(reponse.texte)
    except ValueError:
        log.info("Réponse illisible pour un lot de %d article(s)", len(lot))
        ILLISIBLES.mkdir(exist_ok=True)  # réponse gardée pour comprendre après coup
        (ILLISIBLES / f"traduction-{lot[0]['id']}.txt").write_text(reponse.texte, encoding="utf-8")
        return list(lot)
    recus = {str(t.get("id")): t for t in brut.get("articles") or [] if isinstance(t, dict)}
    restes = []
    for article in lot:
        if article["id"] in recus:
            traduction = normaliser(recus[article["id"]])
            probleme = erreurs(article, traduction)
            if not probleme:
                article["en"] = traduction
                continue
            log.info("Traduction refusée (%s) : %s", article["titre"][:60], "; ".join(probleme))
        restes.append(article)
    return restes


def traduire(articles: list[dict], cascade: Cascade) -> int:
    """Ajoute « en » aux articles qui n'en ont pas encore. Renvoie le nombre d'articles traduits."""
    preferes = tuple(c.charger_yaml("llm.yaml").get("traduction_d_abord") or ())
    a_faire = [a for a in articles if not a.get("en") and a.get("titre")]
    for lot in lots(a_faire):
        if not cascade.disponible():
            break
        try:
            restes = traduire_lot(lot, cascade, preferes)
        except AucunFournisseur:
            continue  # aucun modèle n'a répondu pour ce lot ; le suivant aura peut-être plus de chance
        if len(lot) > 1:  # second essai, article par article
            for article in restes:
                if not cascade.disponible():
                    break
                try:
                    traduire_lot([article], cascade, preferes)
                except AucunFournisseur:
                    pass
    faits = sum(1 for a in a_faire if a.get("en"))
    log.info("Traduction anglaise : %d article(s) sur %d", faits, len(a_faire))
    return faits


def traduire_edition(jour: str | None, factice: bool = False) -> bool:
    """Traduit une édition déjà publiée dans docs/ et la republie sous une nouvelle version."""
    jour = jour or (c.lire_json(c.DOCS / "index.json", {}) or {}).get("derniere")
    chemin = c.EDITIONS / f"{jour}.json"
    edition = c.lire_json(chemin, {}) if jour else {}
    if not edition or not edition.get("articles"):
        log.error("Aucune édition à traduire (%s)", chemin)
        return False
    if traduire(edition["articles"], Cascade.depuis_config(factice=factice)):
        edition["genere_a"] = c.iso(c.maintenant())  # nouvelle version : l'application la retélécharge
        c.ecrire_json(chemin, edition)
        publie.mettre_a_jour_index()
    avec = sum(1 for a in edition["articles"] if a.get("en"))
    log.info("Édition du %s : %d article(s) sur %d lisibles en anglais", jour, avec, len(edition["articles"]))
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Ajoute la traduction anglaise à une édition publiée.")
    parser.add_argument("--date", help="date de l'édition AAAA-MM-JJ (par défaut : la dernière publiée)")
    parser.add_argument("--factice", action="store_true", help="faux modèle, pour tester sans clé")
    parser.add_argument("-v", "--verbeux", action="store_true")
    args = parser.parse_args()
    c.demarrer(args.verbeux)
    if not traduire_edition(args.date, args.factice):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
