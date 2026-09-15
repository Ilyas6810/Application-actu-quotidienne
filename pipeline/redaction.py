"""Étape 4 : sélection des sujets et rédaction des articles.

Un appel au modèle par article. Le contexte ne contient que les résumés des sources
du groupe, avec leur nom et leur date : le modèle ne cherche rien lui-même. La charte
éditoriale du cahier des charges sert de prompt système, mot pour mot (CHARTE).
Chaque article passe les contrôles de controle.py ; en cas d'échec il repart une fois
avec la liste des erreurs, puis il est écarté.

Usage (vérification de l'étape 4 : dix articles lisibles) :
    python redaction.py --nombre 10          # écrit etat/brouillons.json et etat/brouillons.md
    python redaction.py --nombre 3 --factice # sans clé : faux modèle, pour tester la mécanique
"""

from __future__ import annotations

import argparse
import difflib
import json
import logging
import re
from datetime import date, datetime, timedelta

import communs as c
import controle
from llm import AucunFournisseur, Cascade, Reponse

log = logging.getLogger("redaction")

BROUILLONS = c.ETAT / "brouillons.json"
ILLISIBLES = c.ETAT / "reponses_illisibles"

# Charte éditoriale du cahier des charges (section 6), copiée telle quelle.
CHARTE = """Tu es rédacteur dans un quotidien de référence. Tu écris un article
à partir des seules sources fournies ci-dessous. Tu n'ajoutes aucun
fait qui ne s'y trouve pas.

STRUCTURE
1. Un titre informatif de 8 à 12 mots. Il dit ce qui s'est passé,
   pas ce que le lecteur doit ressentir.
2. Un chapeau de deux phrases qui répond à quoi, qui, où, quand.
3. Le corps, du plus important au moins important.
4. Si les sources divergent, une section "Ce que disent les sources"
   qui expose les versions en les attribuant nommément.
5. Si des éléments manquent, une dernière phrase qui le dit.

STYLE
- Phrases courtes. Une idée par phrase.
- Voix active, sujet identifié. "Le gouvernement espagnol a annoncé",
  jamais "il a été annoncé".
- Vocabulaire courant. Tu expliques tout terme technique en cinq mots.
- Aucun adjectif d'appréciation : dramatique, historique, choquant,
  massif, sans précédent, spectaculaire.
- Aucun adverbe de renforcement : véritablement, particulièrement,
  extrêmement.
- Pas de tirets cadratins.
- Les chiffres avec leur source et leur date.

NEUTRALITÉ
- Tu attribues chaque affirmation contestée à celui qui la formule.
- Tu donnes le même traitement aux parties d'un conflit.
- Tu n'emploies pas de vocabulaire connoté sans le mettre au compte
  d'un acteur.
- Tu ne conclus pas sur le sens ou la portée d'un événement.
- Tu n'écris jamais "on peut se demander si", "l'avenir dira",
  "une chose est sûre".

INTERDITS ABSOLUS
- Reproduire une phrase des sources. Tu reformules tout.
- Inventer une déclaration, un chiffre, un nom.
- Écrire un article si les sources ne concordent pas sur le fait
  central. Dans ce cas, réponds exactement : ARTICLE_IMPOSSIBLE

SORTIE
JSON strict, sans balises de code, avec les clés :
titre, chapeau, corps, rubrique, format, niveau_de_confiance
(confirmé | partiel | contesté), sources (liste de {nom, url})."""

# Plafond de jetons de sortie par format, raisonnement des modèles compris.
# Plafonds de jetons de sortie. Chez Gemini, le raisonnement compte dedans : trop bas, la réponse est tronquée.
JETONS = {"breve": 4000, "standard": 6000, "fond": 8000, "alerte": 2500}

LANGUES = {
    "fr": "français", "en": "anglais", "es": "espagnol", "de": "allemand", "it": "italien", "pt": "portugais",
    "nl": "néerlandais", "ja": "japonais", "ar": "arabe", "ru": "russe", "uk": "ukrainien", "zh": "chinois",
    "tr": "turc", "pl": "polonais", "id": "indonésien", "ko": "coréen", "he": "hébreu", "fa": "persan",
}

