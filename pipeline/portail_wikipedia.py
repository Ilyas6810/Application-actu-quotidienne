"""Filet de sécurité : le portail des événements actuels de Wikipédia (anglais).

Chaque puce du portail, rédigée et sourcée par des bénévoles, devient un item de
niveau 2 : elle ne compte jamais comme source indépendante. Les liens qu'elle cite
vers une source connue (Reuters, AP, BBC…) deviennent des items de niveau 1 :
c'est par là que les agences sans flux public entrent dans le pipeline, comme le
prévoit le cahier des charges. Pour ces liens, on lit le titre et le résumé publics
de l'article ; si la page refuse les robots, on garde le texte du portail et on le
signale (champ resume_de), pour que la rédaction sache d'où vient ce résumé.

Usage seul : python portail_wikipedia.py   (affiche les événements, pool intact)
"""

from __future__ import annotations

import argparse
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta, timezone

import requests
from bs4 import BeautifulSoup

import communs as c

log = logging.getLogger("wikipedia")

API = "https://en.wikipedia.org/w/api.php"
NOM_SOURCE = "Wikipédia (portail d'actualité)"
MOIS_ANGLAIS = ("January", "February", "March", "April", "May", "June", "July", "August",
                "September", "October", "November", "December")
CATEGORIES = {
    "armed conflicts and attacks": "geopolitique",
    "international relations": "geopolitique",
    "politics and elections": "monde",
    "disasters and accidents": "monde",
    "law and crime": "monde",
    "business and economy": "economie",
    "health and environment": "sante",
    "science and technology": "sciences",
    "arts and culture": "culture",
    "sports": "sport",
}


def page_du_jour(jour: date) -> str:
    return f"Portal:Current_events/{jour.year}_{MOIS_ANGLAIS[jour.month - 1]}_{jour.day}"


def telecharger(session: requests.Session, jour: date) -> str | None:
    parametres_api = {"action": "parse", "page": page_du_jour(jour), "prop": "text",
                      "formatversion": "2", "format": "json", "redirects": "1"}
    try:
        donnees = session.get(API, params=parametres_api, timeout=25).json()
    except (requests.RequestException, ValueError) as e:
        log.warning("Portail du %s illisible : %s", jour, e)
        return None
    if "error" in donnees:
        log.info("Portail du %s pas encore publié", jour)
        return None
    return donnees.get("parse", {}).get("text")


def evenements(html_page: str) -> list[dict]:
    """Puces-événements du portail : texte, catégorie, sujets englobants, liens cités."""
    soup = BeautifulSoup(html_page, "html.parser")
    trouves: list[dict] = []
    for bloc in soup.select("div.current-events-content"):
        categorie = ""
        for enfant in bloc.find_all(recursive=False):
            if enfant.name == "p" and enfant.find("b"):
                categorie = enfant.get_text(" ", strip=True).lower()
            elif enfant.name == "ul":
                parcourir(enfant, categorie, [], trouves)
    return trouves


def parcourir(liste, categorie: str, sujets: list[str], trouves: list[dict]) -> None:
    for puce in liste.find_all("li", recursive=False):
        sous_liste = puce.find("ul", recursive=False)
        if sous_liste is not None:
            sous_liste = sous_liste.extract()  # il reste l'intitulé du sujet
            parcourir(sous_liste, categorie, sujets + [puce.get_text(" ", strip=True)], trouves)
            continue
        liens = [a for a in puce.find_all("a", href=True) if "external" in (a.get("class") or [])]
        urls = [a["href"] for a in liens if a["href"].startswith("http")]
        for a in liens:
            a.decompose()  # retire « (Reuters) » du texte
        texte = c.nettoyer_html(puce.get_text(" ", strip=True))
        texte = re.sub(r"\(\s*\)", "", re.sub(r"\s+([.,;:!?)])", r"\1", texte)).strip()
        if len(texte) >= 30:
            trouves.append({"texte": texte, "categorie": categorie, "sujets": sujets, "urls": urls})


def premiere_phrase(texte: str) -> str:
    trouve = re.match(r"(.{20,220}?[.!?])(?:\s+[A-Z0-9]|$)", texte)
    return trouve.group(1) if trouve else c.tronquer(texte, 200)


