"""Étape 3 : regroupement des items par événement, puis notation.

Similarité entre deux items, mélange de deux mesures :
  - TF-IDF + cosinus (scikit-learn), comme le prévoit le cahier des charges :
    noms propres, chiffres et vocabulaire communs dans une même langue ;
  - vecteurs multilingues calculés sur la machine (fastembed, gratuit, sans API) :
    ils rapprochent un article du Monde et un article de la BBC sur le même fait,
    ce que TF-IDF ne sait pas faire d'une langue à l'autre.
Regroupement hiérarchique à lien moyen, coupé au seuil configuré.

Chaque groupe (« cluster ») reçoit ensuite :
  - son nombre de sources indépendantes de niveau 1 : même groupe de presse,
    même agence reprise ou citation mutuelle = une seule source ;
  - sa rubrique ;
  - son score = fiabilité × diffusion × fraîcheur × diversité géographique.

Usage :
    python cluster.py                  # écrit etat/clusters.json et etat/rapport_clusters.md
    python cluster.py --seuil 0.5      # essai d'un autre seuil
    python cluster.py --methode tfidf  # sans vecteurs multilingues

Vérification de l'étape 3 : dans le rapport, les articles sur un même événement sont
ensemble et deux événements distincts ne sont pas mélangés.
"""

from __future__ import annotations

import argparse
import logging
import math
import re
from collections import Counter, defaultdict
from datetime import datetime

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from sklearn.feature_extraction.text import TfidfVectorizer

import communs as c

log = logging.getLogger("cluster")

RAPPORT = c.ETAT / "rapport_clusters.md"
MAX_ITEMS = 8000  # au-delà, la matrice de similarité devient lourde : on garde les plus récents

_MOTS_VIDES = """
le la les un une des du de au aux et ou mais donc ni car que qu qui quoi dont ce cet cette ces se sa son ses leur
leurs lui elle ils elles on nous vous je tu il en ne pas plus moins tres tout tous toute toutes par pour sur sous
dans avec sans entre vers chez apres avant depuis pendant contre selon comme ainsi aussi alors encore deja etre ete
est sont etait etaient sera seront ont avait avaient aura auront fait faire dit dire peut peuvent doit doivent faut
cela ca ceci celui celle ceux celles meme memes autre autres quand comment pourquoi si non oui lors
the an and or but if then than that this these those there their they them he she it its his her we you me my our
your of in on at to for from by with without about into over after before under between during against among via as
is are was were be been being has have had do does did will would can could should may might must not no yes so such
more most less very just also only up down out new said says say
el los las una unos unas pero del al por para con sin sobre desde hasta es son fue ser ha han este esta estos estas
ese esa su sus lo le les mas muy ya tambien segun tras
der die das den dem des ein eine einer eines einem einen und oder aber dass wie im am an auf aus bei mit nach von vor
zu zum zur fur uber unter ist sind wird werden hat haben nicht auch noch schon mehr sich sie er es wir ihr ich du
il lo gli di della dei delle degli alla nel nella tra fra sono era essere hanno anche loro
os um uma do da dos das em no na nos nas foi tem nao seu sua ao
het een van op aan met voor uit naar door over zijn wordt worden heeft hebben niet ook nog er zich
"""
MOTS_VIDES = sorted(set(_MOTS_VIDES.split()))

