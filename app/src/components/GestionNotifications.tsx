// Reprogramme la notification de 6 heures à chaque ouverture et à chaque changement
// de réglage, et ramène sur l'édition quand on touche une notification.

import * as Notifications from "expo-notifications";
import { router, useRootNavigationState } from "expo-router";
import { useEffect } from "react";
import { Platform } from "react-native";

import { programmerEdition } from "../lib/notifications";
import { useReglages } from "../lib/reglages";

export default function GestionNotifications() {
  // Le module de notifications n'existe pas dans un navigateur (aperçu web).
  return Platform.OS === "web" ? null : <GestionTelephone />;
}

function GestionTelephone() {
  const { reglages } = useReglages();
  const reponse = Notifications.useLastNotificationResponse();
  const navigation = useRootNavigationState();

  useEffect(() => {
    programmerEdition(reglages.heureNotification, reglages.notification === "locale").catch(() => undefined);
  }, [reglages.heureNotification, reglages.notification]);

  useEffect(() => {
    if (!navigation?.key || !reponse) return;
    if (reponse.actionIdentifier === Notifications.DEFAULT_ACTION_IDENTIFIER) router.navigate("/");
  }, [navigation?.key, reponse]);

  return null;
}
