import { StyleSheet, Text, View } from "react-native";

import { ANGLAIS, type Langue } from "../lib/langue";
import { LIBELLES_CONFIANCE, couleurConfiance, usePalette } from "../lib/theme";
import type { NiveauConfiance } from "../lib/types";

export default function Pastille({
  niveau,
  avecLibelle = false,
  langue = "fr",
}: {
  niveau: NiveauConfiance;
  avecLibelle?: boolean;
  langue?: Langue;
}) {
  const p = usePalette();
  const couleur = couleurConfiance(p, niveau);
  const libelles = langue === "en" ? ANGLAIS.confiance : LIBELLES_CONFIANCE;
  const libelle = libelles[niveau] ?? libelles.partiel;
  return (
    <View
      style={styles.ligne}
      accessibilityLabel={langue === "en" ? `Confidence level: ${libelle}` : `Niveau de confiance : ${libelle}`}
    >
      <View style={[styles.point, { backgroundColor: couleur }]} />
      {avecLibelle ? <Text style={[styles.libelle, { color: couleur }]}>{libelle}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  ligne: { flexDirection: "row", alignItems: "center", gap: 6 },
  point: { width: 8, height: 8, borderRadius: 4 },
  libelle: { fontSize: 13, fontWeight: "600" },
});