_MOTS_OUTILS = {
    "dans", "pour", "avec", "sans", "sous", "entre", "apres", "avant", "depuis", "selon", "contre", "vers",
    "chez", "cette", "leur", "leurs", "elle", "elles", "nous", "vous", "tout", "tous", "toute", "toutes",
    "plus", "moins", "tres", "mais", "donc", "comme", "aussi", "alors", "encore", "deja", "etre", "sont",
    "etait", "sera", "avait", "fait", "font", "dont", "quand", "lors", "part", "pres", "face", "suite",
}


def mots_significatifs(texte: str) -> set[str]:
    return {m for m in c.mots_normalises(texte) if len(m) >= 4 and m not in _MOTS_OUTILS}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


# --- Épisodes précédents (champ suite_de) ------------------------------------------------

class Historique:
    """Articles des éditions précédentes, pour relier un sujet à son épisode précédent."""

    def __init__(self, avant: date, jours: int):
        self.articles: list[dict] = []
        self.par_url: dict[str, dict] = {}
        for chemin in sorted(c.EDITIONS.glob("*.json"), reverse=True):  # plus récente d'abord
            try:
                jour = date.fromisoformat(chemin.stem)
            except ValueError:
                continue
            if not avant - timedelta(days=jours) <= jour < avant:
                continue
            edition = c.lire_json(chemin, {}) or {}
            for article in edition.get("articles", []):
                fiche = {
                    "id": article["id"], "titre": article["titre"], "chapeau": article.get("chapeau", ""),
                    "date": edition.get("date", chemin.stem), "genere_a": edition.get("genere_a", ""),
                    "mots": mots_significatifs(article["titre"]),
                }
                self.articles.append(fiche)
                for source in article.get("sources", []):
                    self.par_url.setdefault(c.url_canonique(source.get("url", "")), fiche)

    def episode(self, sujet: dict, pool: dict) -> dict | None:
        items = [pool[i] for i in sujet["items"] if i in pool]
        precedents = [self.par_url[it["url"]] for it in items if it["url"] in self.par_url]
        if not precedents:  # au-delà de 72 heures, les URL ont quitté le pool : on compare les titres
            mots = mots_significatifs(sujet["titre"])
            precedents = [a for a in self.articles if jaccard(mots, a["mots"]) >= 0.5]
        if not precedents:
            return None
        dernier = max(precedents, key=lambda a: a["genere_a"])
        nouveau = any(it.get("niveau") == 1 and it["date"] > dernier["genere_a"] for it in items)
        return {**dernier, "nouveau": nouveau}


# --- Sélection -----------------------------------------------------------------------------

def selectionner(clusters: list[dict], pool: dict, historique: Historique) -> list[dict]:
    """Sujets du jour : quotas par rubrique (plafonds souples), À la une, formats."""
    reglages = c.parametres()["edition"]
    minimum = c.parametres()["notation"]["score_minimal"]
    candidats = []
    for cluster in clusters:  # déjà triés par score décroissant
        if not cluster["publiable"] or cluster["score"] < minimum:
            continue
        episode = historique.episode(cluster, pool)
        if episode and not episode["nouveau"]:
            continue  # déjà traité, rien de neuf depuis
        candidats.append({**cluster, "episode": episode, "suite_de": episode["id"] if episode else None})
    retenus = []
    for rubrique, conf in reglages["rubriques"].items():
        retenus += [s for s in candidats if s["rubrique"] == rubrique][: conf["quota"]]
    retenus.sort(key=lambda s: s["score"], reverse=True)
    une = {s["id"] for s in retenus[: reglages["une"]]}
    fonds = [s["id"] for s in retenus if s["id"] in une and s["independants"] >= reglages["sources_min_fond"]]
    fonds = set(fonds[: reglages["fonds_max"]])
    standards = 0
    for sujet in retenus:
        sujet["a_la_une"] = sujet["id"] in une
        if sujet["id"] in fonds:
            sujet["format"] = "fond"
        elif sujet["independants"] >= reglages["sources_min_standard"] and standards < reglages["standards_max"]:
            sujet["format"] = "standard"
            standards += 1
        else:
            sujet["format"] = "breve"
    if len(fonds) < reglages["fonds_min"]:
        log.info("Seulement %d sujet(s) assez sourcé(s) pour un article de fond", len(fonds))
    log.info("%d sujets retenus sur %d candidats publiables", len(retenus), len(candidats))
    return retenus


