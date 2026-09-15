// Une édition : barre d'onglets (À la une puis les rubriques) et pages glissables.

import { Ionicons } from "@expo/vector-icons";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useWindowDimensions,
  type NativeScrollEvent,
  type NativeSyntheticEvent,
} from "react-native";

import CarteArticle from "./CarteArticle";
import { useLecteur } from "../lib/lecteur";
import { useReglages } from "../lib/reglages";
import { usePalette } from "../lib/theme";
import { RUBRIQUES, type Article, type Edition, type Rubrique } from "../lib/types";

interface Page {
  rubrique: Rubrique;
  articles: Article[];
}

interface Props {
  edition: Edition;
  entete?: ReactNode;
  actualisation?: boolean;
  onActualiser?: () => void;
}

export default function VueEdition({ edition, entete, actualisation = false, onActualiser }: Props) {
  const p = usePalette();
  const { width } = useWindowDimensions();
  const { reglages } = useReglages();
  const lecteur = useLecteur();
  const pager = useRef<FlatList<Page>>(null);
  const barre = useRef<ScrollView>(null);
  const positions = useRef<number[]>([]);
  const [actif, setActif] = useState(0);

  const pages = useMemo<Page[]>(() => {
    const parId = new Map(edition.articles.map((a) => [a.id, a] as const));
    const une = edition.une.map((id) => parId.get(id)).filter((a): a is Article => a !== undefined);
    const rubriques = (edition.rubriques.length ? edition.rubriques : RUBRIQUES).filter(
      (r) => r.id !== "une" && !reglages.rubriquesMasquees.includes(r.id),
    );
    const toutes: Page[] = [
      { rubrique: { id: "une", nom: "À la une" }, articles: une },
      ...rubriques.map((r) => ({ rubrique: r, articles: edition.articles.filter((a) => a.rubrique === r.id) })),
    ];
    return toutes.filter((page) => page.articles.length > 0);
  }, [edition, reglages.rubriquesMasquees]);

  useEffect(() => {
    if (actif >= pages.length) setActif(0);
  }, [pages.length, actif]);

  useEffect(() => {
    barre.current?.scrollTo({ x: Math.max(0, (positions.current[actif] ?? 0) - 24), animated: true });
  }, [actif]);

  function aller(index: number) {
    setActif(index);
    pager.current?.scrollToIndex({ index, animated: true });
  }

  function finDefilement(e: NativeSyntheticEvent<NativeScrollEvent>) {
    const index = Math.round(e.nativeEvent.contentOffset.x / width);
    if (index !== actif) setActif(index);
  }

  return (
    <View style={styles.conteneur}>
      {entete}
      <ScrollView
        ref={barre}
        horizontal
        showsHorizontalScrollIndicator={false}
        style={[styles.barre, { borderColor: p.filet }]}
        contentContainerStyle={styles.barreContenu}
      >
        {pages.map((page, i) => (
          <Pressable
            key={page.rubrique.id}
            onPress={() => aller(i)}
            onLayout={(e) => {
              positions.current[i] = e.nativeEvent.layout.x;
            }}
            style={[styles.onglet, { borderBottomColor: i === actif ? p.accent : "transparent" }]}
          >
            <Text style={[styles.texteOnglet, { color: i === actif ? p.accent : p.secondaire }]}>{page.rubrique.nom}</Text>
          </Pressable>
        ))}
      </ScrollView>
      <FlatList
        ref={pager}
        data={pages}
        horizontal
        pagingEnabled
        showsHorizontalScrollIndicator={false}
        keyExtractor={(page) => page.rubrique.id}
        getItemLayout={(_, index) => ({ length: width, offset: width * index, index })}
        onMomentumScrollEnd={finDefilement}
        renderItem={({ item: page }) => (
          <FlatList
            style={{ width }}
            data={page.articles}
            keyExtractor={(a) => a.id}
            renderItem={({ item }) => <CarteArticle article={item} />}
            ListHeaderComponent={
              <Pressable onPress={() => lecteur.lire(page.articles)} style={[styles.ecouter, { borderColor: p.filet }]}>
                <Ionicons name="volume-high-outline" size={18} color={p.accent} />
                <Text style={[styles.texteEcouter, { color: p.accent }]}>
                  Écouter {page.rubrique.id === "une" ? "la une" : "la rubrique"} ({page.articles.length})
                </Text>
              </Pressable>
            }
            contentContainerStyle={styles.liste}
            refreshControl={
              onActualiser ? (
                <RefreshControl refreshing={actualisation} onRefresh={onActualiser} colors={[p.accent]} tintColor={p.accent} />
              ) : undefined
            }
          />
        )}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  conteneur: { flex: 1 },
  barre: { flexGrow: 0, borderBottomWidth: StyleSheet.hairlineWidth },
  barreContenu: { paddingHorizontal: 10 },
  onglet: { paddingHorizontal: 10, paddingVertical: 12, borderBottomWidth: 2 },
  texteOnglet: { fontSize: 15, fontWeight: "600" },
  ecouter: {
    flexDirection: "row",
    alignItems: "center",
    alignSelf: "flex-start",
    gap: 8,
    marginHorizontal: 16,
    marginTop: 12,
    marginBottom: 4,
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderWidth: StyleSheet.hairlineWidth,
    borderRadius: 20,
  },
  texteEcouter: { fontSize: 14, fontWeight: "600" },
  liste: { paddingBottom: 140 },
});
