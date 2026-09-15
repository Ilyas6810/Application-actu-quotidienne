"""Étape 2 : radar GDELT.

L'API DOC de GDELT bloque par adresse IP : 429 dès la première requête depuis une
adresse chargée, et le blocage dure plus longtemps que la faute. Les serveurs de
GitHub Actions partagent leurs adresses. Le radar lit donc les fichiers bruts de
GDELT 2.0, publiés toutes les 15 minutes et libres d'accès :
  - mentions : quel site parle de quel événement, avec l'URL de l'article ;
  - translation.mentions : la même chose pour 65 langues autres que l'anglais.

Un événement repris par beaucoup de sites différents devient une poignée d'items,
après lecture du titre et du résumé publics de quelques articles originaux
(sources connues d'abord, puis pays différents). Quand l'article est déjà dans le
pool, le radar se contente d'y noter l'ampleur de la reprise (radar_domaines).

Usage seul : python radar_gdelt.py   (liste les événements détectés, pool intact)
"""

from __future__ import annotations

import argparse
import io
import logging
import re
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests

import communs as c

log = logging.getLogger("gdelt")

BASE = "http://data.gdeltproject.org/gdeltv2/"
CACHE = c.ETAT / "gdelt"

# Langue d'origine des fichiers de traduction (ISO 639-2) vers les codes à deux lettres.
LANGUES = {
    "spa": "es", "fra": "fr", "deu": "de", "ita": "it", "por": "pt", "nld": "nl", "rus": "ru",
    "ukr": "uk", "pol": "pl", "tur": "tr", "ara": "ar", "heb": "he", "fas": "fa", "zho": "zh",
    "jpn": "ja", "kor": "ko", "ind": "id", "msa": "ms", "vie": "vi", "tha": "th", "hin": "hi",
    "ben": "bn", "urd": "ur", "ell": "el", "ron": "ro", "hun": "hu", "ces": "cs", "swe": "sv",
    "nor": "no", "dan": "da", "fin": "fi", "cat": "ca", "hrv": "hr", "srp": "sr", "bul": "bg",
    "slk": "sk", "slv": "sl", "lit": "lt", "lav": "lv", "est": "et", "tam": "ta", "swa": "sw",
}


class Evenement:
    __slots__ = ("id", "domaines", "urls", "debut")

    def __init__(self, identifiant: str):
        self.id = identifiant
        self.domaines: set[str] = set()
        self.urls: dict[str, tuple[str, str]] = {}  # url -> (domaine, langue)
        self.debut: datetime | None = None


def dernier_horodatage(session: requests.Session) -> datetime:
    reponse = session.get(BASE + "lastupdate.txt", timeout=20)
    reponse.raise_for_status()
    trouve = re.search(r"(\d{14})\.export", reponse.text)
    if not trouve:
        raise ValueError("lastupdate.txt illisible")
    return datetime.strptime(trouve.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)


def fichier(session: requests.Session, nom: str) -> bytes | None:
    """Télécharge un fichier de 15 minutes, avec cache disque (ils ne changent jamais)."""
    chemin = CACHE / nom
    if chemin.exists():
        return chemin.read_bytes()
    try:
        reponse = session.get(BASE + nom, timeout=60)
    except requests.RequestException as e:
        log.debug("%s : %s", nom, e)
        return None
    if reponse.status_code != 200:
        return None  # il manque parfois un fichier : on passe
    CACHE.mkdir(parents=True, exist_ok=True)
    chemin.write_bytes(reponse.content)
    return reponse.content


def lignes_zip(contenu: bytes) -> list[list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(contenu)) as archive:
            with archive.open(archive.namelist()[0]) as f:
                texte = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
                return [ligne.rstrip("\r\n").split("\t") for ligne in texte]
    except (zipfile.BadZipFile, IndexError, OSError):
        return []


def langue_de(info_traduction: str) -> str:
    trouve = re.search(r"srclc:(\w{3})", info_traduction or "")
    return LANGUES.get(trouve.group(1), trouve.group(1)) if trouve else "en"


