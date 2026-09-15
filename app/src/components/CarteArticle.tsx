import { router } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";

import Pastille from "./Pastille";
import { dateCourte } from "../lib/dates";
import { ANGLAIS, contenu } from "../lib/langue";
import { useReglages } from "../lib/reglages";
import { LIBELLES_FORMAT, SERIF, usePalette } from "../lib/theme";
import type { Article } from "../lib/types";

export default function CarteArticle({ article, date }: { article: Article; date?: string }) {
  const p = usePalette();
  const { reglages } = useReglages();
  const k = reglages.taillePolice;
  const t = contenu(article, reglages.langue);
  const en = t.langue === "en";
  const details = [
    (en ? ANGLAIS.formats : LIBELLES_FORMAT)[article.format] ?? "",
    article.suite_de ? (en ? "Follow-up" : "Suite") : "",
    date ? dateCourte(date) : "",
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Pressable
      onPress={() => router.push(`/article/${encodeURIComponent(article.id)}`)}
      style={({ pressed }) => [styles.carte, { borderColor: p.filet, backgroundColor: pressed ? p.accentDoux : "transparent" }]}
    >
      <View style={styles.entete}>
        <Pastille niveau={article.niveau_de_confiance} langue={t.langue} />
        <Text style={[styles.details, { color: p.secondaire }]}>{details}</Text>
      </View>
      <Text style={[styles.titre, { color: p.texte, fontFamily: SERIF, fontSize: 19 * k, lineHeight: 25 * k }]}>
        {t.titre}
      </Text>
      {t.chapeau ? (
        <Text numberOfLines={3} style={{ color: p.secondaire, fontSize: 15 * k, lineHeight: 21 * k }}>
          {t.chapeau}
        </Text>
      ) : null}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  carte: { paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: StyleSheet.hairlineWidth },
  entete: { flexDirection: "row", alignItems: "center", gap: 8, marginBottom: 6 },
  details: { fontSize: 12, textTransform: "uppercase", letterSpacing: 0.4 },
  titre: { fontWeight: "700", marginBottom: 6 },
});
