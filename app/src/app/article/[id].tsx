import { Ionicons } from "@expo/vector-icons";
import { Stack, router, useLocalSearchParams } from "expo-router";
import { useSQLiteContext } from "expo-sqlite";
import { useEffect, useState, type ComponentProps } from "react";
import { ActivityIndicator, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import Pastille from "../../components/Pastille";
import { basculerFavori, chargerArticle, estFavori } from "../../lib/base";
import { dateLongue } from "../../lib/dates";
import { ANGLAIS, contenu, dateLongueAnglais, type Langue } from "../../lib/langue";
import { useLecteur } from "../../lib/lecteur";
import { useReglages } from "../../lib/reglages";
import { EXPLICATIONS_CONFIANCE, LIBELLES_CONFIANCE, LIBELLES_FORMAT, SERIF, usePalette } from "../../lib/theme";
import { nomRubrique, type ArticleDate } from "../../lib/types";

export default function PageArticle() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const db = useSQLiteContext();
  const p = usePalette();
  const lecteur = useLecteur();
  const { reglages } = useReglages();
  const k = reglages.taillePolice;
  const [article, setArticle] = useState<ArticleDate | null | undefined>(undefined);
  const [precedent, setPrecedent] = useState<ArticleDate | null>(null);
  const [favori, setFavori] = useState(false);
  // Langue de la page : celle des réglages, que le bouton English / Français change pour cet article.
  const [langue, setLangue] = useState<Langue>(reglages.langue);

  useEffect(() => {
    let actif = true;
    (async () => {
      const lu = await chargerArticle(db, String(id));
      if (!actif) return;
      setArticle(lu);
      if (lu) {
        setFavori(await estFavori(db, lu.id));
        setPrecedent(lu.suite_de ? await chargerArticle(db, lu.suite_de) : null);
      }
    })();
    return () => {
      actif = false;
    };
  }, [db, id]);

  if (article === undefined) {
    return (
      <View style={[styles.centre, { backgroundColor: p.fond }]}>
        <ActivityIndicator color={p.accent} />
      </View>
    );
  }
  if (article === null) {
    return (
      <View style={[styles.centre, { backgroundColor: p.fond }]}>
        <Text style={{ color: p.secondaire, padding: 24 }}>Article introuvable : il a sans doute plus de 30 jours.</Text>
      </View>
    );
  }

  const t = contenu(article, langue);
  const en = t.langue === "en";
  const paragraphes = t.corps.split(/\n{2,}/).filter((bloc) => bloc.trim());
  const niveau = article.niveau_de_confiance;
  const format = (en ? ANGLAIS.formats : LIBELLES_FORMAT)[article.format] ?? "";

  return (
    <>
      <Stack.Screen options={{ title: nomRubrique(article.rubrique) }} />
      <ScrollView style={{ backgroundColor: p.fond }} contentContainerStyle={styles.page}>
        <View style={styles.meta}>
          <Pastille niveau={niveau} avecLibelle langue={t.langue} />
          <Text style={[styles.details, { color: p.secondaire }]}>
            {format} · {en ? dateLongueAnglais(article.date) : dateLongue(article.date)}
          </Text>
        </View>
        <Text style={[styles.titre, { color: p.texte, fontFamily: SERIF, fontSize: 26 * k, lineHeight: 33 * k }]}>
          {t.titre}
        </Text>
        <Text style={[styles.chapeau, { color: p.texte, fontSize: 17 * k, lineHeight: 25 * k }]}>{t.chapeau}</Text>
        <View style={styles.actions}>
          <Action
            icone="volume-high-outline"
            libelle={en ? ANGLAIS.ecouter : "Écouter"}
            onPress={() => lecteur.lire([article], 0, t.langue)}
          />
          <Action
            icone={favori ? "bookmark" : "bookmark-outline"}
            libelle={favori ? (en ? ANGLAIS.enregistre : "Enregistré") : en ? ANGLAIS.enregistrer : "Enregistrer"}
            onPress={async () => setFavori(await basculerFavori(db, article))}
          />
          {article.en ? (
            <Action icone="language-outline" libelle={en ? "Français" : "English"} onPress={() => setLangue(en ? "fr" : "en")} />
          ) : null}
        </View>
        {langue === "en" && !article.en ? (
          <Text style={[styles.note, styles.sansTraduction, { color: p.secondaire }]}>
            English translation not available yet for this article.
          </Text>
        ) : null}
        {paragraphes.map((bloc, i) =>
          bloc.startsWith("## ") ? (
            <Text key={i} style={[styles.intertitre, { color: p.texte, fontFamily: SERIF, fontSize: 19 * k, lineHeight: 25 * k }]}>
              {bloc.slice(3)}
            </Text>
          ) : (
            <Text key={i} style={[styles.paragraphe, { color: p.texte, fontSize: 16.5 * k, lineHeight: 26 * k }]}>
              {bloc}
            </Text>
          ),
        )}
        {article.suite_de ? (
          precedent ? (
            <Pressable
              onPress={() => router.push(`/article/${encodeURIComponent(precedent.id)}`)}
              style={[styles.suite, { borderColor: p.filet, backgroundColor: p.surface }]}
            >
              <Text style={[styles.libelleSuite, { color: p.secondaire }]}>
                {en ? `${ANGLAIS.precedent} · ${dateLongueAnglais(precedent.date)}` : `Épisode précédent · ${dateLongue(precedent.date)}`}
              </Text>
              <Text style={[styles.titreSuite, { color: p.accent, fontFamily: SERIF }]}>{contenu(precedent, t.langue).titre}</Text>
            </Pressable>
          ) : (
            <Text style={[styles.note, { color: p.secondaire }]}>
              {en ? ANGLAIS.precedentAbsent : "Cet article fait suite à un épisode qui n'est plus sur le téléphone."}
            </Text>
          )
        ) : null}
        <Text style={[styles.titreSources, { color: p.texte }]}>Sources</Text>
        {article.sources.map((source, i) => (
          <Pressable key={`${source.url}-${i}`} onPress={() => Linking.openURL(source.url)} hitSlop={6}>
            <Text style={[styles.source, { color: p.accent }]}>{source.nom}</Text>
          </Pressable>
        ))}
        <Text style={[styles.note, { color: p.secondaire }]}>
          {en
            ? `${ANGLAIS.note} ${ANGLAIS.confiance[niveau] ?? ""}: ${ANGLAIS.explications[niveau] ?? ""}.`
            : `Article rédigé automatiquement à partir de ces sources. ${LIBELLES_CONFIANCE[niveau] ?? ""} : ${EXPLICATIONS_CONFIANCE[niveau] ?? ""}.`}
        </Text>
      </ScrollView>
    </>
  );
}

