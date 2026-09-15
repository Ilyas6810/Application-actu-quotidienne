// Recherche plein texte (SQLite FTS5) dans tout ce qui est téléchargé.

import { router } from "expo-router";
import { useSQLiteContext } from "expo-sqlite";
import { useEffect, useRef, useState } from "react";
import { FlatList, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { rechercher, type Resultat } from "../../lib/base";
import { dateCourte } from "../../lib/dates";
import { SERIF, usePalette } from "../../lib/theme";

export default function Recherche() {
  const db = useSQLiteContext();
  const p = usePalette();
  const [texte, setTexte] = useState("");
  const [resultats, setResultats] = useState<Resultat[]>([]);
  const [cherche, setCherche] = useState(false);
  const derniere = useRef(0); // ignore les réponses d'une frappe dépassée

  useEffect(() => {
    const numero = ++derniere.current;
    const minuterie = setTimeout(async () => {
      if (texte.trim().length < 2) {
        setResultats([]);
        setCherche(false);
        return;
      }
      const trouves = await rechercher(db, texte);
      if (numero === derniere.current) {
        setResultats(trouves);
        setCherche(true);
      }
    }, 250);
    return () => clearTimeout(minuterie);
  }, [db, texte]);

  return (
    <View style={[styles.page, { backgroundColor: p.fond }]}>
      <TextInput
        value={texte}
        onChangeText={setTexte}
        placeholder="Chercher dans les 30 derniers jours"
        placeholderTextColor={p.secondaire}
        style={[styles.champ, { color: p.texte, borderColor: p.filet, backgroundColor: p.surface }]}
        autoCorrect={false}
        returnKeyType="search"
        clearButtonMode="while-editing"
      />
      <FlatList
        data={resultats}
        keyExtractor={(r) => r.id}
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={styles.liste}
        renderItem={({ item }) => (
          <Pressable
            onPress={() => router.push(`/article/${encodeURIComponent(item.id)}`)}
            style={({ pressed }) => [styles.resultat, { borderColor: p.filet, backgroundColor: pressed ? p.accentDoux : "transparent" }]}
          >
            <Text style={[styles.date, { color: p.secondaire }]}>{dateCourte(item.date)}</Text>
            <Text style={[styles.titre, { color: p.texte, fontFamily: SERIF }]}>{item.titre}</Text>
            {item.extrait ? (
              <Text numberOfLines={2} style={{ color: p.secondaire, fontSize: 14, lineHeight: 20 }}>
                {item.extrait}
              </Text>
            ) : null}
          </Pressable>
        )}
        ListEmptyComponent={cherche ? <Text style={[styles.vide, { color: p.secondaire }]}>Aucun article ne correspond.</Text> : null}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1 },
  champ: { margin: 16, paddingHorizontal: 14, paddingVertical: 10, borderWidth: 1, borderRadius: 8, fontSize: 16 },
  liste: { paddingBottom: 120 },
  resultat: { paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth },
  date: { fontSize: 12, textTransform: "uppercase", marginBottom: 4 },
  titre: { fontSize: 17, fontWeight: "700", marginBottom: 4 },
  vide: { padding: 16, fontSize: 15 },
});
