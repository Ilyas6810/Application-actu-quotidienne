"""Contrôle automatique d'un article avant publication (étape 5).

Les cinq vérifications du cahier des charges :
  1. aucune suite de 12 mots identique à une source (copie) ;
  2. au moins deux liens sources, pris dans le contexte fourni au modèle ;
  3. aucun mot interdit par la charte (config/mots_interdits.txt) ;
  4. longueur conforme au format ;
  5. titre sans point d'exclamation, sans question, sans superlatif.
Une sixième, ajoutée :
  6. chaque nombre de l'article figure dans les sources. Un chiffre inventé est
     l'erreur la plus grave d'un modèle gratuit, et la seule qu'une règle
     mécanique attrape à coup sûr. Désactivable (controle.verifier_chiffres).

Un article qui échoue repart pour une seconde génération avec la liste des
erreurs ; au second échec, il est écarté (voir redaction.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache

import communs as c


@dataclass
class Verdict:
    erreurs: list[str] = field(default_factory=list)
    avertissements: list[str] = field(default_factory=list)
    format: str | None = None

    @property
    def ok(self) -> bool:
        return not self.erreurs


# --- Typographie : corrigée avant contrôle plutôt que refusée -------------------------

def corriger_typographie(texte: str) -> str:
    """Tirets cadratins d'incise -> virgules, gras Markdown retiré."""
    texte = re.sub(r"(?m)^[ \t]*[—–][ \t]*", "", texte)  # tiret en début de ligne
    texte = re.sub(r"[ \t]*—[ \t]*", ", ", texte)  # cadratin d'incise
    texte = re.sub(r"[ \t]+–[ \t]+", ", ", texte)  # demi-cadratin employé comme tiret
    texte = re.sub(r",[ \t]*([,.;:])", r"\1", texte)
    return texte.replace("**", "").replace("__", "")


# --- 1. Copie ---------------------------------------------------------------------------

_CITATION = re.compile(r"«[^»]{0,600}»|“[^”]{0,600}”|\"[^\"\n]{0,600}\"")


def retirer_citations_courtes(texte: str, mots_max: int) -> str:
    """Une citation officielle courte, entre guillemets, est autorisée par la charte."""
    return _CITATION.sub(lambda m: " " if c.compter_mots(m.group(0)) < mots_max else m.group(0), texte)


def _ngrammes(mots: list[str], n: int) -> set[tuple[str, ...]]:
    return {tuple(mots[i:i + n]) for i in range(len(mots) - n + 1)}


def passages_copies(texte_article: str, textes_sources: list[str], n: int, mots_citation: int) -> list[str]:
    mots = c.mots_normalises(retirer_citations_courtes(texte_article, mots_citation))
    reference: set[tuple[str, ...]] = set()
    for texte in textes_sources:
        reference |= _ngrammes(c.mots_normalises(texte), n)
    copies, i = [], 0
    while i <= len(mots) - n:
        if tuple(mots[i:i + n]) in reference:
            j = i + n
            while j < len(mots) and tuple(mots[j - n + 1:j + 1]) in reference:
                j += 1
            copies.append(" ".join(mots[i:j]))
            i = j
        else:
            i += 1
    return copies


# --- 3. Mots interdits -----------------------------------------------------------------

@lru_cache(maxsize=1)
def motifs_interdits() -> tuple[tuple[re.Pattern, ...], tuple[re.Pattern, ...]]:
    interdits, exceptions = [], []
    for ligne in (c.CONFIG / "mots_interdits.txt").read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#"):
            continue
        cible = exceptions if ligne.startswith("!") else interdits
        expression = ligne.lstrip("!").strip()
        if not re.search(r"\w", expression):  # ponctuation seule, comme le tiret cadratin
            cible.append(re.compile(re.escape(expression)))
        else:
            cible.append(re.compile(rf"(?<!\w)(?:{expression})(?!\w)", re.IGNORECASE))
    return tuple(interdits), tuple(exceptions)


def mots_interdits_trouves(texte: str) -> list[str]:
    interdits, exceptions = motifs_interdits()
    for exception in exceptions:
        texte = exception.sub(" ", texte)
    return [m.group(0) for m in (motif.search(texte) for motif in interdits) if m]


# --- 4. Longueur -----------------------------------------------------------------------

def format_selon_longueur(mots: int, demande: str, formats: dict, tolerance: float) -> str | None:
    """Format conforme à la longueur. Un article trop court pour son format est
    reclassé dans un format plus court ; jamais promu en article de fond."""
    def convient(nom: str) -> bool:
        f = formats[nom]
        return f["min"] * (1 - tolerance) <= mots <= f["max"] * (1 + tolerance)

    if demande in formats and convient(demande):
        return demande
    for nom in ("breve", "standard"):
        if nom != demande and nom in formats and convient(nom):
            return nom
    # Entre deux formats (plus long qu'une brève, plus court qu'un article) : le plus proche des
    # deux, sans dépasser le format demandé ni promouvoir en article de fond.
    ordre = [nom for nom in ("breve", "standard", "fond") if nom in formats]
    for court, long_ in zip(ordre, ordre[1:]):
        haut, bas = formats[court]["max"] * (1 + tolerance), formats[long_]["min"] * (1 - tolerance)
        if haut < mots < bas:
            if long_ == "fond" or (demande in ordre and ordre.index(long_) > ordre.index(demande)):
                return court
            return court if mots - haut <= bas - mots else long_
    return None


# --- 5. Titre --------------------------------------------------------------------------

_SUPERLATIF = re.compile(r"\b(?:le|la|les|l['’])\s*(?:plus|moins)\b|\bmeilleure?s?\b|\bpires?\b|\b\w+issimes?\b",
                         re.IGNORECASE)