function Action({ icone, libelle, onPress }: { icone: ComponentProps<typeof Ionicons>["name"]; libelle: string; onPress: () => void }) {
  const p = usePalette();
  return (
    <Pressable onPress={onPress} style={[styles.action, { borderColor: p.filet }]}>
      <Ionicons name={icone} size={18} color={p.accent} />
      <Text style={[styles.texteAction, { color: p.accent }]}>{libelle}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  centre: { flex: 1, alignItems: "center", justifyContent: "center" },
  page: { padding: 20, paddingBottom: 140 },
  meta: { flexDirection: "row", alignItems: "center", flexWrap: "wrap", gap: 10, marginBottom: 10 },
  details: { fontSize: 13 },
  titre: { fontWeight: "700", marginBottom: 12 },
  chapeau: { fontWeight: "600", marginBottom: 16 },
  actions: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginBottom: 20 },
  action: { flexDirection: "row", alignItems: "center", gap: 6, paddingVertical: 8, paddingHorizontal: 14, borderWidth: 1, borderRadius: 20 },
  texteAction: { fontSize: 14, fontWeight: "600" },
  sansTraduction: { marginTop: 0, marginBottom: 14 },
  intertitre: { fontWeight: "700", marginTop: 8, marginBottom: 10 },
  paragraphe: { marginBottom: 14 },
  suite: { marginTop: 8, marginBottom: 12, padding: 14, borderWidth: 1, borderRadius: 8, gap: 4 },
  libelleSuite: { fontSize: 12, textTransform: "uppercase" },
  titreSuite: { fontSize: 17, fontWeight: "700" },
  titreSources: { fontSize: 15, fontWeight: "700", marginTop: 16, marginBottom: 8 },
  source: { fontSize: 15, paddingVertical: 4, textDecorationLine: "underline" },
  note: { fontSize: 13, lineHeight: 19, marginTop: 16 },
});
