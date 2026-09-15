import { Stack } from "expo-router";
import { SQLiteProvider } from "expo-sqlite";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";

import BarreLecteur from "../components/BarreLecteur";
import GestionNotifications from "../components/GestionNotifications";
import { migrer } from "../lib/base";
import { FournisseurLecteur } from "../lib/lecteur";
import { FournisseurReglages } from "../lib/reglages";
import { usePalette } from "../lib/theme";

export default function Racine() {
  const p = usePalette();
  return (
    <SafeAreaProvider>
      <SQLiteProvider databaseName="actu.db" onInit={migrer}>
        <FournisseurReglages>
          <FournisseurLecteur>
            <GestionNotifications />
            <StatusBar style="auto" />
            <Stack
              screenOptions={{
                headerStyle: { backgroundColor: p.fond },
                headerTintColor: p.texte,
                headerShadowVisible: false,
                contentStyle: { backgroundColor: p.fond },
              }}
            >
              <Stack.Screen name="(onglets)" options={{ headerShown: false }} />
              <Stack.Screen name="article/[id]" options={{ title: "" }} />
              <Stack.Screen name="edition/[date]" options={{ title: "Archives" }} />
            </Stack>
            <BarreLecteur />
          </FournisseurLecteur>
        </FournisseurReglages>
      </SQLiteProvider>
    </SafeAreaProvider>
  );
}
