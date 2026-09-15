"""Outils partagés par les scripts du pipeline.

Chemins, configuration, dates, HTTP, nettoyage de texte, URL canoniques,
lecture et écriture de l'état. Aucun script n'importe un autre script :
tout ce qui sert à plusieurs endroits vit ici.
"""

from __future__ import annotations

import gzip
import hashlib
import html
import json
import logging
import os
import re
import sys
import tempfile
import unicodedata
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

PIPELINE = Path(__file__).resolve().parent
RACINE = PIPELINE.parent
CONFIG = PIPELINE / "config"
ETAT = PIPELINE / "etat"
DOCS = RACINE / "docs"
EDITIONS = DOCS / "editions"
POOL = ETAT / "pool.json.gz"
CLUSTERS = ETAT / "clusters.json"

RUBRIQUES = ("monde", "france", "geopolitique", "economie", "tech", "sciences", "sante", "sport", "culture")
NOMS_RUBRIQUES = {
    "une": "À la une",
    "monde": "Monde",
    "france": "France",
    "geopolitique": "Géopolitique",
    "economie": "Économie",
    "tech": "Tech / IA",
    "sciences": "Sciences",
    "sante": "Santé",
    "sport": "Sport",
    "culture": "Culture",
}

log = logging.getLogger("communs")


# --- Console, journal, variables d'environnement --------------------------------

def preparer_console() -> None:
    """Force l'UTF-8 sur la console : sous Windows les accents sortent sinon en bouillie."""
    for flux in (sys.stdout, sys.stderr):
        try:
            flux.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def configurer_journal(verbeux: bool = False) -> None:
    preparer_console()
    logging.basicConfig(
        level=logging.DEBUG if verbeux else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-10s %(message)s",
        datefmt="%H:%M:%S",
    )
    for bruyant in ("urllib3", "filelock", "httpx", "huggingface_hub", "fastembed"):
        logging.getLogger(bruyant).setLevel(logging.WARNING)


def charger_env(chemin: Path | None = None) -> None:
    """Charge pipeline/.env (clés d'API en local). Une variable déjà définie garde la priorité."""
    chemin = chemin or PIPELINE / ".env"
    if not chemin.exists():
        return
    for ligne in chemin.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        cle, valeur = cle.strip(), valeur.strip().strip('"').strip("'")
        if cle and valeur and cle not in os.environ:
            os.environ[cle] = valeur


def demarrer(verbeux: bool = False) -> None:
    """À appeler en tête de chaque script."""
    configurer_journal(verbeux)
    charger_env()
    ETAT.mkdir(parents=True, exist_ok=True)


# --- Configuration ----------------------------------------------------------------

