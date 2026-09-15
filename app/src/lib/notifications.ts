// Notification locale de 6 heures et jeton de notification push.
//
// Une notification locale se programme d'avance : elle ne peut pas contenir les titres
// du jour. Les titres arrivent par notification push, envoyée à 6 heures par le
// workflow GitHub quand le jeton du téléphone est rangé dans le secret EXPO_PUSH_TOKEN.
// Le push ne marche pas dans Expo Go sur Android (depuis le SDK 53) : il faut l'APK.

import Constants, { ExecutionEnvironment } from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { Platform } from "react-native";

const IDENTIFIANT_EDITION = "edition-du-matin";

if (Platform.OS !== "web") {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
}

/** Sur Android 13 et plus, les canaux doivent exister avant la demande d'autorisation. */
async function preparerCanaux(): Promise<void> {
  if (Platform.OS !== "android") return;
  await Notifications.setNotificationChannelAsync("edition", {
    name: "Édition du matin",
    importance: Notifications.AndroidImportance.DEFAULT,
  });
  await Notifications.setNotificationChannelAsync("alertes", {
    name: "Alertes",
    importance: Notifications.AndroidImportance.HIGH,
  });
}

export async function autoriser(): Promise<boolean> {
  await preparerCanaux();
  const actuelle = await Notifications.getPermissionsAsync();
  if (actuelle.granted) return true;
  return (await Notifications.requestPermissionsAsync()).granted;
}

/** Reprogramme la notification quotidienne (à chaque ouverture : pas de dérive). */
export async function programmerEdition(heure: string, active: boolean): Promise<void> {
  await Notifications.cancelScheduledNotificationAsync(IDENTIFIANT_EDITION).catch(() => undefined);
  if (!active || !(await autoriser())) return;
  const [heures, minutes] = heure.split(":").map(Number);
  await Notifications.scheduleNotificationAsync({
    identifier: IDENTIFIANT_EDITION,
    content: {
      title: "L'édition du jour est prête",
      body: "Ouvre l'application pour la lire, même sans connexion.",
      data: { type: "edition" },
    },
    trigger: {
      type: Notifications.SchedulableTriggerInputTypes.DAILY,
      hour: heures,
      minute: minutes,
      channelId: "edition",
    },
  });
}

export async function jetonPush(): Promise<{ jeton?: string; erreur?: string }> {
  if (!Device.isDevice) return { erreur: "Il faut un vrai téléphone." };
  if (Constants.executionEnvironment === ExecutionEnvironment.StoreClient) {
    return { erreur: "Les notifications push ne marchent pas dans Expo Go sur Android : installe l'APK." };
  }
  const projectId = Constants.expoConfig?.extra?.eas?.projectId ?? Constants.easConfig?.projectId;
  if (!projectId) return { erreur: "Projet EAS non configuré : lance « npx eas-cli init » dans le dossier app." };
  if (!(await autoriser())) return { erreur: "Les notifications sont refusées dans les réglages du téléphone." };
  try {
    return { jeton: (await Notifications.getExpoPushTokenAsync({ projectId })).data };
  } catch (e) {
    return { erreur: e instanceof Error ? e.message : String(e) };
  }
}