def ordre_de_redaction(retenus: list[dict]) -> list[dict]:
    """À la une d'abord (fonds en tête), puis par priorité de rubrique et par score :
    si le temps ou les quotas manquent, l'essentiel est déjà écrit."""
    priorites = {r: conf["priorite"] for r, conf in c.parametres()["edition"]["rubriques"].items()}
    return sorted(retenus, key=lambda s: (not s.get("a_la_une"), s.get("format") != "fond",
                                          priorites.get(s["rubrique"], 9), -s["score"]))


# --- Contexte et consignes -------------------------------------------------------------------

def items_contexte(sujet: dict, pool: dict, maximum: int) -> list[dict]:
    """Une source par groupe de presse d'abord (la plus récente), puis le reste."""
    items = [pool[i] for i in sujet["items"] if i in pool]
    niveau1 = sorted((it for it in items if it.get("niveau") == 1), key=lambda it: it["date"], reverse=True)
    autres = sorted((it for it in items if it.get("niveau") != 1), key=lambda it: it.get("radar_domaines", 0),
                    reverse=True)
    choix, groupes, titres = [], set(), set()

    def ajouter(it: dict) -> None:
        cle = " ".join(c.mots_normalises(it["titre"]))
        if cle not in titres and len(choix) < maximum:
            choix.append(it)
            groupes.add(it["groupe"])
            titres.add(cle)

    for it in niveau1:
        if it["groupe"] not in groupes:
            ajouter(it)
    for it in niveau1 + autres:
        if not any(it is deja for deja in choix):
            ajouter(it)
    return sorted(choix, key=lambda it: it["date"])


def dates_reference(items: list[dict], date_ed: date) -> list[datetime]:
    """Dates des sources (UTC et heure locale) : leurs jours et heures sont des nombres admis."""
    dates = []
    for it in items:
        moment = c.lire_date(it["date"])
        if moment:
            dates += [moment, moment.astimezone(c.fuseau())]
    jour = datetime(date_ed.year, date_ed.month, date_ed.day)
    return dates + [jour, jour - timedelta(days=1)]


def consignes(sujet: dict, items: list[dict], format_: str, date_ed: date,
              corrections: list[str] | None = None, formats: dict | None = None) -> str:
    reglages = c.parametres()["edition"]
    f = (formats or reglages["formats"])[format_]
    lignes = [
        "Rédige en français l'article tiré des sources ci-dessous.",
        "",
        f"Rubrique : {sujet['rubrique']}",
        f"Format : {format_}, de {f['min']} à {f['max']} mots pour le chapeau et le corps réunis.",
        f"Date de l'édition : {c.date_longue(date_ed)}. Les heures des sources sont données à l'heure de l'édition (UTC+4).",
    ]
    if format_ == "alerte":
        lignes.append("Une alerte tient dans le titre et le chapeau : laisse « corps » vide.")
    episode = sujet.get("episode")
    if episode:
        lignes += ["", f"Épisode précédent, publié le {episode['date']} : « {episode['titre']} ». {episode['chapeau']}",
                   "Concentre-toi sur les faits nouveaux. Rappelle l'épisode précédent en une phrase au plus."]
    lignes += ["", f"SOURCES ({len(items)}), de la plus ancienne à la plus récente :"]
    for numero, it in enumerate(items, 1):
        quand = (c.lire_date(it["date"]) or c.maintenant()).astimezone(c.fuseau())
        origine = it["source"] + (f" ({it['pays']})" if it.get("pays") else "")
        langue = LANGUES.get(it.get("langue", ""), it.get("langue", "langue inconnue"))
        lignes += ["", f"[{numero}] {origine}, {quand:%d/%m/%Y} à {quand:%H:%M}, en {langue}",
                   f"Titre : {it['titre']}"]
        if it.get("resume"):
            libelle = "Résumé (rédigé par le portail Wikipédia, qui cite cet article)" if it.get("resume_de") else "Résumé"
            lignes.append(f"{libelle} : {c.tronquer(it['resume'], reglages['longueur_resume_contexte'])}")
        lignes.append(f"Lien : {it['url']}")
    lignes += [
        "",
        "CONSIGNES DE FORME",
        "- Dans « corps », sépare les paragraphes par une ligne vide.",
        "- Si les sources divergent, la section commence par une ligne qui contient seulement : Ce que disent les sources",
        "- Dans « sources », ne mets que des liens de la liste ci-dessus, recopiés à l'identique.",
        "- La date et l'heure d'une source accompagnent ses chiffres, pas chacune de ses informations.",
        f"- « rubrique » vaut « {sujet['rubrique']} » et « format » vaut « {format_} ».",
    ]
    if corrections:
        lignes += ["", "TA VERSION PRÉCÉDENTE A ÉTÉ REFUSÉE. Corrige ces points :"] + [f"- {e}" for e in corrections]
    return "\n".join(lignes)


