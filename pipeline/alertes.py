"""Alertes urgentes hors édition, au plus trois par jour.

Lancé après chaque collecte (toutes les 3 heures). Un sujet devient une alerte si au
moins trois sources indépendantes de niveau 1 en parlent depuis moins de trois heures,
avec un mot d'urgence dans les titres (cinq sources sans mot d'urgence). L'alerte est
un titre et deux phrases, écrits avec la charte et contrôlés comme un article, publiés
dans docs/alertes.json et envoyés au téléphone si EXPO_PUSH_TOKEN est défini.

Usage :
    python alertes.py --simulation   # liste les candidats, sans rédiger ni publier
    python alertes.py                # rédige et écrit docs/alertes.json
    python alertes.py --commit       # et pousse sur GitHub (GitHub Actions)
"""

from __future__ import annotations

import argparse
import logging
import re
from datetime import datetime, timedelta

import cluster
import communs as c
import controle
import notifier
import publie
import redaction
from llm import AucunFournisseur, Cascade

log = logging.getLogger("alertes")

FICHIER = c.DOCS / "alertes.json"
FORMAT_ALERTE = {"alerte": {"min": 20, "max": 90}}


def motif_urgence() -> re.Pattern:
    mots = [c.sans_accents(m.lower()) for m in c.parametres()["alertes"]["mots_urgence"]]
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(m) for m in sorted(mots, key=len, reverse=True)) + r")(?!\w)")


def detecter(clusters: list[dict], pool: dict, deja: list[dict], reference: datetime) -> list[dict]:
    reglages = c.parametres()["alertes"]
    urgence = motif_urgence()
    urls_deja = {u for a in deja for u in a.get("urls", [])}
    clusters_deja = {a.get("cluster") for a in deja}
    depuis = reference - timedelta(hours=reglages["fenetre_heures"])
    candidats = []
    for sujet in clusters:
        if not sujet["publiable"] or sujet["id"] in clusters_deja:
            continue
        items = [pool[i] for i in sujet["items"] if i in pool]
        if {it["url"] for it in items} & urls_deja:
            continue
        recents = [it for it in items if it.get("niveau") == 1 and (c.lire_date(it["date"]) or reference) >= depuis]
        sources = len(cluster.composantes_independantes(recents))
        if sources < reglages["sources_min"]:
            continue
        urgent = any(urgence.search(c.sans_accents(it["titre"].lower())) for it in recents)
        if not urgent and sources < reglages["sources_sans_mot_cle"]:
            continue
        candidats.append({**sujet, "sources_recentes": sources, "urgent": urgent})
    return sorted(candidats, key=lambda s: (s["sources_recentes"], s["score"]), reverse=True)


def rediger_alerte(sujet: dict, pool: dict, cascade: Cascade, jour, numero: int) -> dict | None:
    items = redaction.items_contexte(sujet, pool, 8)
    textes = [f"{it['titre']}\n{it.get('resume', '')}" for it in items]
    contexte = {"textes": textes, "dates": redaction.dates_reference(items, jour), "officiel_competent": False}
    corrections = None
    for _ in (1, 2):
        message = redaction.consignes(sujet, items, "alerte", jour, corrections, formats=FORMAT_ALERTE)
        reponse = cascade.completer(redaction.CHARTE, message, max_tokens=redaction.JETONS["alerte"])
        if "ARTICLE_IMPOSSIBLE" in reponse.texte[:300]:
            return None
        try:
            article = redaction.normaliser(redaction.extraire_json(reponse.texte), items)
        except ValueError:
            corrections = ["La réponse doit être un unique objet JSON valide."]
            continue
        verdict = controle.verifier(article, contexte, "alerte", formats=FORMAT_ALERTE,
                                    champs_requis=("titre", "chapeau"))
        if verdict.ok:
            return {
                "id": f"{jour.isoformat()}-alerte-{numero:02d}",
                "date": jour.isoformat(),
                "publiee_a": c.iso(c.maintenant()),
                "titre": article["titre"],
                "texte": article["chapeau"],
                "sources": article["sources"],
                "cluster": sujet["id"],
                "urls": sorted({pool[i]["url"] for i in sujet["items"] if i in pool}),
            }
        corrections = verdict.erreurs
        log.info("Alerte refusée (%s) : %s", sujet["titre"][:60], "; ".join(verdict.erreurs)[:200])
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Détecte et publie les alertes urgentes.")
    parser.add_argument("--simulation", action="store_true", help="liste les candidats sans rien publier")
    parser.add_argument("--commit", action="store_true", help="commit et push de docs/alertes.json")
    parser.add_argument("--factice", action="store_true", help="faux modèle, pour tester sans clé")
    parser.add_argument("-v", "--verbeux", action="store_true")
    args = parser.parse_args()
    c.demarrer(args.verbeux)
    reglages = c.parametres()["alertes"]
    if not reglages.get("actif", True):
        return
    reference = c.maintenant()
    jour = c.date_locale(reference)
    donnees = c.lire_json(FICHIER, {}) or {}
    deja = [a for a in donnees.get("alertes", []) if a.get("date", "") >= (jour - timedelta(days=7)).isoformat()]
    places = reglages["plafond_jour"] - sum(1 for a in deja if a.get("date") == jour.isoformat())
    if places <= 0:
        log.info("Plafond de %d alertes atteint aujourd'hui", reglages["plafond_jour"])
        return
    pool = c.lire_pool()
    # Pas d'alerte sur un sujet que l'édition du matin a déjà traité.
    edition = c.lire_json(c.EDITIONS / f"{jour.isoformat()}.json", {}) or {}
    urls_edition = {c.url_canonique(s["url"]) for a in edition.get("articles", []) for s in a.get("sources", [])}
    candidats = [s for s in detecter(cluster.charger(), pool, deja, reference)
                 if not {pool[i]["url"] for i in s["items"] if i in pool} & urls_edition]
    if not candidats:
        log.info("Aucun sujet ne justifie une alerte")
        return
    if args.simulation:
        for s in candidats:
            print(f"{s['sources_recentes']} sources récentes, urgent={s['urgent']} : {s['titre']}")
        return
    cascade = Cascade.depuis_config(factice=args.factice)
    nouvelles = []
    for sujet in candidats[:places]:
        numero = reglages["plafond_jour"] - places + len(nouvelles) + 1
        try:
            alerte = rediger_alerte(sujet, pool, cascade, jour, numero)
        except AucunFournisseur:
            log.error("Aucun modèle disponible pour rédiger l'alerte")
            break
        if alerte:
            nouvelles.append(alerte)
    if not nouvelles:
        return
    publie.preparer_docs()
    c.ecrire_json(FICHIER, {"maj": c.iso(c.maintenant()), "alertes": nouvelles + deja})
    if args.commit:
        publie.commit_git(f"Alerte : {nouvelles[0]['titre']}", ["docs/alertes.json"])
    for alerte in nouvelles:
        notifier.envoyer(alerte["titre"], alerte["texte"], {"type": "alerte", "id": alerte["id"]}, canal="alertes")


if __name__ == "__main__":
    main()
