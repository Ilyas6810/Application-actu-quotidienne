"""Étape 1 : collecte.

Lit les flux RSS de config/sources.yaml, puis le radar GDELT et le portail
Wikipédia. Chaque entrée devient un « item » normalisé, ajouté au pool
(etat/pool.json.gz) : 72 heures glissantes, dédoublonnées par URL canonique.

Usage :
    python collecte.py                  # flux RSS + GDELT + Wikipédia
    python collecte.py --rss-seulement  # flux RSS seuls
    python collecte.py -v               # journal détaillé

Vérification de l'étape 1 : le bilan final affiche des centaines d'items et zéro
doublon d'URL ; etat/sante_flux.json donne l'état de chaque flux.
"""

from __future__ import annotations

import argparse
import calendar
import importlib
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import feedparser
import requests

import communs as c

log = logging.getLogger("collecte")

CACHE_HTTP = c.ETAT / "cache_http.json"
SANTE = c.ETAT / "sante_flux.json"

# Quand deux collectes trouvent la même URL, la version la plus fiable l'emporte.
PRIORITE_VIA = {"rss": 3, "gdelt": 2, "wikipedia": 1}


def date_entree(entree) -> datetime | None:
    for champ in ("published_parsed", "updated_parsed", "created_parsed"):
        valeur = entree.get(champ)
        if not valeur:
            continue
        try:
            return datetime.fromtimestamp(calendar.timegm(valeur), tz=timezone.utc)
        except (OverflowError, ValueError, TypeError):
            continue
    return None


def resume_entree(entree) -> str:
    resume = c.nettoyer_html(entree.get("summary") or entree.get("description"))
    if len(resume) < 40:
        for contenu in entree.get("content") or []:
            texte = c.nettoyer_html(contenu.get("value"))
            if len(texte) > len(resume):
                resume = texte
    return resume


def construire_item(source: dict, flux: dict, entree, vu_le: datetime, reglages: dict,
                    index: c.IndexSources) -> dict | None:
    lien = (entree.get("link") or "").strip()
    titre = c.nettoyer_html(entree.get("title"))
    if not lien.startswith("http") or not titre:
        return None
    resume = "" if source.get("titres_seuls") else resume_entree(entree)
    if resume.lower() == titre.lower():
        resume = ""
    resume = c.tronquer(resume, reglages["longueur_resume"])
    publie = date_entree(entree)
    date_estimee = publie is None
    publie = min(publie or vu_le, vu_le)  # certains flux datent dans le futur
    if (vu_le - publie).total_seconds() > reglages["age_max_heures"] * 3600:
        return None
    url = c.url_canonique(lien)
    texte = f"{titre} {resume}"
    return {
        "id": c.empreinte(url),
        "url": url,
        "titre": titre,
        "resume": resume,
        "date": c.iso(publie),
        "date_estimee": date_estimee,
        "vu_le": c.iso(vu_le),
        "langue": flux.get("langue") or source.get("langue", "en"),
        "source": source["nom"],
        "groupe": source["groupe"],
        "pays": source.get("pays"),
        "niveau": source.get("niveau", 1),
        "type": source.get("type", "presse"),
        "rubrique_flux": flux.get("rubrique", ""),
        "agences": index.agences_citees(texte),
        "cites": index.groupes_cites(texte, source["groupe"]),
        "via": "rss",
    }