def item_portail(evenement: dict, jour: date, moment: datetime, index: c.IndexSources) -> dict:
    contexte = " › ".join(evenement["sujets"])
    resume = f"{evenement['texte']} (Sujet : {contexte}.)" if contexte else evenement["texte"]
    # Le fragment « # » disparaîtrait à la canonisation : l'identifiant va dans la requête.
    url = c.url_canonique(f"https://en.wikipedia.org/wiki/{page_du_jour(jour)}"
                          f"?evenement={c.empreinte(evenement['texte'], 10)}")
    return {
        "id": c.empreinte(url),
        "url": url,
        "titre": premiere_phrase(evenement["texte"]),
        "resume": c.tronquer(resume, 700),
        "date": c.iso(moment),
        "date_estimee": True,
        "vu_le": c.iso(c.maintenant()),
        "langue": "en",
        "source": NOM_SOURCE,
        "groupe": "Wikimédia",
        "pays": None,
        "niveau": 2,
        "type": "wikipedia",
        "rubrique_flux": CATEGORIES.get(evenement["categorie"], ""),
        "agences": index.agences_citees(evenement["texte"]),
        "cites": [],
        "via": "wikipedia",
        "liens_cites": evenement["urls"][:6],
    }


def item_cite(url: str, source: dict, portail: dict, page: dict | None, index: c.IndexSources) -> dict:
    """Article cité par le portail, attribué à sa source d'origine."""
    if page and page.get("titre"):
        titre, resume, resume_de = page["titre"], c.tronquer(page.get("resume", ""), 700), None
        publie = c.lire_date(page.get("publie"))
    else:
        titre, resume, resume_de = portail["titre"], portail["resume"], "Wikipédia"
        publie = None
    texte = f"{titre} {resume}"
    item = {
        "id": c.empreinte(url),
        "url": url,
        "titre": titre,
        "resume": resume,
        "date": c.iso(min(publie or c.lire_date(portail["date"]), c.maintenant())),
        "date_estimee": publie is None,
        "vu_le": c.iso(c.maintenant()),
        "langue": (page or {}).get("langue") or source.get("langue", "en"),
        "source": source["nom"],
        "groupe": source["groupe"],
        "pays": source.get("pays"),
        "niveau": source.get("niveau", 1),
        "type": source.get("type", "presse"),
        "rubrique_flux": portail["rubrique_flux"],
        "agences": [] if resume_de else index.agences_citees(texte),
        "cites": [] if resume_de else index.groupes_cites(texte, source["groupe"]),
        "via": "wikipedia",
    }
    if resume_de:
        item["resume_de"] = resume_de
    return item


def collecter(session: requests.Session, index: c.IndexSources, pool: dict) -> list[dict]:
    reglages = c.parametres().get("wikipedia", {})
    aujourd_hui = c.maintenant().date()
    items: list[dict] = []
    a_lire: dict[str, tuple[dict, dict]] = {}
    for decalage in range(reglages.get("jours", 2)):
        jour = aujourd_hui - timedelta(days=decalage)
        page = telecharger(session, jour)
        if not page:
            continue
        moment = min(datetime.combine(jour, time(12), tzinfo=timezone.utc), c.maintenant())
        for evenement in evenements(page):
            portail = item_portail(evenement, jour, moment, index)
            items.append(portail)
            for lien in evenement["urls"]:
                source = index.source_du_domaine(c.domaine(lien))
                url = c.url_canonique(lien)
                if source is not None and c.empreinte(url) not in pool:
                    a_lire.setdefault(url, (source, portail))
    lectures = list(a_lire.items())[: reglages.get("lectures_max", 40)]
    with ThreadPoolExecutor(max_workers=8) as executeur:
        pages = list(executeur.map(lambda t: c.lire_og(session, t[0]), lectures))
    for (url, (source, portail)), page in zip(lectures, pages):
        items.append(item_cite(url, source, portail, page, index))
    log.info("Wikipédia : %d événements, %d articles cités de sources connues", len(items) - len(lectures), len(lectures))
    return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Affiche les événements du portail Wikipédia.")
    parser.add_argument("-v", "--verbeux", action="store_true")
    args = parser.parse_args()
    c.demarrer(args.verbeux)
    session = c.session_http()
    page = telecharger(session, c.maintenant().date()) or telecharger(session, c.maintenant().date() - timedelta(days=1))
    for evenement in evenements(page or ""):
        print(f"[{evenement['categorie'][:22]:22s}] {evenement['texte'][:110]}  ({len(evenement['urls'])} liens)")


if __name__ == "__main__":
    main()