# Lexiques de classement : minuscules, sans accents, termes séparés par des virgules.
# Servent quand les flux ne donnent pas d'indice de rubrique, et pour distinguer
# Géopolitique de Monde.
LEXIQUES = {
    "sport": """football, footballeur, match, matchs, ligue des champions, champions league, premier league,
        ligue 1, coupe du monde, world cup, championnat, championship, tennis, rugby, basket, basketball, nba,
        cyclisme, cycling, tour de france, jeux olympiques, olympic, olympics, paralympiques, mondial,
        entraineur, coach, joueur, joueuse, player, players, grand chelem, grand slam, formule 1, formula one,
        f1, roland-garros, wimbledon, psg, marathon, athletisme, athletics, handball, judo, natation, swimming,
        golf, boxe, boxing, medaille, medal, buts""",
    "culture": """film, films, cinema, festival, musique, music, album, chanteur, chanteuse, singer, concert,
        concerts, exposition, exhibition, musee, museum, livre, livres, book, roman, novel, ecrivain, ecrivaine,
        writer, author, theatre, serie, netflix, oscar, oscars, cesar, goncourt, artiste, artistes, artist,
        danse, opera, patrimoine, heritage, realisateur, realisatrice, acteur, actrice, actor, actress,
        box-office""",
    "sante": """sante, health, hopital, hopitaux, hospital, hospitals, maladie, maladies, disease, virus,
        epidemie, epidemic, pandemie, pandemic, vaccin, vaccins, vaccine, vaccines, cancer, medicament,
        medicaments, medecin, medecins, doctors, patients, oms, covid, grippe, flu, mpox, cholera, dengue,
        ebola, soins, traitement, treatment, essai clinique, clinical trial, obesite, obesity, diabete,
        diabetes, alzheimer, sida, hiv, vih""",
    "sciences": """scientifique, scientifiques, scientists, chercheurs, researchers, etude, study, espace,
        space, nasa, esa, fusee, rocket, satellite, satellites, planete, planet, telescope, astronome,
        astronomes, astronomers, climat, climate, rechauffement, warming, fossile, fossiles, fossil, espece,
        especes, species, biodiversite, biodiversity, physique, physics, archeologie, archeologues, archaeology,
        archaeologists, genome, adn, dna, lune, moon, asteroide, asteroid""",
    "tech": """intelligence artificielle, artificial intelligence, ia, openai, chatgpt, anthropic, google,
        apple, microsoft, meta, amazon, nvidia, puce, puces, chips, semi-conducteurs, semiconducteurs,
        semiconductors, logiciel, logiciels, software, cyberattaque, cyberattack, piratage, hackers, smartphone,
        iphone, algorithme, algorithms, startup, start-up, robot, robots, quantique, quantum, reseaux sociaux,
        social media, tiktok, musk, tesla, spacex, data center, datacenter""",
    "economie": """economie, economy, economic, economique, inflation, croissance, growth, pib, gdp, bourse,
        bourses, stocks, stock market, marches financiers, markets, taux d'interet, interest rate,
        interest rates, banque centrale, central bank, bce, ecb, entreprise, entreprises, company, companies,
        emploi, emplois, jobs, chomage, unemployment, dette, debt, budget, impots, impot, taxes, tax, tariffs,
        droits de douane, commerce, trade, petrole, oil, salaires, wages, faillite, bankruptcy, fusion, merger,
        acquisition, benefice, benefices, profit, profits, chiffre d'affaires, revenue, investissement,
        investissements, investment, actionnaires, shareholders, recession, pouvoir d'achat""",
    "geopolitique": """guerre, war, armee, army, militaire, militaires, military, missile, missiles, frappe,
        frappes, airstrike, airstrikes, bombardement, bombardements, bombing, drone, drones, otan, nato,
        sanctions, diplomatie, diplomatique, diplomatic, diplomate, diplomats, ambassadeur, ambassador, sommet,
        summit, cessez-le-feu, ceasefire, cease-fire, treve, truce, negociations de paix, peace talks, invasion,
        annexion, annexation, frontiere, border, pentagone, pentagon, kremlin, hamas, hezbollah, houthis,
        taliban, conseil de securite, security council, nucleaire, nuclear, traite, treaty, rebelles, rebels,
        junte, junta, coup d'etat, otages, hostages, soldats, soldiers, troupes, troops, offensive, occupation,
        armement, weapons, ministre des affaires etrangeres, foreign minister""",
    "france": """france, francais, francaise, francaises, paris, assemblee nationale, senat, elysee, matignon,
        premier ministre, deputes, depute, senateurs, prefet, prefecture, marseille, lyon, toulouse, bordeaux,
        lille, nantes, strasbourg, montpellier, reunionnais, reunionnaise, guadeloupe, martinique, guyane,
        mayotte, nouvelle-caledonie, corse, macron, rassemblement national, france insoumise, gendarmerie,
        gendarmes""",
}


