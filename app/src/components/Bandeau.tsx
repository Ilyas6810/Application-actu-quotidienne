import { StyleSheet, Text, View } from "react-native";

import { usePalette } from "../lib/theme";

type Genre = "info" | "attention" | "alerte";

export default function Bandeau({ genre = "info", titre, texte }: { genre?: Genre; titre?: string; texte: string }) {
  const p = usePalette();
  const couleur = genre === "alerte" ? p.conteste : genre === "attention" ? p.partiel : p.secondaire;
  return (
    <View style={[styles.bandeau, { borderLeftColor: couleur, backgroundColor: p.surface }]}>
      {titre ? <Text style={[styles.titre, { color: couleur }]}>{titre}</Text> : null}
      <Text style={[styles.texte, { color: p.texte }]}>{texte}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  bandeau: { marginHorizontal: 16, marginBottom: 10, padding: 12, borderLeftWidth: 3, borderRadius: 4 },
  titre: { fontSize: 13, fontWeight: "700", marginBottom: 4, textTransform: "uppercase", letterSpacing: 0.5 },
  texte: { fontSize: 14, lineHeight: 20 },
});