# --- Lecture de la réponse ---------------------------------------------------------------------

def extraire_json(texte: str) -> dict:
    """Objet JSON de la réponse, même entouré de balises de code ou de texte."""
    texte = re.sub(r"(?s)<think>.*?</think>", "", texte).strip()
    texte = re.sub(r"^```(?:json)?\s*|\s*```$", "", texte, flags=re.IGNORECASE).strip()
    candidats = [texte]
    debut, fin = texte.find("{"), texte.rfind("}")
    if 0 <= debut < fin:
        candidats.append(texte[debut:fin + 1])
    for candidat in candidats:
        try:
            valeur = json.loads(candidat, strict=False)  # strict=False : retours à la ligne dans les chaînes
        except json.JSONDecodeError:
            continue
        if isinstance(valeur, dict):
            return valeur
    raise ValueError("pas d'objet JSON exploitable")


_INTERTITRE = re.compile(r"(?mi)^[ \t]*(ce que disent les sources)[ \t]*:?[ \t]*$")


def _champ(brut: dict, cle: str) -> str:
    valeur = brut.get(cle, "")
    if isinstance(valeur, list):
        valeur = "\n\n".join(str(v) for v in valeur)
    return str(valeur or "").strip()


def _lien_proche(lien: str, connus) -> str | None:
    """Lien de la liste que le modèle a recopié avec une petite faute (un mot traduit, une lettre)."""
    domaine = c.domaine(lien)
    meilleur, score = None, 0.0
    for connu in connus:
        if c.domaine(connu) == domaine:
            ratio = difflib.SequenceMatcher(None, lien, connu).ratio()
            if ratio > score:
                meilleur, score = connu, ratio
    return meilleur if score >= 0.9 else None


def normaliser(brut: dict, items: list[dict]) -> dict:
    titre = controle.corriger_typographie(_champ(brut, "titre")).strip().rstrip(".").strip("«»\"' ")
    chapeau = " ".join(controle.corriger_typographie(_champ(brut, "chapeau")).split())
    corps = controle.corriger_typographie(_champ(brut, "corps"))
    corps = re.sub(r"(?m)^[ \t]*#{1,6}[ \t]*", "", corps)
    corps = _INTERTITRE.sub("\n\n## Ce que disent les sources\n\n", corps)
    paragraphes = []
    for bloc in re.split(r"\n\s*\n", corps):
        bloc = bloc.strip()
        if bloc:
            paragraphes.append(bloc if bloc.startswith("## ") else " ".join(bloc.split()))
    par_url = {c.url_canonique(it["url"]): it for it in items}
    par_nom = {it["source"].lower(): c.url_canonique(it["url"]) for it in items}
    citees, inventes = [], []
    for source in brut.get("sources") or []:
        if isinstance(source, dict):
            lien, nom = str(source.get("url") or ""), str(source.get("nom") or "")
        else:
            lien, nom = (str(source), "") if str(source).startswith("http") else ("", str(source))
        canonique = c.url_canonique(lien) if lien else par_nom.get(nom.lower().strip(), "")
        if canonique and canonique not in par_url:
            canonique = _lien_proche(canonique, par_url) or canonique
        if canonique in par_url:
            if canonique not in citees:
                citees.append(canonique)
        elif lien.strip():
            inventes.append(lien.strip())
    # En pied d'article : toutes les sources données au modèle, une par titre de presse,
    # celles qu'il cite en premier.
    sources, noms = [], set()
    for canonique in citees + [u for u in par_url if u not in citees]:
        it = par_url[canonique]
        if it["source"] not in noms:
            noms.add(it["source"])
            sources.append({"nom": it["source"], "url": it["url"]})
    return {
        "titre": titre, "chapeau": chapeau, "corps": "\n\n".join(paragraphes), "sources": sources[:8],
        "liens_inventes": inventes,
        "niveau_llm": c.sans_accents(str(brut.get("niveau_de_confiance", ""))).lower(),
    }