def agreger(lignes: list[list[str]], age_max: timedelta, reference: datetime) -> dict[str, Evenement]:
    """Mentions -> événements. Colonnes utiles du fichier mentions (16 colonnes) :
    0 identifiant, 1 première détection de l'événement, 3 type (1 = web),
    4 domaine, 5 URL, 14 langue d'origine."""
    evenements: dict[str, Evenement] = {}
    for champs in lignes:
        if len(champs) < 15 or champs[3] != "1" or not champs[5].startswith("http"):
            continue
        try:
            debut = datetime.strptime(champs[1], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if reference - debut > age_max:
            continue  # vieil événement simplement recité (anniversaire, rappel)
        evenement = evenements.get(champs[0])
        if evenement is None:
            evenement = evenements[champs[0]] = Evenement(champs[0])
        domaine = champs[4].lower()
        evenement.domaines.add(domaine)
        evenement.urls.setdefault(champs[5], (domaine, langue_de(champs[14])))
        evenement.debut = min(evenement.debut or debut, debut)
    return evenements


def choisir_urls(evenement: Evenement, nombre: int, index: c.IndexSources, pool: dict) -> list[tuple[str, str, str]]:
    """Articles originaux à lire : sources connues d'abord, puis domaines et pays différents."""
    connues, autres = [], []
    for url, (domaine, langue) in evenement.urls.items():
        if c.empreinte(c.url_canonique(url)) in pool:
            continue
        (connues if index.source_du_domaine(domaine) else autres).append((url, domaine, langue))
    choix, domaines, pays = [], set(), set()
    for url, domaine, langue in connues + autres:
        if len(choix) >= nombre:
            break
        p = c.pays_du_domaine(domaine)
        if domaine in domaines or (p and p in pays and not index.source_du_domaine(domaine)):
            continue
        choix.append((url, domaine, langue))
        domaines.add(domaine)
        if p:
            pays.add(p)
    return choix


def item_radar(url: str, domaine: str, langue: str, page: dict, evenement: Evenement,
               index: c.IndexSources) -> dict:
    source = index.source_du_domaine(domaine)
    url_c = c.url_canonique(url)
    publie = c.lire_date(page.get("publie"))
    date_item = min(publie or evenement.debut or c.maintenant(), c.maintenant())
    resume = c.tronquer(page.get("resume", ""), c.parametres()["collecte"]["longueur_resume"])
    groupe = source["groupe"] if source else domaine
    texte = f"{page['titre']} {resume}"
    return {
        "id": c.empreinte(url_c),
        "url": url_c,
        "titre": page["titre"],
        "resume": resume,
        "date": c.iso(date_item),
        "date_estimee": publie is None,
        "vu_le": c.iso(c.maintenant()),
        "langue": page.get("langue") or langue,
        "source": source["nom"] if source else domaine,
        "groupe": groupe,
        "pays": (source or {}).get("pays") or c.pays_du_domaine(domaine),
        "niveau": source.get("niveau", 1) if source else 2,
        "type": source.get("type", "presse") if source else "radar",
        "rubrique_flux": "",
        "agences": index.agences_citees(texte),
        "cites": index.groupes_cites(texte, groupe),
        "via": "gdelt",
        "radar_domaines": len(evenement.domaines),
    }


def detecter(session: requests.Session, pool: dict) -> list[Evenement]:
    """Lit les fichiers de la fenêtre et renvoie les événements les plus repris."""
    reglages = c.parametres()["gdelt"]
    fin = dernier_horodatage(session)
    noms = []
    for i in range(int(reglages["fenetre_heures"] * 4)):
        horodatage = (fin - timedelta(minutes=15 * i)).strftime("%Y%m%d%H%M%S")
        noms += [f"{horodatage}.mentions.CSV.zip", f"{horodatage}.translation.mentions.CSV.zip"]
    lignes: list[list[str]] = []
    with ThreadPoolExecutor(max_workers=6) as executeur:
        for contenu in executeur.map(lambda n: fichier(session, n), noms):
            if contenu:
                lignes.extend(lignes_zip(contenu))
    if CACHE.exists():  # le cache ne garde que la fenêtre courante
        for f in CACHE.iterdir():
            if f.name not in noms:
                f.unlink(missing_ok=True)
    evenements = agreger(lignes, timedelta(days=reglages["age_max_evenement_jours"]), c.maintenant())
    log.info("GDELT : %d fichiers, %d mentions, %d événements récents", len(noms), len(lignes), len(evenements))
    candidats = sorted((e for e in evenements.values() if len(e.domaines) >= reglages["min_domaines"]),
                       key=lambda e: len(e.domaines), reverse=True)
    # Ampleur de la reprise notée sur les articles déjà connus.
    for evenement in candidats:
        for url in evenement.urls:
            item = pool.get(c.empreinte(c.url_canonique(url)))
            if item is not None:
                item["radar_domaines"] = max(item.get("radar_domaines", 0), len(evenement.domaines))
    # Un même fait produit plusieurs événements GDELT : on écarte ceux qui partagent leurs URL.
    retenus, urls_prises = [], set()
    for evenement in candidats:
        urls = set(evenement.urls)
        if len(urls & urls_prises) > 0.3 * len(urls):
            continue
        urls_prises |= urls
        retenus.append(evenement)
        if len(retenus) >= reglages["max_evenements"]:
            break
    return retenus


def collecter(session: requests.Session, index: c.IndexSources, pool: dict) -> list[dict]:
    reglages = c.parametres()["gdelt"]
    retenus = detecter(session, pool)
    taches = [(e, *choix) for e in retenus for choix in choisir_urls(e, reglages["urls_par_evenement"], index, pool)]
    taches = taches[: reglages["lectures_max"]]
    with ThreadPoolExecutor(max_workers=8) as executeur:
        pages = list(executeur.map(lambda t: c.lire_og(session, t[1]), taches))
    items = [item_radar(url, domaine, langue, page, e, index)
             for (e, url, domaine, langue), page in zip(taches, pages) if page]
    log.info("GDELT : %d événements retenus, %d pages lues, %d exploitables", len(retenus), len(taches), len(items))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Affiche les événements détectés par le radar GDELT.")
    parser.add_argument("-v", "--verbeux", action="store_true")
    args = parser.parse_args()
    c.demarrer(args.verbeux)
    session = c.session_http()
    pool = c.lire_pool()
    for evenement in detecter(session, pool):
        langues = sorted({langue for _, langue in evenement.urls.values()})
        exemple = next(iter(evenement.urls))
        print(f"{len(evenement.domaines):4d} sites  {'/'.join(langues):12s}  {exemple}")


if __name__ == "__main__":
    main()
