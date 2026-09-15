import { Ionicons } from "@expo/vector-icons";
import { Tabs } from "expo-router";
import type { ComponentProps } from "react";

import { usePalette } from "../../lib/theme";

type NomIcone = ComponentProps<typeof Ionicons>["name"];

const ONGLETS: { nom: string; titre: string; icone: NomIcone }[] = [
  { nom: "index", titre: "Édition", icone: "newspaper-outline" },
  { nom: "archives", titre: "Archives", icone: "calendar-outline" },
  { nom: "recherche", titre: "Recherche", icone: "search-outline" },
  { nom: "favoris", titre: "Favoris", icone: "bookmark-outline" },
  { nom: "reglages", titre: "Réglages", icone: "settings-outline" },
];

export default function Onglets() {
  const p = usePalette();
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: p.fond },
        headerTintColor: p.texte,
        headerShadowVisible: false,
        tabBarActiveTintColor: p.accent,
        tabBarInactiveTintColor: p.secondaire,
        tabBarStyle: { backgroundColor: p.fond, borderTopColor: p.filet },
        sceneStyle: { backgroundColor: p.fond },
      }}
    >
      {ONGLETS.map((onglet) => (
        <Tabs.Screen
          key={onglet.nom}
          name={onglet.nom}
          options={{
            title: onglet.titre,
            headerShown: onglet.nom !== "index",
            tabBarIcon: ({ color, size }) => <Ionicons name={onglet.icone} color={color} size={size} />,
          }}
        />
      ))}
    </Tabs>
  );
}
