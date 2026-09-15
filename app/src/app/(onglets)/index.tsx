// Édition du jour : l'édition déjà sur le téléphone s'affiche tout de suite (lecture
// hors ligne), puis l'application tente de télécharger la plus récente.

import { router, useFocusEffect } from "expo-router";
import { useSQLiteContext } from "expo-sqlite";
import { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import Bandeau from "../../components/Bandeau";
import VueEdition from "../../components/VueEdition";
import { alertesRecentes, chargerEdition, dateLaPlusRecente } from "../../lib/base";
import { aujourdhui, dateLongue, majuscule } from "../../lib/dates";
import { chargerDemonstration } from "../../lib/demo";
import { useReglages } from "../../lib/reglages";
import { synchroniser } from "../../lib/synchro";
import { SERIF, usePalette } from "../../lib/theme";
import type { Alerte, Edition } from "../../lib/types";

export default function EditionDuJour() {
  const db = useSQLiteContext();
  const { reglages } = useReglages();
  const p = usePalette();
  const [edition, setEdition] = useState<Edition | null>(null);
  const [alertes, setAlertes] = useState<Alerte[]>([]);
  const [chargement, setChargement] = useState(true);
  const [actualisation, setActualisation] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);

  const afficherLocal = useCallback(async () => {
    const date = await dateLaPlusRecente(db);
    setEdition(date ? await chargerEdition(db, date) : null);
    setAlertes(await alertesRecentes(db));
  }, [db]);

  const actualiser = useCallback(async () => {
    setActualisation(true);
    let premiere = true;
    const resultat = await synchroniser(db, reglages.urlEditions, () => {
      if (premiere) {
        premiere = false;
        afficherLocal(); // la plus récente s'affiche dès son arrivée, sans attendre les archives
      }
    });
    setErreur(resultat.ok ? null : (resultat.erreur ?? "erreur inconnue"));
    await afficherLocal();
    setActualisation(false);
  }, [db, reglages.urlEditions, afficherLocal]);

  useEffect(() => {
    afficherLocal().finally(() => {
      setChargement(false);
      actualiser();
    });
  }, [afficherLocal, actualiser]);

  // Retour sur l'onglet : l'édition affichée a pu changer (démonstration, retéléchargement depuis Réglages).
  useFocusEffect(
    useCallback(() => {
      if (!chargement) afficherLocal();
    }, [chargement, afficherLocal]),
  );

  if (chargement) {
    return (
      <View style={[styles.centre, { backgroundColor: p.fond }]}>
        <ActivityIndicator color={p.accent} />
      </View>
    );
  }

  if (!edition) {
    const etat = actualisation
      ? "Téléchargement en cours…"
      : erreur
        ? `Téléchargement impossible : ${erreur}.`
        : "La première édition n'est pas encore publiée.";
    return (
      <SafeAreaView style={[styles.vide, { backgroundColor: p.fond }]}>
        <Text style={[styles.titreVide, { color: p.texte, fontFamily: SERIF }]}>Aucune édition sur ce téléphone</Text>
        <Text style={[styles.texteVide, { color: p.secondaire }]}>{etat}</Text>
        <Pressable style={[styles.bouton, { backgroundColor: p.accent }]} onPress={actualiser} disabled={actualisation}>
          <Text style={styles.texteBouton}>Réessayer</Text>
        </Pressable>
        <Pressable
          style={[styles.boutonSecondaire, { borderColor: p.accent }]}
          onPress={async () => {
            await chargerDemonstration(db);
            await afficherLocal();
          }}
        >
          <Text style={[styles.texteBoutonSecondaire, { color: p.accent }]}>Voir une édition de démonstration</Text>
        </Pressable>
        <Pressable onPress={() => router.navigate("/reglages")} hitSlop={8}>
          <Text style={[styles.lien, { color: p.accent }]}>Régler l'adresse des éditions</Text>
        </Pressable>
      </SafeAreaView>
    );
  }

  const entete = (
    <View>
      <Text style={[styles.date, { color: p.texte, fontFamily: SERIF }]}>{majuscule(dateLongue(edition.date))}</Text>
      {edition.genere_a === "demonstration" ? (
        <Bandeau genre="attention" texte="Édition de démonstration : aucun de ces textes n'est une information." />
      ) : null}
      {erreur && !actualisation ? (
        <Bandeau genre="attention" texte={`Pas de mise à jour (${erreur}). Voici la dernière édition téléchargée.`} />
      ) : null}
      {edition.date !== aujourdhui() && !erreur && !actualisation ? (
        <Bandeau texte="L'édition du jour n'est pas encore arrivée. Voici la plus récente." />
      ) : null}
      {alertes.map((a) => (
        <Bandeau key={a.id} genre="alerte" titre="Alerte" texte={`${a.titre}. ${a.texte}`} />
      ))}
    </View>
  );

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: p.fond }} edges={["top"]}>
      <VueEdition edition={edition} entete={entete} actualisation={actualisation} onActualiser={actualiser} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  centre: { flex: 1, alignItems: "center", justifyContent: "center" },
  date: { fontSize: 24, fontWeight: "700", paddingHorizontal: 16, paddingTop: 8, paddingBottom: 12 },
  vide: { flex: 1, padding: 24, justifyContent: "center", gap: 14 },
  titreVide: { fontSize: 24, fontWeight: "700" },
  texteVide: { fontSize: 15, lineHeight: 22 },
  bouton: { paddingVertical: 12, borderRadius: 8, alignItems: "center" },
  texteBouton: { color: "#FFFFFF", fontSize: 16, fontWeight: "700" },
  boutonSecondaire: { paddingVertical: 12, borderRadius: 8, alignItems: "center", borderWidth: 1 },
  texteBoutonSecondaire: { fontSize: 16, fontWeight: "600" },
  lien: { fontSize: 15, textAlign: "center", textDecorationLine: "underline" },
});
