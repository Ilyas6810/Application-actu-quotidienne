import { router, useFocusEffect } from "expo-router";
import { useSQLiteContext } from "expo-sqlite";
import { useCallback, useMemo, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text } from "react-native";

import Calendrier from "../../components/Calendrier";
import { editionsDisponibles } from "../../lib/base";
import { dateLongue, majuscule } from "../../lib/dates";
import { usePalette } from "../../lib/theme";

export default function Archives() {
  const db = useSQLiteContext();
  const p = usePalette();
  const [editions, setEditions] = useState<{ date: string; articles: number }[]>([]);
  const [mois, setMois] = useState(() => {
    const d = new Date();
    return { annee: d.getFullYear(), mois: d.getMonth() };
  });

  useFocusEffect(
    useCallback(() => {
      editionsDisponibles(db).then(setEditions);
    }, [db]),
  );

  const disponibles = useMemo(() => new Set(editions.map((e) => e.date)), [editions]);
  const ouvrir = (date: string) => router.push(`/edition/${date}`);
  const changer = (decalage: number) =>
    setMois(({ annee, mois: m }) => {
      const d = new Date(annee, m + decalage, 1);
      return { annee: d.getFullYear(), mois: d.getMonth() };
    });

  return (
    <FlatList
      style={{ backgroundColor: p.fond }}
      data={editions}
      keyExtractor={(e) => e.date}
      ListHeaderComponent={
        <Calendrier annee={mois.annee} mois={mois.mois} disponibles={disponibles} onChoisir={ouvrir} onChanger={changer} />
      }
      renderItem={({ item }) => (
        <Pressable
          onPress={() => ouvrir(item.date)}
          style={({ pressed }) => [styles.ligne, { borderColor: p.filet, backgroundColor: pressed ? p.accentDoux : "transparent" }]}
        >
          <Text style={[styles.date, { color: p.texte }]}>{majuscule(dateLongue(item.date))}</Text>
          <Text style={{ color: p.secondaire }}>{item.articles} articles</Text>
        </Pressable>
      )}
      ListEmptyComponent={<Text style={[styles.vide, { color: p.secondaire }]}>Aucune édition téléchargée pour l'instant.</Text>}
      contentContainerStyle={styles.contenu}
    />
  );
}

const styles = StyleSheet.create({
  ligne: { flexDirection: "row", justifyContent: "space-between", paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: StyleSheet.hairlineWidth },
  date: { fontSize: 16, fontWeight: "600" },
  vide: { padding: 16, fontSize: 15 },
  contenu: { paddingBottom: 120 },
});