def _compiler(lexique: str) -> re.Pattern:
    termes = sorted({" ".join(t.split()) for t in lexique.split(",") if t.strip()}, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(?:" + "|".join(re.escape(t) for t in termes) + r")(?![\w-])")


MOTIFS = {rubrique: _compiler(texte) for rubrique, texte in LEXIQUES.items()}
ORDRE_LEXIQUES = ("sport", "culture", "sante", "sciences", "tech", "economie", "geopolitique", "france")


# --- Similarité et regroupement -----------------------------------------------------

def texte_item(item: dict) -> str:
    return f"{item['titre']}. {c.tronquer(item.get('resume', ''), 300)}"


def matrice_tfidf(textes: list[str]) -> np.ndarray:
    vectoriseur = TfidfVectorizer(
        strip_accents="unicode", lowercase=True, stop_words=MOTS_VIDES,
        token_pattern=r"(?u)\b\w\w+\b", sublinear_tf=True,
        max_df=0.3 if len(textes) >= 50 else 1.0,
    )
    try:
        matrice = vectoriseur.fit_transform(textes)
    except ValueError:  # vocabulaire vide
        return np.eye(len(textes), dtype=np.float32)
    return (matrice @ matrice.T).toarray().astype(np.float32)


def matrice_vecteurs(textes: list[str], modele: str) -> np.ndarray | None:
    """Cosinus entre vecteurs multilingues. None si fastembed ou le modèle manquent."""
    try:
        from fastembed import TextEmbedding
    except ImportError:
        log.warning("fastembed n'est pas installé : regroupement en TF-IDF seul")
        return None
    try:
        encodeur = TextEmbedding(model_name=modele, cache_dir=str(c.PIPELINE / "modeles"))
        vecteurs = np.asarray(list(encodeur.embed(textes, batch_size=64)), dtype=np.float32)
    except Exception as e:  # téléchargement impossible, cache corrompu…
        log.warning("Vecteurs multilingues indisponibles (%s) : TF-IDF seul", e)
        return None
    vecteurs /= np.linalg.norm(vecteurs, axis=1, keepdims=True) + 1e-9
    return vecteurs @ vecteurs.T


def similarites(items: list[dict], reglages: dict, reference: datetime) -> tuple[np.ndarray, str]:
    """Matrice de similarité et méthode réellement employée."""
    textes = [texte_item(it) for it in items]
    matrice = matrice_tfidf(textes)
    methode = "tfidf"
    if reglages.get("methode", "hybride") == "hybride":
        vecteurs = matrice_vecteurs(textes, reglages["modele_vecteurs"])
        if vecteurs is not None:
            poids = reglages["poids_vecteurs"]
            matrice = poids * vecteurs + (1 - poids) * matrice
            methode = "hybride"
    heures = np.array([(c.lire_date(it["date"]) or reference).timestamp() / 3600 for it in items])
    ecart_jours = np.abs(heures[:, None] - heures[None, :]) / 24
    matrice = matrice - reglages["penalite_par_jour"] * np.maximum(0.0, ecart_jours - 1.0)
    np.clip(matrice, 0.0, 1.0, out=matrice)
    np.fill_diagonal(matrice, 1.0)
    return matrice.astype(np.float32), methode


def regrouper(matrice: np.ndarray, seuil: float) -> np.ndarray:
    """Étiquette de groupe de chaque item (lien moyen, coupe à 1 - seuil)."""
    if len(matrice) == 1:
        return np.array([1])
    distances = 1.0 - matrice.astype(np.float64)
    distances = (distances + distances.T) / 2
    np.fill_diagonal(distances, 0.0)
    liens = linkage(squareform(distances, checks=False), method="average")
    return fcluster(liens, t=1.0 - seuil, criterion="distance")


# --- Indépendance, rubrique, score ----------------------------------------------------

def composantes_independantes(items: list[dict]) -> list[list[dict]]:
    """Regroupe les items de niveau 1 qui ne sont pas indépendants.

    Deux items dépendent l'un de l'autre s'ils appartiennent au même groupe de presse,
    reprennent la même agence (« avec AFP ») ou si l'un cite la source de l'autre.
    Chaque composante compte pour une seule source.
    """
    parent: dict[str, str] = {}

    def racine(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def unir(a: str, b: str) -> None:
        parent[racine(a)] = racine(b)

    niveau1 = [it for it in items if it.get("niveau") == 1]
    for it in niveau1:
        noeud = "g:" + it["groupe"]
        racine(noeud)
        for agence in it.get("agences", []):
            unir(noeud, "g:" + agence)  # une agence est son propre groupe (fiche_agence)
        for groupe in it.get("cites", []):
            unir(noeud, "g:" + groupe)
    composantes: dict[str, list[dict]] = defaultdict(list)
    for it in niveau1:
        composantes[racine("g:" + it["groupe"])].append(it)
    return list(composantes.values())


def textes_normalises(items: list[dict]) -> list[str]:
    return [c.sans_accents(f"{it['titre']} {it.get('resume', '')[:200]}".lower()) for it in items]


def part_avec(textes: list[str], motif: re.Pattern) -> float:
    return sum(1 for t in textes if motif.search(t)) / max(1, len(textes))


def rubrique_par_mots(textes: list[str]) -> str:
    scores = {r: sum(1 for t in textes if MOTIFS[r].search(t)) for r in ORDRE_LEXIQUES}
    meilleur = max(ORDRE_LEXIQUES, key=lambda r: scores[r])  # à égalité, l'ordre du tuple décide
    return meilleur if scores[meilleur] > 0 else "monde"


def classer(items: list[dict]) -> str:
    """Rubrique d'un groupe : vote des flux d'origine, corrigé par les lexiques."""
    votes: Counter = Counter()
    for it in items:
        rubrique = it.get("rubrique_flux") or ""
        if rubrique in c.RUBRIQUES:
            votes[rubrique] += 1.0 if it.get("niveau") == 1 else 0.5
    textes = textes_normalises(items)
    if votes:
        rubrique = votes.most_common(1)[0][0]
        france, monde = votes.get("france", 0), votes.get("monde", 0)
        # La presse étrangère range la France dans « Monde » : 40 % de votes « France » suffisent.
        if rubrique in ("france", "monde") and france and france >= 0.4 * (france + monde):
            rubrique = "france"
    else:
        rubrique = rubrique_par_mots(textes)
    if rubrique in ("monde", "france") and part_avec(textes, MOTIFS["geopolitique"]) >= 0.34:
        rubrique = "geopolitique"
    return rubrique


def noter(cluster: dict, notation: dict, reference: datetime) -> float:
    """Score = fiabilité × diffusion × fraîcheur × diversité géographique."""
    independants = cluster["independants"]
    if cluster["officiel_competent"]:
        independants = max(independants, 2)
    fiabilite = math.log2(1 + independants)
    diffusion = math.log2(1 + cluster["diffusion"])
    age = c.age_heures(cluster["derniere_activite"], reference)
    fraicheur = math.exp(-age / notation["constante_fraicheur_heures"])
    diversite = min(notation["bonus_pays_max"], 1 + notation["bonus_pays"] * max(0, len(cluster["pays"]) - 1))
    return round(fiabilite * diffusion * fraicheur * diversite, 4)


def decrire(items: list[dict], sous_matrice: np.ndarray, index: c.IndexSources, notation: dict,
            reference: datetime) -> dict:
    rubrique = classer(items)
    composantes = composantes_independantes(items)
    officiel = any(
        it.get("type") == "officiel" and rubrique in index.par_nom.get(it["source"], {}).get("competence", [])
        for it in items if it.get("niveau") == 1
    )
    niveau1 = [it for it in items if it.get("niveau") == 1]
    moyennes = sous_matrice.mean(axis=1)
    # Titre représentatif : un item français de niveau 1 si possible, le plus central sinon.
    representant = items[min(range(len(items)), key=lambda i: (
        items[i].get("langue") != "fr", items[i].get("niveau") != 1, -moyennes[i]))]
    cluster = {
        "id": min(items, key=lambda it: (it.get("vu_le", ""), it["id"]))["id"],
        "titre": representant["titre"],
        "rubrique": rubrique,
        "independants": len(composantes),
        "officiel_competent": officiel,
        "publiable": len(composantes) >= 2 or officiel,
        "diffusion": max(len({it["groupe"] for it in items}),
                         max((it.get("radar_domaines", 0) for it in items), default=0)),
        "pays": sorted({it["pays"] for it in items if it.get("pays")}),
        "langues": sorted({it.get("langue", "?") for it in items}),
        "sources": sorted({it["source"] for it in items}),
        "premiere_parution": min(it["date"] for it in items),
        "derniere_activite": max(it["date"] for it in (niveau1 or items)),
        "items": [it["id"] for it in sorted(items, key=lambda it: it["date"])],
    }
    cluster["score"] = noter(cluster, notation, reference)
    return cluster


# --- Construction, sauvegarde, rapport -----------------------------------------------

def construire(pool: dict[str, dict] | None = None, methode: str | None = None,
               seuil: float | None = None) -> list[dict]:
    reglages = dict(c.parametres()["regroupement"])
    if methode:
        reglages["methode"] = methode
    pool = c.lire_pool() if pool is None else pool
    reference = c.maintenant()
    items = [it for it in pool.values() if c.age_heures(it.get("date"), reference) <= reglages["fenetre_heures"]]
    items.sort(key=lambda it: it.get("date", ""), reverse=True)
    items = sorted(items[:MAX_ITEMS], key=lambda it: (it.get("vu_le", ""), it["id"]))
    if not items:
        log.warning("Pool vide : lancer d'abord python collecte.py")
        return []
    matrice, methode_employee = similarites(items, reglages, reference)
    if seuil is None:
        seuil = reglages["seuil"] if methode_employee == "hybride" else reglages.get("seuil_tfidf", reglages["seuil"])
    etiquettes = regrouper(matrice, seuil)
    positions_par_groupe: dict[int, list[int]] = defaultdict(list)
    for position, etiquette in enumerate(etiquettes):
        positions_par_groupe[int(etiquette)].append(position)
    index = c.index_sources()
    notation = c.parametres()["notation"]
    clusters = [
        decrire([items[p] for p in positions], matrice[np.ix_(positions, positions)], index, notation, reference)
        for positions in positions_par_groupe.values()
    ]
    clusters.sort(key=lambda cl: cl["score"], reverse=True)
    publiables = sum(1 for cl in clusters if cl["publiable"])
    log.info("%d items -> %d groupes (%s, seuil %.2f), %d publiables",
             len(items), len(clusters), methode_employee, seuil, publiables)
    return clusters


def enregistrer(clusters: list[dict]) -> None:
    c.ecrire_json(c.CLUSTERS, {"genere_a": c.iso(c.maintenant()), "clusters": clusters})


def charger() -> list[dict]:
    return (c.lire_json(c.CLUSTERS, {}) or {}).get("clusters", [])


def rapport(clusters: list[dict], pool: dict[str, dict], chemin=RAPPORT) -> None:
    """Rapport lisible pour calibrer le seuil à la main."""
    publiables = [cl for cl in clusters if cl["publiable"]]
    attente = sorted((cl for cl in clusters if not cl["publiable"] and cl["independants"] == 1),
                     key=lambda cl: cl["diffusion"], reverse=True)
    repartition = Counter(cl["rubrique"] for cl in publiables)
    lignes = [
        f"# Regroupement du {c.date_longue(c.date_locale())}",
        "",
        f"{sum(len(cl['items']) for cl in clusters)} items, {len(clusters)} groupes, {len(publiables)} publiables.",
        "Publiables par rubrique : " + ", ".join(f"{c.NOMS_RUBRIQUES[r]} {n}" for r, n in repartition.most_common()),
        "",
        "## Sujets publiables, par score",
        "",
    ]

    def bloc(cl: dict) -> list[str]:
        entete = (f"### {cl['score']:.2f} · {c.NOMS_RUBRIQUES.get(cl['rubrique'], cl['rubrique'])} · "
                  f"{cl['independants']} source(s) indépendante(s) · diffusion {cl['diffusion']} · "
                  f"{', '.join(cl['pays']) or 'pays ?'}")
        sortie = [entete, "", f"**{cl['titre']}**", ""]
        for identifiant in cl["items"]:
            it = pool.get(identifiant)
            if it:
                heure = (c.lire_date(it["date"]) or c.maintenant()).astimezone(c.fuseau()).strftime("%d/%m %H:%M")
                marque = "" if it.get("niveau") == 1 else " _(niveau 2)_"
                sortie.append(f"- {heure} · {it['source']} ({it.get('langue', '?')}){marque} : {it['titre']}")
        return sortie + [""]

    for cl in publiables[:120]:
        lignes += bloc(cl)
    lignes += ["## En attente d'une deuxième source indépendante (les plus repris d'abord)", ""]
    for cl in attente[:40]:
        lignes += bloc(cl)
    chemin.write_text("\n".join(lignes), encoding="utf-8")
    log.info("Rapport écrit : %s", chemin)


def main() -> None:
    parser = argparse.ArgumentParser(description="Regroupe les items par événement et note les sujets.")
    parser.add_argument("--seuil", type=float, help="seuil de similarité (sinon celui de pipeline.yaml)")
    parser.add_argument("--methode", choices=("hybride", "tfidf"))
    parser.add_argument("-v", "--verbeux", action="store_true")
    args = parser.parse_args()
    c.demarrer(args.verbeux)
    pool = c.lire_pool()
    clusters = construire(pool, args.methode, args.seuil)
    enregistrer(clusters)
    rapport(clusters, pool)


if __name__ == "__main__":
    main()
