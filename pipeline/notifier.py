"""Notifications push par le service gratuit d'Expo (alertes, titres de 6 heures).

Le jeton du téléphone (ExponentPushToken[...]) s'affiche dans l'écran Réglages de
l'application ; il se range dans le secret GitHub EXPO_PUSH_TOKEN. Sans jeton,
rien n'est envoyé : la notification locale de 6 heures de l'application suffit.
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger("notifier")

URL = "https://exp.host/--/api/v2/push/send"


def configure() -> bool:
    return bool(os.environ.get("EXPO_PUSH_TOKEN", "").strip())


def envoyer(titre: str, texte: str, donnees: dict | None = None, canal: str = "edition") -> bool:
    jeton = os.environ.get("EXPO_PUSH_TOKEN", "").strip()
    if not jeton:
        log.info("EXPO_PUSH_TOKEN absent : pas de notification")
        return False
    message = {"to": jeton, "title": titre, "body": texte, "data": donnees or {}, "sound": "default",
               "priority": "high", "channelId": canal}
    entetes = {"Accept": "application/json", "Content-Type": "application/json"}
    if os.environ.get("EXPO_ACCESS_TOKEN"):  # seulement si la « sécurité renforcée » est activée chez Expo
        entetes["Authorization"] = f"Bearer {os.environ['EXPO_ACCESS_TOKEN']}"
    try:
        reponse = requests.post(URL, json=message, headers=entetes, timeout=20)
        retour = reponse.json().get("data", {})
    except (requests.RequestException, ValueError) as e:
        log.warning("Notification non envoyée : %s", e)
        return False
    if isinstance(retour, list):
        retour = retour[0] if retour else {}
    if retour.get("status") != "ok":
        log.warning("Notification refusée par Expo : %s", retour)
        return False
    log.info("Notification envoyée : %s", titre)
    return True