@lru_cache(maxsize=None)
def charger_yaml(nom: str) -> dict:
    with open(CONFIG / nom, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def parametres() -> dict:
    return charger_yaml("pipeline.yaml")


# --- Dates ------------------------------------------------------------------------

JOURS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
MOIS = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre")


def maintenant() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    """Date UTC au format 2026-09-11T01:40:00Z."""
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def lire_date(texte: str | None) -> datetime | None:
    if not texte:
        return None
    try:
        dt = datetime.fromisoformat(texte.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def age_heures(texte_iso: str | None, reference: datetime | None = None) -> float:
    dt = lire_date(texte_iso)
    if dt is None:
        return 0.0
    return max(0.0, ((reference or maintenant()) - dt).total_seconds() / 3600)


def fuseau() -> ZoneInfo:
    return ZoneInfo(parametres().get("fuseau", "Indian/Reunion"))


def date_locale(dt: datetime | None = None) -> date:
    """Date du jour à l'heure locale de l'édition (UTC+4)."""
    return (dt or maintenant()).astimezone(fuseau()).date()


def date_longue(d: date) -> str:
    return f"{JOURS[d.weekday()]} {d.day} {MOIS[d.month - 1]} {d.year}"


# --- HTTP -------------------------------------------------------------------------

def agent_utilisateur() -> str:
    """User-Agent honnête : on se déclare comme robot, avec un lien de contact."""
    contact = parametres().get("contact", "")
    suffixe = f"; +{contact}" if contact else ""
    return f"Mozilla/5.0 (compatible; ActuQuotidienne/0.1{suffixe})"


def session_http() -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = agent_utilisateur()
    reprises = Retry(
        total=2, connect=2, read=1, status=2, backoff_factor=1.5,
        status_forcelist=(500, 502, 503, 504), allowed_methods=("GET", "HEAD"),
        raise_on_status=False,
    )
    adaptateur = HTTPAdapter(max_retries=reprises, pool_connections=24, pool_maxsize=24)
    session.mount("https://", adaptateur)
    session.mount("http://", adaptateur)
    return session


# --- Texte ------------------------------------------------------------------------

_BALISES = re.compile(r"<[^>]+>")
_ESPACES = re.compile(r"\s+")
_MOT = re.compile(r"\w+(?:['’-]\w+)*")


def nettoyer_html(texte: str | None) -> str:
    """Retire les balises et les entités HTML, écrase les espaces."""
    if not texte:
        return ""
    texte = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", texte)
    texte = _BALISES.sub(" ", texte)
    texte = html.unescape(texte).replace(chr(0xA0), " ").replace(chr(0x202F), " ").replace(chr(0x200B), "")
    return _ESPACES.sub(" ", texte).strip()


def tronquer(texte: str, limite: int) -> str:
    """Coupe à la limite, sur une frontière de mot."""
    if len(texte) <= limite:
        return texte
    coupe = texte[:limite]
    espace = coupe.rfind(" ")
    if espace > limite * 0.6:
        coupe = coupe[:espace]
    return coupe.rstrip(" ,;:") + "…"


def sans_accents(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texte) if not unicodedata.combining(c))


def mots_normalises(texte: str) -> list[str]:
    """Minuscules, sans accents, sans ponctuation : sert aux comparaisons mécaniques."""
    return re.findall(r"\w+", sans_accents(texte.lower()))


def compter_mots(texte: str) -> int:
    """« l'Élysée » et « peut-être » comptent pour un mot, comme dans un traitement de texte."""
    return len(_MOT.findall(texte))


def empreinte(texte: str, longueur: int = 16) -> str:
    return hashlib.sha1(texte.encode("utf-8")).hexdigest()[:longueur]


# --- URL --------------------------------------------------------------------------

_PARAMETRES_SUIVI = re.compile(
    r"^(utm_|at_|xtor|xts|ns_|fbclid|gclid|mc_|cmp|ito|ref$|src$|source$|origin$|partner|"
    r"dicbo|smid|ncid|ocid|taid|share|output$|rss$|feed$|from$|mod$|traffic_source)",
    re.IGNORECASE,
)


def url_canonique(url: str) -> str:
    """Forme normalisée d'une URL, pour dédoublonner.

    Schéma https, hôte sans « www. », sans fragment, sans paramètres de suivi,
    sans barre finale ni suffixe /amp.
    """
    url = (url or "").strip()
    # Lien de redirection qui embarque l'adresse réelle (Folha : redir.folha.com.br/…/*https://www1.folha…)
    emballe = re.search(r"\*(https?://.+)$", url)
    if emballe:
        url = emballe.group(1)
    try:
        morceaux = urlsplit(url)
    except ValueError:
        return url
    hote = (morceaux.hostname or "").lower()
    if hote.startswith("www."):
        hote = hote[4:]
    if not hote:
        return url
    chemin = re.sub(r"/amp/?$", "", morceaux.path or "")
    if len(chemin) > 1:
        chemin = chemin.rstrip("/")
    parametres_url = [(k, v) for k, v in parse_qsl(morceaux.query) if not _PARAMETRES_SUIVI.match(k)]
    return urlunsplit(("https", hote, chemin, urlencode(sorted(parametres_url)), ""))


def domaine(url: str) -> str:
    try:
        hote = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return ""
    return hote[4:] if hote.startswith("www.") else hote


def domaine_couvert(dom: str, site: str) -> bool:
    """Vrai si dom est le site lui-même ou l'un de ses sous-domaines."""
    return dom == site or dom.endswith("." + site)


# Pays déduit du suffixe du domaine (radar GDELT). Les .com, .org, .net restent inconnus.
PAYS_PAR_SUFFIXE = {
    "fr": "FR", "re": "FR", "gp": "FR", "mq": "FR", "nc": "FR", "pf": "FR", "yt": "FR",
    "uk": "GB", "ie": "IE", "de": "DE", "at": "AT", "ch": "CH", "be": "BE", "nl": "NL", "lu": "LU",
    "es": "ES", "pt": "PT", "it": "IT", "gr": "GR", "pl": "PL", "cz": "CZ", "sk": "SK", "hu": "HU",
    "ro": "RO", "bg": "BG", "rs": "RS", "hr": "HR", "si": "SI", "se": "SE", "no": "NO", "dk": "DK",
    "fi": "FI", "ee": "EE", "lv": "LV", "lt": "LT", "ua": "UA", "ru": "RU", "by": "BY", "md": "MD",
    "tr": "TR", "il": "IL", "lb": "LB", "jo": "JO", "sy": "SY", "iq": "IQ", "ir": "IR", "sa": "SA",
    "ae": "AE", "qa": "QA", "kw": "KW", "om": "OM", "ye": "YE", "eg": "EG", "ma": "MA", "dz": "DZ",
    "tn": "TN", "ly": "LY", "sn": "SN", "ci": "CI", "ml": "ML", "bf": "BF", "ne": "NE", "cm": "CM",
    "cd": "CD", "cg": "CG", "ga": "GA", "ng": "NG", "gh": "GH", "ke": "KE", "et": "ET", "tz": "TZ",
    "ug": "UG", "rw": "RW", "za": "ZA", "zw": "ZW", "mg": "MG", "mu": "MU", "sc": "SC", "km": "KM",
    "in": "IN", "pk": "PK", "bd": "BD", "lk": "LK", "np": "NP", "af": "AF", "cn": "CN", "hk": "HK",
    "tw": "TW", "jp": "JP", "kr": "KR", "ph": "PH", "vn": "VN", "th": "TH", "my": "MY", "sg": "SG",
    "id": "ID", "au": "AU", "nz": "NZ", "ca": "CA", "mx": "MX", "br": "BR", "ar": "AR", "cl": "CL",
    "co": "CO", "pe": "PE", "ve": "VE", "ec": "EC", "bo": "BO", "uy": "UY", "py": "PY", "cu": "CU",
    "ht": "HT", "do": "DO", "gt": "GT", "hn": "HN", "sv": "SV", "ni": "NI", "cr": "CR", "pa": "PA",
    "kz": "KZ", "uz": "UZ", "ge": "GE", "am": "AM", "az": "AZ", "mn": "MN",
}


def pays_du_domaine(dom: str) -> str | None:
    suffixe = dom.rsplit(".", 1)[-1] if "." in dom else ""
    return PAYS_PAR_SUFFIXE.get(suffixe)


# --- Fichiers ---------------------------------------------------------------------

def lire_json(chemin: Path, defaut: Any = None) -> Any:
    if not chemin.exists():
        return defaut
    ouvrir = gzip.open if chemin.suffix == ".gz" else open
    try:
        with ouvrir(chemin, "rt", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, EOFError, json.JSONDecodeError) as e:
        log.warning("Lecture impossible de %s : %s", chemin, e)
        return defaut


def ecrire_json(chemin: Path, donnees: Any, compact: bool = False) -> None:
    """Écriture atomique : un fichier à moitié écrit ne remplace jamais le bon."""
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, temporaire = tempfile.mkstemp(dir=chemin.parent, prefix=chemin.name + ".", suffix=".tmp")
    os.close(fd)
    ouvrir = gzip.open if chemin.suffix == ".gz" else open
    try:
        with ouvrir(temporaire, "wt", encoding="utf-8") as f:
            if compact:
                json.dump(donnees, f, ensure_ascii=False, separators=(",", ":"))
            else:
                json.dump(donnees, f, ensure_ascii=False, indent=1)
        os.replace(temporaire, chemin)
    finally:
        if os.path.exists(temporaire):
            os.remove(temporaire)


def lire_pool() -> dict[str, dict]:
    """Items collectés sur les dernières 72 heures, indexés par identifiant."""
    donnees = lire_json(POOL, {"items": []}) or {"items": []}
    return {item["id"]: item for item in donnees.get("items", [])}


def ecrire_pool(items: dict[str, dict]) -> None:
    tries = sorted(items.values(), key=lambda i: i.get("date", ""), reverse=True)
    ecrire_json(POOL, {"maj": iso(maintenant()), "items": tries}, compact=True)


# --- Sources ----------------------------------------------------------------------

class IndexSources:
    """Accès rapide aux sources configurées : par domaine, par nom, par motif cité."""

    def __init__(self, conf: dict):
        self.sources: list[dict] = conf.get("sources", [])
        self.agences: list[dict] = conf.get("agences", [])
        self._par_site: dict[str, dict] = {}
        self.par_nom: dict[str, dict] = {}
        for source in self.sources:
            self.par_nom[source["nom"]] = source
            for site in source.get("sites", []):
                self._par_site[site] = source
        for agence in self.agences:
            fiche = self.fiche_agence(agence)
            self.par_nom[agence["nom"]] = fiche
            for site in agence.get("sites", []):
                self._par_site[site] = fiche
        # Les motifs d'agence sont sensibles à la casse : « AFP » oui, « afp » dans une URL non.
        self._motifs_agences = [(a["nom"], re.compile("|".join(a["motifs"]))) for a in self.agences]
        self._motifs_citations = []
        for source in self.sources:
            alias = source.get("alias") or [source["nom"]]
            motif = "|".join(rf"(?<![\w-]){re.escape(a)}(?![\w-])" for a in alias)
            self._motifs_citations.append((source["groupe"], re.compile(motif)))

    @staticmethod
    def fiche_agence(agence: dict) -> dict:
        """Une agence vue comme une source de niveau 1, son propre groupe."""
        return {
            "nom": agence["nom"], "groupe": agence["nom"], "pays": agence.get("pays"),
            "langue": agence.get("langue", "en"), "type": "agence", "niveau": 1,
            "sites": agence.get("sites", []),
        }

    def source_du_domaine(self, dom: str) -> dict | None:
        morceaux = dom.split(".")
        for i in range(len(morceaux) - 1):
            candidat = ".".join(morceaux[i:])
            if candidat in self._par_site:
                return self._par_site[candidat]
        return None

    def agences_citees(self, texte: str) -> list[str]:
        return [nom for nom, motif in self._motifs_agences if motif.search(texte)]

    def groupes_cites(self, texte: str, groupe_auteur: str) -> list[str]:
        """Groupes d'autres sources mentionnées dans le texte (« selon la BBC »)."""
        return sorted({g for g, motif in self._motifs_citations if g != groupe_auteur and motif.search(texte)})


@lru_cache(maxsize=None)
def index_sources() -> IndexSources:
    return IndexSources(charger_yaml("sources.yaml"))


# --- Pages web : métadonnées publiques de partage --------------------------------

_META = re.compile(r"<meta\b[^>]*>", re.IGNORECASE)
_ATTRIBUT = re.compile(r"""([\w:.-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_TITRE_PAGE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_LANGUE_PAGE = re.compile(r"""<html\b[^>]*\blang\s*=\s*["']?([a-zA-Z]{2})""", re.IGNORECASE)


def lire_og(session: requests.Session, url: str, delai: int = 12) -> dict | None:
    """Titre et résumé publics d'un article (balises og:title et og:description).

    Seul l'en-tête de la page est lu, jamais le corps de l'article.
    Renvoie None si la page est inaccessible ou sans métadonnées.
    """
    try:
        reponse = session.get(url, timeout=delai, stream=True)
        if reponse.status_code != 200 or "html" not in reponse.headers.get("Content-Type", "").lower():
            reponse.close()
            return None
        brut = b""
        for morceau in reponse.iter_content(16384):
            brut += morceau
            if len(brut) > 400_000 or b"</head>" in brut:
                break
        reponse.close()
    except requests.RequestException:
        return None
    declare = re.search(rb"""charset=["']?([\w-]+)""", brut[:4000], re.IGNORECASE)
    try:
        texte = brut.decode(declare.group(1).decode("ascii") if declare else "utf-8", errors="replace")
    except LookupError:
        texte = brut.decode("utf-8", errors="replace")
    metas: dict[str, str] = {}
    for balise in _META.findall(texte):
        attributs = {
            m.group(1).lower(): m.group(2) if m.group(2) is not None else m.group(3)
            for m in _ATTRIBUT.finditer(balise)
        }
        cle = (attributs.get("property") or attributs.get("name") or "").lower()
        if cle and attributs.get("content"):
            metas.setdefault(cle, nettoyer_html(attributs["content"]))
    titre = metas.get("og:title") or metas.get("twitter:title")
    if not titre:
        trouve = _TITRE_PAGE.search(texte)
        titre = nettoyer_html(trouve.group(1)) if trouve else ""
    if not titre:
        return None
    langue = _LANGUE_PAGE.search(texte)
    return {
        "titre": titre,
        "resume": metas.get("og:description") or metas.get("description") or metas.get("twitter:description") or "",
        "langue": langue.group(1).lower() if langue else None,
        "publie": metas.get("article:published_time"),
    }