def erreurs_titre(titre: str) -> list[str]:
    erreurs = []
    if "!" in titre:
        erreurs.append("le titre contient un point d'exclamation")
    if "?" in titre:
        erreurs.append("le titre contient une question")
    superlatif = _SUPERLATIF.search(titre)
    if superlatif:
        erreurs.append(f"le titre contient un superlatif : « {superlatif.group(0)} »")
    return erreurs


# --- 6. Nombres ------------------------------------------------------------------------

# Nombre isolé : 12, 3,5, 1.200, 12 000 (espace, insécable ou fine). Les ordinaux (1er, 20e) sont exclus.
ESPACES = " " + chr(0xA0) + chr(0x202F)  # espace, insécable, fine insécable
_NOMBRE = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:[" + ESPACES + r"]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)*)(?!\s?(?:er|re|ère|ème|eme|e)\b)(?![\w])"
)
_TOUJOURS_ADMIS = {24.0, 48.0, 72.0}  # « dans les 24 heures »


def interpretations(jeton: str) -> set[float]:
    """Valeurs possibles d'un nombre écrit à la française ou à l'anglaise."""
    s = re.sub("[" + ESPACES + "]", "", jeton)
    candidats = set()
    if "," in s and "." in s:
        candidats.add(s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", ""))
    elif s.count(",") > 1 or s.count(".") > 1:
        candidats.add(s.replace(",", "").replace(".", ""))
    elif "," in s or "." in s:
        entier, fraction = re.split(r"[.,]", s)
        candidats.add(f"{entier}.{fraction}")  # décimale
        if len(fraction) == 3:
            candidats.add(entier + fraction)  # séparateur de milliers
    else:
        candidats.add(s)
    valeurs = set()
    for candidat in candidats:
        try:
            valeurs.add(round(float(candidat), 6))
        except ValueError:
            pass
    return valeurs


def nombres_non_sources(texte_article: str, textes_sources: list[str], dates: list[datetime]) -> list[str]:
    reference = set(_TOUJOURS_ADMIS)
    for texte in textes_sources:
        for m in _NOMBRE.finditer(texte):
            reference |= interpretations(m.group(1))
    for d in dates:
        reference |= {float(d.day), float(d.month), float(d.year), float(d.hour), float(d.minute)}

    def connu(valeur: float) -> bool:
        return any(round(valeur * echelle, 6) in reference for echelle in (1, 1e3, 1e6, 1e9, 1e-3, 1e-6, 1e-9))

    absents = []
    for m in _NOMBRE.finditer(texte_article):
        valeurs = interpretations(m.group(1))
        if not valeurs or all(v <= 10 and v == int(v) for v in valeurs):
            continue  # petits entiers : souvent écrits en lettres dans les sources
        if not any(connu(v) for v in valeurs):
            absents.append(m.group(1))
    return sorted(set(absents))


# --- Vérification complète ---------------------------------------------------------------

def verifier(article: dict, contexte: dict, format_demande: str, formats: dict | None = None,
             champs_requis: tuple[str, ...] = ("titre", "chapeau", "corps")) -> Verdict:
    """article : titre, chapeau, corps, sources (liste de {nom, url}), liens_inventes.
    contexte : textes (sources montrées au modèle), textes_chiffres (idem + épisode
    précédent), dates, officiel_competent."""
    reglages = c.parametres()["controle"]
    edition = c.parametres()["edition"]
    formats = formats or edition["formats"]
    verdict = Verdict()
    for champ in champs_requis:
        if not str(article.get(champ, "")).strip():
            verdict.erreurs.append(f"le champ « {champ} » est vide")
    if verdict.erreurs:
        return verdict
    titre, chapeau, corps = article["titre"], article.get("chapeau", ""), article.get("corps", "")
    texte = f"{titre}\n{chapeau}\n{corps}"

    copies = passages_copies(texte, contexte["textes"], reglages["ngramme_copie"], reglages["citation_mots_max"])
    if copies:
        verdict.erreurs.append(f"passage recopié mot pour mot d'une source, à reformuler : « {copies[0][:150]} »")

    if article.get("liens_inventes"):
        verdict.erreurs.append("liens absents de la liste des sources : " + ", ".join(article["liens_inventes"][:3]))
    minimum = 1 if contexte.get("officiel_competent") else 2
    if len({s["url"] for s in article.get("sources", [])}) < minimum:
        verdict.erreurs.append(f"moins de {minimum} liens sources")

    interdits = mots_interdits_trouves(texte)
    if interdits:
        verdict.erreurs.append("mots interdits par la charte : " + ", ".join(sorted({m.lower() for m in interdits})))

    mots = c.compter_mots(f"{chapeau} {corps}")
    verdict.format = format_selon_longueur(mots, format_demande, formats, edition["tolerance_longueur"])
    if verdict.format is None:
        cible = formats[format_demande]
        sens = "trop court" if mots < cible["min"] else "trop long"
        verdict.erreurs.append(f"article {sens} : {mots} mots pour le format {format_demande} "
                               f"(de {cible['min']} à {cible['max']} mots attendus)")
    elif verdict.format != format_demande:
        verdict.avertissements.append(f"reclassé en {verdict.format} ({mots} mots)")

    verdict.erreurs += erreurs_titre(titre)
    mots_titre = c.compter_mots(titre)
    if not 6 <= mots_titre <= 15:
        verdict.avertissements.append(f"titre de {mots_titre} mots (8 à 12 demandés)")

    if reglages.get("verifier_chiffres", True):
        absents = nombres_non_sources(texte, contexte.get("textes_chiffres", contexte["textes"]), contexte["dates"])
        if absents:
            verdict.erreurs.append("nombres absents des sources, à retirer ou corriger : " + ", ".join(absents[:8]))
    return verdict
