import { useFocusEffect } from "expo-router";
import { useSQLiteContext } from "expo-sqlite";
import { useCallback, useState } from "react";
import { FlatList, StyleSheet, Text } from "react-native";

import CarteArticle from "../../components/CarteArticle";
import { listerFavoris } from "../../lib/base";
import { usePalette } from "../../lib/theme";
import type { ArticleDate } from "../../lib/types";

export default function Favoris() {
  const db = useSQLiteContext();
  const p = usePalette();
  const [favoris, setFavoris] = useState<ArticleDate[]>([]);

  useFocusEffect(
    useCallback(() => {
      listerFavoris(db).then(setFavoris);
    }, [db]),
  );

  return (
    <FlatList
      style={{ backgroundColor: p.fond }}
      data={favoris}
      keyExtractor={(a) => a.id}
      renderItem={({ item }) => <CarteArticle article={item} date={item.date} />}
      ListEmptyComponent={
        <Text style={[styles.vide, { color: p.secondaire }]}>
          Aucun favori. Touche « Enregistrer » dans un article pour le garder ici, même au-delà de 30 jours.
        </Text>
      }
      contentContainerStyle={styles.contenu}
    />
  );
}

const styles = StyleSheet.create({
  vide: { padding: 16, fontSize: 15, lineHeight: 22 },
  contenu: { paddingBottom: 120 },
});