def niveau_de_confiance(sujet: dict, niveau_llm: str) -> str:
    """Confirmé : trois sources indépendantes ou une source officielle sur son domaine.
    Partiel : deux sources. Contesté : le modèle a relevé une divergence."""
    if niveau_llm.startswith("contest"):
        return "conteste"
    if sujet["independants"] >= 3 or sujet.get("officiel_competent"):
        return "confirme"
    return "partiel"


def assembler(article: dict, sujet: dict, verdict: controle.Verdict, reponse: Reponse) -> dict:
    return {
        "rubrique": sujet["rubrique"],
        "format": verdict.format,
        "titre": article["titre"],
        "chapeau": article["chapeau"],
        "corps": article["corps"],
        "niveau_de_confiance": niveau_de_confiance(sujet, article["niveau_llm"]),
        "sources": article["sources"],
        "premiere_parution": sujet["premiere_parution"],
        "suite_de": sujet.get("suite_de"),
        "mots": c.compter_mots(f"{article['chapeau']} {article['corps']}"),
        "modele": reponse.modele,
        # Champs internes, retirés à la publication :
        "a_la_une": sujet.get("a_la_une", False),
        "score": sujet["score"],
        "cluster": sujet["id"],
        "avertissements": verdict.avertissements,
    }


# --- Rédaction ---------------------------------------------------------------------------------

def rediger_article(sujet: dict, pool: dict, cascade: Cascade, date_ed: date) -> tuple[dict | None, str]:
    """Rédige, contrôle, recommence une fois. Renvoie (article, raison du rejet)."""
    reglages = c.parametres()["edition"]
    items = items_contexte(sujet, pool, reglages["sources_max_contexte"])
    if not items:
        return None, "sources introuvables dans le pool"
    textes = [f"{it['titre']}\n{it.get('resume', '')}" for it in items]
    episode = sujet.get("episode")
    contexte = {
        "textes": textes,
        "textes_chiffres": textes + ([f"{episode['titre']}\n{episode['chapeau']}"] if episode else []),
        "dates": dates_reference(items, date_ed),
        "officiel_competent": sujet.get("officiel_competent", False),
    }
    format_ = sujet.get("format", "breve")
    corrections, raison = None, ""
    for tentative in (1, 2):
        reponse = cascade.completer(CHARTE, consignes(sujet, items, format_, date_ed, corrections),
                                    max_tokens=JETONS[format_])
        if "ARTICLE_IMPOSSIBLE" in reponse.texte[:300]:
            return None, "sources discordantes sur le fait central (ARTICLE_IMPOSSIBLE)"
        try:
            brut = extraire_json(reponse.texte)
        except ValueError as e:
            raison = f"réponse illisible ({e})"
            # Réponse gardée pour comprendre après coup ce que le modèle a renvoyé
            ILLISIBLES.mkdir(exist_ok=True)
            nom_fichier = re.sub(r"[^\w-]", "_", str(sujet["id"]))
            (ILLISIBLES / f"{nom_fichier}-{tentative}.txt").write_text(reponse.texte, encoding="utf-8")
            corrections = ["La réponse doit être un unique objet JSON valide, sans texte autour ni balises de code."]
            continue
        article = normaliser(brut, items)
        verdict = controle.verifier(article, contexte, format_)
        if verdict.ok:
            return assembler(article, sujet, verdict, reponse), ""
        raison = "; ".join(verdict.erreurs)
        corrections = verdict.erreurs
        log.info("Tentative %d refusée (%s) : %s", tentative, sujet["titre"][:60], raison[:200])
    return None, raison


