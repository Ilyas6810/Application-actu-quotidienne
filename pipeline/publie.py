"""Étape 5 (fin) : publication de l'édition.

Écrit docs/editions/AAAA-MM-JJ.json au format de la section 7 du cahier des charges,
met à jour docs/index.json et, sur demande, fait le commit et le push Git.
GitHub Pages sert ensuite ces fichiers en HTTPS.

Usage :
    python publie.py            # publie etat/brouillons.json comme édition du jour
    python publie.py --commit   # et pousse sur GitHub
"""

from __future__ import annotations

import argparse
import logging
import subprocess
from collections import Counter

import communs as c

log = logging.getLogger("publie")

CHAMPS_PUBLICS = ("id", "rubrique", "format", "titre", "chapeau", "corps", "niveau_de_confiance",
                  "sources", "premiere_parution", "suite_de", "mots", "modele", "en")


def _ordre(article: dict) -> tuple:
    rubrique = article["rubrique"]
    return (c.RUBRIQUES.index(rubrique) if rubrique in c.RUBRIQUES else 99, -article.get("score", 0))


def attribuer_identifiants(articles: list[dict], jour: str) -> None:
    """Identifiants du type 2026-09-11-monde-004, numérotés par rubrique et par score."""
    compteurs: Counter = Counter()
    for article in sorted(articles, key=_ordre):
        compteurs[article["rubrique"]] += 1
        article["id"] = f"{jour}-{article['rubrique']}-{compteurs[article['rubrique']]:03d}"


def construire_edition(articles: list[dict], jour: str, genere_a: str) -> dict:
    attribuer_identifiants(articles, jour)
    une = sorted((a for a in articles if a.get("a_la_une")), key=lambda a: -a.get("score", 0))
    return {
        "date": jour,
        "genere_a": genere_a,
        "rubriques": [{"id": r, "nom": c.NOMS_RUBRIQUES[r]} for r in ("une",) + c.RUBRIQUES],
        "articles": [{champ: a.get(champ) for champ in CHAMPS_PUBLICS} for a in sorted(articles, key=_ordre)],
        "une": [a["id"] for a in une],
    }


def preparer_docs() -> None:
    """Fichiers fixes du site : pas de Jekyll, pas d'indexation par les moteurs."""
    c.EDITIONS.mkdir(parents=True, exist_ok=True)
    (c.DOCS / ".nojekyll").touch()
    robots = c.DOCS / "robots.txt"
    if not robots.exists():
        robots.write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")
    if not (c.DOCS / "alertes.json").exists():
        c.ecrire_json(c.DOCS / "alertes.json", {"maj": None, "alertes": []})


def mettre_a_jour_index() -> dict:
    editions = []
    for chemin in sorted(c.EDITIONS.glob("*.json"), reverse=True):
        edition = c.lire_json(chemin, {}) or {}
        if not edition.get("articles"):
            continue
        titres = {a["id"]: a["titre"] for a in edition["articles"]}
        editions.append({
            "date": edition["date"],
            "genere_a": edition.get("genere_a"),
            "articles": len(edition["articles"]),
            "une": [titres[i] for i in edition.get("une", [])[:3] if i in titres],
            "octets": chemin.stat().st_size,
        })
    index = {"maj": c.iso(c.maintenant()), "derniere": editions[0]["date"] if editions else None,
             "editions": editions}
    c.ecrire_json(c.DOCS / "index.json", index)
    return index


def git(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *arguments], cwd=c.RACINE, capture_output=True, text=True, encoding="utf-8")


def commit_git(message: str, chemins: list[str]) -> bool:
    git("add", *chemins)
    if git("diff", "--cached", "--quiet").returncode == 0:
        log.info("Rien de nouveau à publier")
        return False
    resultat = git("commit", "-m", message)
    if resultat.returncode != 0:
        log.error("Commit impossible : %s", (resultat.stderr or resultat.stdout).strip()[:300])
        return False
    for _ in range(3):
        resultat = git("push")
        if resultat.returncode == 0:
            log.info("Poussé sur GitHub : %s", message)
            return True
        log.warning("Push refusé (%s) : synchronisation puis nouvel essai", resultat.stderr.strip()[:200])
        git("pull", "--rebase", "--autostash")
    log.error("Push impossible après trois essais")
    return False


def publier(articles: list[dict], jour: str, commit: bool = False) -> dict:
    preparer_docs()
    edition = construire_edition(articles, jour, c.iso(c.maintenant()))
    chemin = c.EDITIONS / f"{jour}.json"
    c.ecrire_json(chemin, edition)
    mettre_a_jour_index()
    log.info("Édition du %s : %d articles, %d à la une, %.0f Ko -> %s", jour, len(edition["articles"]),
             len(edition["une"]), chemin.stat().st_size / 1024, chemin)
    if commit:
        commit_git(f"Édition du {jour} ({len(edition['articles'])} articles)", ["docs"])
    return edition


def main() -> None:
    parser = argparse.ArgumentParser(description="Publie etat/brouillons.json comme édition du jour.")
    parser.add_argument("--date", help="date de l'édition AAAA-MM-JJ (par défaut : aujourd'hui, heure locale)")
    parser.add_argument("--commit", action="store_true", help="commit et push de docs/")
    parser.add_argument("-v", "--verbeux", action="store_true")
    args = parser.parse_args()
    c.demarrer(args.verbeux)
    brouillons = c.lire_json(c.ETAT / "brouillons.json", {}) or {}
    articles = brouillons.get("articles", [])
    if not articles:
        log.error("Aucun brouillon : lancer d'abord python redaction.py")
        return
    publier(articles, args.date or c.date_locale().isoformat(), commit=args.commit)


if __name__ == "__main__":
    main()
