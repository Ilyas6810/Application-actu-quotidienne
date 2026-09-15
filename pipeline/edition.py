"""Édition du matin : collecte, regroupement, sélection, rédaction, contrôle, traduction, publication.

GitHub Actions le lance à 00:30 UTC (04:30 à La Réunion). Les articles sont rédigés
par ordre d'importance (À la une d'abord) jusqu'à l'heure limite : si un quota tombe
ou si le temps manque, l'édition sort incomplète, mais avec l'essentiel.

Usage :
    python edition.py                         # édition complète, en local, sans commit
    python edition.py --sans-collecte         # réutilise le pool existant
    python edition.py --factice --limite 5    # test de la mécanique sans clé
    python edition.py --commit --heure-limite 05:45 --notifier-a 06:00   # GitHub Actions
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections import Counter
from datetime import date, datetime

import cluster
import collecte
import communs as c
import notifier
import publie
import redaction
import traduction
from llm import Cascade

log = logging.getLogger("edition")

RAPPORT = c.ETAT / "rapport_edition.md"


def heure_locale(jour: date, hhmm: str) -> datetime:
    heures, minutes = (int(x) for x in hhmm.split(":"))
    return datetime(jour.year, jour.month, jour.day, heures, minutes, tzinfo=c.fuseau())


def notifier_titres(edition: dict, moment: datetime) -> None:
    """Notification push avec les trois premiers titres, envoyée à l'heure dite."""
    if not notifier.configure():
        log.info("EXPO_PUSH_TOKEN absent : la notification locale de l'application prend le relais")
        return
    attente = (moment - c.maintenant()).total_seconds()
    if 0 < attente <= 3 * 3600:
        log.info("Notification prévue à %s, dans %.0f min", moment.strftime("%H:%M"), attente / 60)
        time.sleep(attente)
    par_id = {a["id"]: a for a in edition["articles"]}
    titres = [par_id[i]["titre"] for i in edition["une"][:3] if i in par_id] or [a["titre"] for a in edition["articles"][:3]]
    notifier.envoyer(f"L'édition du {c.date_longue(date.fromisoformat(edition['date']))}",
                     "\n".join(f"• {t}" for t in titres), {"type": "edition", "date": edition["date"]}, canal="edition")


def ecrire_rapport(jour: date, debut: datetime, sujets: list[dict], articles: list[dict], rejets: list[dict],
                   cascade: Cascade) -> None:
    rubriques = c.parametres()["edition"]["rubriques"]
    par_rubrique = Counter(a["rubrique"] for a in articles)
    par_format = Counter(a["format"] for a in articles)
    duree = (c.maintenant() - debut).total_seconds() / 60
    lignes = [
        f"# Édition du {c.date_longue(jour)}", "",
        f"Durée : {duree:.0f} min. Sujets retenus : {len(sujets)}. Articles publiés : {len(articles)}. "
        f"Écartés : {len(rejets)}. Traduits en anglais : {sum(1 for a in articles if a.get('en'))}.", "",
        "## Articles par rubrique", "",
    ]
    lignes += [f"- {c.NOMS_RUBRIQUES[r]} : {par_rubrique.get(r, 0)} (plafond {conf['quota']})" for r, conf in rubriques.items()]
    lignes += ["", "Formats : " + ", ".join(f"{f} {n}" for f, n in par_format.most_common()), "", "## Modèles", ""]
    for b in cascade.bilan():
        etat = "pas de clé" if not b["cle"] else (f"écarté : {b['ecarte']}" if b["ecarte"] else "disponible")
        lignes.append(f"- {b['nom']} ({b['modele']}) : {b['appels']} appels, {b['echecs']} échecs, "
                      f"{b['jetons']} jetons, {etat}")
    avertis = [a for a in articles if a.get("avertissements")]
    if avertis:
        lignes += ["", "## Avertissements", ""] + [f"- {a['titre']} : {', '.join(a['avertissements'])}" for a in avertis]
    if rejets:
        lignes += ["", "## Sujets écartés", ""]
        lignes += [f"- [{c.NOMS_RUBRIQUES.get(r['rubrique'], r['rubrique'])}] {r['titre']} : {r['raison']}" for r in rejets]
    RAPPORT.write_text("\n".join(lignes) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Produit l'édition du jour.")
    parser.add_argument("--sans-collecte", action="store_true", help="réutilise le pool existant")
    parser.add_argument("--factice", action="store_true", help="faux modèle, pour tester sans clé")
    parser.add_argument("--limite", type=int, help="nombre maximal d'articles (tests)")
    parser.add_argument("--heure-limite", help="HH:MM locale après laquelle on n'entame plus d'article")
    parser.add_argument("--commit", action="store_true", help="commit et push de docs/ (GitHub Actions)")
    parser.add_argument("--notifier-a", help="HH:MM locale d'envoi de la notification push des titres")
    parser.add_argument("-v", "--verbeux", action="store_true")
    args = parser.parse_args()
    c.demarrer(args.verbeux)

    debut = c.maintenant()
    jour = c.date_locale(debut)
    log.info("Édition du %s", c.date_longue(jour))
    if not args.sans_collecte:
        collecte.collecter()
    pool = c.lire_pool()
    clusters = cluster.construire(pool)
    cluster.enregistrer(clusters)
    cluster.rapport(clusters, pool)

    historique = redaction.Historique(jour, c.parametres()["edition"]["jours_suivi"])
    sujets = redaction.ordre_de_redaction(redaction.selectionner(clusters, pool, historique))
    if args.limite:
        sujets = sujets[: args.limite]
    limite = heure_locale(jour, args.heure_limite) if args.heure_limite else None
    cascade = Cascade.depuis_config(factice=args.factice)
    articles, rejets = redaction.rediger_serie(sujets, pool, cascade, jour, limite)
    # Traduction anglaise avec les quotas restants : un article non traduit reste lisible en français.
    if articles and cascade.disponible() and not (limite and c.maintenant() >= limite):
        traduction.traduire(articles, cascade)
    redaction.ecrire_brouillons(articles, rejets)
    ecrire_rapport(jour, debut, sujets, articles, rejets, cascade)
    if not articles:
        log.error("Aucun article rédigé : pas de publication (voir %s)", RAPPORT)
        sys.exit(1)
    edition = publie.publier(articles, jour.isoformat(), commit=args.commit)
    if args.notifier_a:
        notifier_titres(edition, heure_locale(jour, args.notifier_a))


if __name__ == "__main__":
    main()