def rediger_serie(sujets: list[dict], pool: dict, cascade: Cascade, date_ed: date,
                  limite: datetime | None = None) -> tuple[list[dict], list[dict]]:
    articles, rejets = [], []
    for numero, sujet in enumerate(sujets, 1):
        restants = sujets[numero - 1:]
        if limite and c.maintenant() >= limite:
            log.warning("Heure limite atteinte : %d sujet(s) non traité(s)", len(restants))
            rejets += [{"titre": s["titre"], "rubrique": s["rubrique"], "raison": "heure limite atteinte"} for s in restants]
            break
        try:
            article, raison = rediger_article(sujet, pool, cascade, date_ed)
        except AucunFournisseur:
            if cascade.disponible():
                # Échec sur ce sujet seulement (surcharge, réponse tronquée) : on passe au suivant.
                rejets.append({"titre": sujet["titre"], "rubrique": sujet["rubrique"],
                               "raison": "aucun modèle n'a répondu pour ce sujet"})
                log.info("[%d/%d] écarté : %s (aucun modèle n'a répondu)", numero, len(sujets), sujet["titre"][:70])
                continue
            log.error("Plus aucun modèle disponible : %d sujet(s) non traité(s)", len(restants))
            rejets += [{"titre": s["titre"], "rubrique": s["rubrique"], "raison": "quotas des modèles épuisés"} for s in restants]
            break
        if article:
            articles.append(article)
            log.info("[%d/%d] %s, %s : %s", numero, len(sujets), article["rubrique"], article["format"], article["titre"])
        else:
            rejets.append({"titre": sujet["titre"], "rubrique": sujet["rubrique"], "raison": raison})
            log.info("[%d/%d] écarté : %s (%s)", numero, len(sujets), sujet["titre"][:70], raison[:150])
    return articles, rejets


def ecrire_brouillons(articles: list[dict], rejets: list[dict]) -> None:
    c.ecrire_json(BROUILLONS, {"genere_a": c.iso(c.maintenant()), "articles": articles, "rejets": rejets})
    lignes = [f"# Brouillons du {c.date_longue(c.date_locale())}", ""]
    for a in articles:
        lignes += [
            f"## {a['titre']}", "",
            f"*{c.NOMS_RUBRIQUES.get(a['rubrique'], a['rubrique'])} · {a['format']} · {a['mots']} mots · "
            f"{a['niveau_de_confiance']} · {a['modele']}*", "",
            f"**{a['chapeau']}**", "", a["corps"], "",
            "Sources : " + ", ".join(f"[{s['nom']}]({s['url']})" for s in a["sources"]), "",
        ]
        if a.get("avertissements"):
            lignes += ["> " + " ; ".join(a["avertissements"]), ""]
        lignes += ["---", ""]
    if rejets:
        lignes += ["## Sujets écartés", ""] + [f"- {r['titre']} : {r['raison']}" for r in rejets]
    (c.ETAT / "brouillons.md").write_text("\n".join(lignes), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Rédige les premiers articles du jour (vérification de l'étape 4).")
    parser.add_argument("--nombre", type=int, default=10, help="nombre d'articles à rédiger")
    parser.add_argument("--factice", action="store_true", help="faux modèle, pour tester sans clé")
    parser.add_argument("-v", "--verbeux", action="store_true")
    args = parser.parse_args()
    c.demarrer(args.verbeux)
    import cluster  # importé ici : numpy et scikit-learn ne servent qu'à ce moment
    clusters = cluster.charger()
    if not clusters:
        log.error("Aucun groupe : lancer d'abord python collecte.py puis python cluster.py")
        return
    pool = c.lire_pool()
    date_ed = c.date_locale()
    historique = Historique(date_ed, c.parametres()["edition"]["jours_suivi"])
    sujets = ordre_de_redaction(selectionner(clusters, pool, historique))[: args.nombre]
    cascade = Cascade.depuis_config(factice=args.factice)
    articles, rejets = rediger_serie(sujets, pool, cascade, date_ed)
    ecrire_brouillons(articles, rejets)
    log.info("%d article(s) rédigé(s), %d écarté(s) : voir etat/brouillons.md", len(articles), len(rejets))


if __name__ == "__main__":
    main()