def lire_flux(session: requests.Session, source: dict, flux: dict, cache: dict, reglages: dict,
              index: c.IndexSources, vu_le: datetime) -> tuple[list[dict], dict, dict | None]:
    """Télécharge et analyse un flux. Renvoie (items, bilan, validateurs HTTP)."""
    url = flux["url"]
    bilan = {"source": source["nom"], "rubrique": flux.get("rubrique", ""), "statut": None,
             "items": 0, "erreur": None}
    entetes = {}
    if cache.get(url, {}).get("etag"):
        entetes["If-None-Match"] = cache[url]["etag"]
    if cache.get(url, {}).get("modifie"):
        entetes["If-Modified-Since"] = cache[url]["modifie"]
    try:
        reponse = session.get(url, headers=entetes, timeout=reglages["delai_http"])
    except requests.RequestException as e:
        bilan["erreur"] = type(e).__name__
        return [], bilan, None
    bilan["statut"] = reponse.status_code
    if reponse.status_code == 304:
        return [], bilan, cache.get(url)
    if not reponse.ok:
        bilan["erreur"] = f"HTTP {reponse.status_code}"
        return [], bilan, None
    analyse = feedparser.parse(reponse.content)
    if not analyse.entries:
        bilan["erreur"] = "flux vide ou illisible"
        return [], bilan, None
    items = [i for i in (construire_item(source, flux, e, vu_le, reglages, index) for e in analyse.entries) if i]
    bilan["items"] = len(items)
    validateurs = {"etag": reponse.headers.get("ETag"), "modifie": reponse.headers.get("Last-Modified")}
    return items, bilan, validateurs


def fusionner(pool: dict[str, dict], nouveaux: list[dict]) -> int:
    """Ajoute les items au pool. Renvoie le nombre d'items réellement nouveaux."""
    ajoutes = 0
    for item in nouveaux:
        ancien = pool.get(item["id"])
        if ancien is None:
            pool[item["id"]] = item
            ajoutes += 1
            continue
        if PRIORITE_VIA.get(item.get("via"), 0) < PRIORITE_VIA.get(ancien.get("via"), 0):
            if item.get("radar_domaines"):
                ancien["radar_domaines"] = max(ancien.get("radar_domaines", 0), item["radar_domaines"])
            continue
        item["vu_le"] = ancien.get("vu_le", item["vu_le"])
        if item.get("date_estimee") and ancien.get("date"):
            # Sans date de publication, la date de première lecture fait foi.
            item["date"] = ancien["date"]
            item["date_estimee"] = ancien.get("date_estimee", True)
        if not item.get("rubrique_flux"):
            item["rubrique_flux"] = ancien.get("rubrique_flux", "")
        if item.get("via") == ancien.get("via") and len(ancien.get("resume", "")) > len(item.get("resume", "")):
            item["resume"] = ancien["resume"]
        if ancien.get("radar_domaines"):
            item["radar_domaines"] = max(ancien["radar_domaines"], item.get("radar_domaines", 0))
        pool[item["id"]] = item
    return ajoutes


def elaguer(pool: dict[str, dict], heures: float) -> int:
    limite = c.maintenant() - timedelta(hours=heures)
    perimes = [i for i, it in pool.items()
               if (c.lire_date(it.get("date")) or c.lire_date(it.get("vu_le")) or c.maintenant()) < limite]
    for i in perimes:
        del pool[i]
    return len(perimes)


def mettre_a_jour_sante(bilans: dict[str, dict]) -> list[str]:
    """Écrit etat/sante_flux.json et renvoie les flux en échec trois fois de suite."""
    precedent = c.lire_json(SANTE, {}) or {}
    maintenant = c.iso(c.maintenant())
    sante = {}
    for url, bilan in sorted(bilans.items()):
        avant = precedent.get(url, {})
        if bilan["erreur"] is None:
            bilan["derniere_reussite"] = maintenant
            bilan["echecs_consecutifs"] = 0
        else:
            bilan["derniere_reussite"] = avant.get("derniere_reussite")
            bilan["echecs_consecutifs"] = avant.get("echecs_consecutifs", 0) + 1
        sante[url] = bilan
    c.ecrire_json(SANTE, sante)
    return [url for url, b in sante.items() if b["echecs_consecutifs"] >= 3]


def collecte_annexe(nom: str, module: str, session, index, pool: dict) -> int:
    """GDELT et Wikipédia : une panne n'arrête jamais la collecte."""
    try:
        items = importlib.import_module(module).collecter(session, index, pool)
    except Exception:
        log.exception("%s en échec : la collecte continue sans lui", nom)
        return 0
    ajoutes = fusionner(pool, items)
    log.info("%s : %d items lus, %d nouveaux", nom, len(items), ajoutes)
    return ajoutes


