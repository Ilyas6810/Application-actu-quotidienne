import { Stack, useLocalSearchParams } from "expo-router";
import { useSQLiteContext } from "expo-sqlite";
import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import VueEdition from "../../components/VueEdition";
import { chargerEdition } from "../../lib/base";
import { dateLongue, majuscule } from "../../lib/dates";
import { usePalette } from "../../lib/theme";
import type { Edition } from "../../lib/types";

export default function EditionPassee() {
  const { date } = useLocalSearchParams<{ date: string }>();
  const db = useSQLiteContext();
  const p = usePalette();
  const [edition, setEdition] = useState<Edition | null | undefined>(undefined);

  useEffect(() => {
    chargerEdition(db, String(date)).then(setEdition);
  }, [db, date]);

  if (edition === undefined) {
    return (
      <View style={[styles.centre, { backgroundColor: p.fond }]}>
        <ActivityIndicator color={p.accent} />
      </View>
    );
  }
  if (edition === null) {
    return (
      <View style={[styles.centre, { backgroundColor: p.fond }]}>
        <Text style={{ color: p.secondaire }}>Cette édition n'est plus sur le téléphone.</Text>
      </View>
    );
  }
  return (
    <View style={[styles.page, { backgroundColor: p.fond }]}>
      <Stack.Screen options={{ title: majuscule(dateLongue(edition.date)) }} />
      <VueEdition edition={edition} />
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  centre: { flex: 1, alignItems: "center", justifyContent: "center" },
});
