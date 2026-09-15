// Mini-lecteur flottant pendant la lecture audio.

import { Ionicons } from "@expo/vector-icons";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { contenu } from "../lib/langue";
import { useLecteur } from "../lib/lecteur";
import { usePalette } from "../lib/theme";

export default function BarreLecteur() {
  const { etat, suivant, arreter } = useLecteur();
  const insets = useSafeAreaInsets();
  const p = usePalette();
  if (!etat) return null;
  const encore = etat.position + 1 < etat.total;
  return (
    <View style={[styles.barre, { bottom: insets.bottom + 64, backgroundColor: p.texte }]}>
      <Ionicons name="volume-high" size={18} color={p.fond} />
      <Text numberOfLines={1} style={[styles.titre, { color: p.fond }]}>
        {contenu(etat.article, etat.langue).titre}
      </Text>
      {etat.total > 1 ? (
        <Text style={[styles.compte, { color: p.fond }]}>
          {etat.position + 1}/{etat.total}
        </Text>
      ) : null}
      {encore ? (
        <Pressable onPress={suivant} hitSlop={10} accessibilityLabel="Article suivant">
          <Ionicons name="play-skip-forward" size={20} color={p.fond} />
        </Pressable>
      ) : null}
      <Pressable onPress={arreter} hitSlop={10} accessibilityLabel="Arrêter la lecture">
        <Ionicons name="stop" size={20} color={p.fond} />
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  barre: {
    position: "absolute",
    left: 12,
    right: 12,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 24,
    elevation: 6,
  },
  titre: { flex: 1, fontSize: 14, fontWeight: "600" },
  compte: { fontSize: 13, opacity: 0.75 },
});