def bilan_pool(pool: dict[str, dict]) -> dict:
    """Contrôle de l'étape 1 : volume, répartition, doublons."""
    urls = Counter(it["url"] for it in pool.values())
    titres = Counter((it["groupe"], " ".join(c.mots_normalises(it["titre"]))) for it in pool.values())
    memes_titres = [(g, t) for (g, t), n in titres.items() if n > 1]
    par_via = Counter(it.get("via") for it in pool.values())
    par_source = Counter(it["source"] for it in pool.values())
    log.info("Pool : %d items (%s)", len(pool), ", ".join(f"{n} {v}" for v, n in par_via.most_common()))
    log.info("Doublons d'URL : %d. Même titre sous deux URL dans un même groupe : %d",
             sum(1 for n in urls.values() if n > 1), len(memes_titres))
    for groupe, titre in memes_titres[:5]:
        log.info("  %s : %s", groupe, titre[:100])
    log.info("Sources les plus fournies : %s", ", ".join(f"{s} ({n})" for s, n in par_source.most_common(12)))
    return {"items": len(pool), "memes_titres": len(memes_titres), "par_via": dict(par_via)}


def collecter(avec_gdelt: bool = True, avec_wikipedia: bool = True) -> dict:
    reglages = c.parametres()["collecte"]
    conf = c.charger_yaml("sources.yaml")
    index = c.index_sources()
    session = c.session_http()
    pool = c.lire_pool()
    # Sans pool (premier lancement, état perdu), on ignore les validateurs HTTP :
    # un « 304 non modifié » ne rendrait aucune entrée.
    cache = (c.lire_json(CACHE_HTTP, {}) or {}) if pool else {}
    vu_le = c.maintenant()

    taches = [(s, f) for s in conf.get("sources", []) if s.get("actif", True)
              for f in s.get("flux", []) if f.get("actif", True)]
    log.info("Lecture de %d flux RSS (%d sources)", len(taches), len({s["nom"] for s, _ in taches}))
    lus, bilans = [], {}
    with ThreadPoolExecutor(max_workers=reglages["telechargements_simultanes"]) as executeur:
        futurs = {executeur.submit(lire_flux, session, s, f, cache, reglages, index, vu_le): f["url"]
                  for s, f in taches}
        for futur in as_completed(futurs):
            url = futurs[futur]
            items, bilan, validateurs = futur.result()
            lus.extend(items)
            bilans[url] = bilan
            if validateurs:
                cache[url] = validateurs
    stats = {"flux": len(taches), "entrees_rss": len(lus), "nouveaux_rss": fusionner(pool, lus)}
    log.info("RSS : %d entrées récentes lues, %d nouvelles", len(lus), stats["nouveaux_rss"])

    params = c.parametres()
    if avec_gdelt and params.get("gdelt", {}).get("actif", True):
        stats["nouveaux_gdelt"] = collecte_annexe("GDELT", "radar_gdelt", session, index, pool)
    if avec_wikipedia and params.get("wikipedia", {}).get("actif", True):
        stats["nouveaux_wikipedia"] = collecte_annexe("Wikipédia", "portail_wikipedia", session, index, pool)

    stats["retires"] = elaguer(pool, reglages["fenetre_pool_heures"])
    c.ecrire_pool(pool)
    c.ecrire_json(CACHE_HTTP, cache)
    en_panne = mettre_a_jour_sante(bilans)
    if en_panne:
        log.warning("%d flux en échec depuis trois collectes : %s", len(en_panne), ", ".join(en_panne[:6]))
    stats["flux_en_erreur"] = sum(1 for b in bilans.values() if b["erreur"])
    stats.update(bilan_pool(pool))
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Collecte des flux RSS, du radar GDELT et du portail Wikipédia.")
    parser.add_argument("--rss-seulement", action="store_true", help="ne lit ni GDELT ni Wikipédia")
    parser.add_argument("--sans-gdelt", action="store_true")
    parser.add_argument("--sans-wikipedia", action="store_true")
    parser.add_argument("-v", "--verbeux", action="store_true")
    args = parser.parse_args()
    c.demarrer(args.verbeux)
    collecter(avec_gdelt=not (args.rss_seulement or args.sans_gdelt),
              avec_wikipedia=not (args.rss_seulement or args.sans_wikipedia))


if __name__ == "__main__":
    main()
