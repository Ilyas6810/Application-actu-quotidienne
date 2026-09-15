import * as Clipboard from "expo-clipboard";
import Constants from "expo-constants";
import * as Speech from "expo-speech";
import { useSQLiteContext } from "expo-sqlite";
import { useState, type ReactNode } from "react";
import { Alert, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from "react-native";

import { effacerEditions } from "../../lib/base";
import { chargerDemonstration } from "../../lib/demo";
import { VOIX, type Langue } from "../../lib/langue";
import { jetonPush } from "../../lib/notifications";
import { useReglages, type ModeNotification } from "../../lib/reglages";
import { adresseValide, lireIndex, synchroniser } from "../../lib/synchro";
import { usePalette } from "../../lib/theme";
import { RUBRIQUES } from "../../lib/types";

function decalerHeure(heure: string, minutes: number): string {
  const [h, m] = heure.split(":").map(Number);
  const total = (((h * 60 + m + minutes) % 1440) + 1440) % 1440;
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

function borner(valeur: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Math.round(valeur * 100) / 100));
}

const MODES: { valeur: ModeNotification; libelle: string }[] = [
  { valeur: "locale", libelle: "Locale" },
  { valeur: "push", libelle: "Push" },
  { valeur: "aucune", libelle: "Aucune" },
];

const LANGUES: { valeur: Langue; libelle: string }[] = [
  { valeur: "fr", libelle: "Français" },
  { valeur: "en", libelle: "English" },
];

export default function PageReglages() {
  const db = useSQLiteContext();
  const p = usePalette();
  const { reglages, modifier } = useReglages();
  const [url, setUrl] = useState(reglages.urlEditions);
  const [etatUrl, setEtatUrl] = useState<string | null>(null);
  const [jeton, setJeton] = useState<{ jeton?: string; erreur?: string } | null>(null);
  const [occupe, setOccupe] = useState(false);

  async function testerAdresse() {
    const propre = url.trim();
    if (!adresseValide(propre)) {
      setEtatUrl("Adresse invalide : elle commence par https:// et ne contient plus « UTILISATEUR ».");
      return;
    }
    setEtatUrl("Test en cours…");
    try {
      const index = await lireIndex(propre);
      await modifier({ urlEditions: propre });
      setEtatUrl(`Adresse enregistrée : ${index.editions?.length ?? 0} édition(s) en ligne.`);
    } catch (e) {
      setEtatUrl(`Échec : ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function toutRetelecharger() {
    setOccupe(true);
    await effacerEditions(db);
    const resultat = await synchroniser(db, reglages.urlEditions);
    setOccupe(false);
    Alert.alert("Téléchargement", resultat.ok ? `${resultat.nouvelles} édition(s) téléchargée(s).` : `Échec : ${resultat.erreur}`);
  }

  const bouton = (libelle: string, action: () => void, desactive = false) => (
    <Pressable onPress={action} disabled={desactive} style={[styles.bouton, { borderColor: p.accent, opacity: desactive ? 0.5 : 1 }]}>
      <Text style={[styles.texteBouton, { color: p.accent }]}>{libelle}</Text>
    </Pressable>
  );

  const pas = (valeur: string, moins: () => void, plus: () => void) => (
    <View style={styles.pas}>
      <Pressable onPress={moins} hitSlop={8} style={[styles.boutonPas, { borderColor: p.filet }]}>
        <Text style={[styles.textePas, { color: p.accent }]}>−</Text>
      </Pressable>
      <Text style={[styles.valeurPas, { color: p.texte }]}>{valeur}</Text>
      <Pressable onPress={plus} hitSlop={8} style={[styles.boutonPas, { borderColor: p.filet }]}>
        <Text style={[styles.textePas, { color: p.accent }]}>+</Text>
      </Pressable>
    </View>
  );

  const choix = <T extends string>(options: { valeur: T; libelle: string }[], actuel: T, choisir: (valeur: T) => void) => (
    <View style={styles.choix}>
      {options.map((option) => {
        const actif = actuel === option.valeur;
        return (
          <Pressable
            key={option.valeur}
            onPress={() => choisir(option.valeur)}
            style={[styles.option, { borderColor: p.accent, backgroundColor: actif ? p.accent : "transparent" }]}
          >
            <Text style={{ color: actif ? "#FFFFFF" : p.accent, fontWeight: "600" }}>{option.libelle}</Text>
          </Pressable>
        );
      })}
    </View>
  );

  return (
    <ScrollView style={{ backgroundColor: p.fond }} contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <Section titre="Langue des articles">
        {choix(LANGUES, reglages.langue, (langue) => modifier({ langue }))}
        <Text style={[styles.aide, { color: p.secondaire }]}>
          En anglais, les articles s'affichent et se lisent dans leur traduction. Un article pas encore traduit reste
          en français.
        </Text>
      </Section>

      <Section titre="Notification du matin">
        {choix(MODES, reglages.notification, (notification) => modifier({ notification }))}
        {reglages.notification === "locale" ? (
          <Ligne libelle="Heure">
            {pas(
              reglages.heureNotification,
              () => modifier({ heureNotification: decalerHeure(reglages.heureNotification, -15) }),
              () => modifier({ heureNotification: decalerHeure(reglages.heureNotification, 15) }),
            )}
          </Ligne>
        ) : null}
        <Text style={[styles.aide, { color: p.secondaire }]}>
          {reglages.notification === "push"
            ? "Les titres du jour arrivent par notification push, envoyée à 6 h par le robot. Il faut l'APK, et ce jeton dans le secret GitHub EXPO_PUSH_TOKEN."
            : reglages.notification === "locale"
              ? "Une notification locale ne connaît pas les titres du jour : elle annonce seulement que l'édition est prête."
              : "Aucune notification du matin. Les alertes urgentes arrivent quand même si le jeton est configuré."}
        </Text>
        {bouton("Afficher mon jeton de notification", async () => setJeton(await jetonPush()))}
        {jeton?.jeton ? (
          <View style={[styles.jeton, { backgroundColor: p.surface, borderColor: p.filet }]}>
            <Text selectable style={{ color: p.texte, fontFamily: "monospace", fontSize: 13 }}>{jeton.jeton}</Text>
            {bouton("Copier", () => Clipboard.setStringAsync(jeton.jeton ?? ""))}
          </View>
        ) : jeton?.erreur ? (
          <Text style={[styles.aide, { color: p.conteste }]}>{jeton.erreur}</Text>
        ) : null}
      </Section>

      <Section titre="Onglets affichés">
        {RUBRIQUES.filter((r) => r.id !== "une").map((r) => {
          const visible = !reglages.rubriquesMasquees.includes(r.id);
          return (
            <Ligne key={r.id} libelle={r.nom}>
              <Switch
                value={visible}
                onValueChange={(afficher) =>
                  modifier({
                    rubriquesMasquees: afficher
                      ? reglages.rubriquesMasquees.filter((id) => id !== r.id)
                      : [...reglages.rubriquesMasquees, r.id],
                  })
                }
                trackColor={{ true: p.accent, false: p.filet }}
                thumbColor="#FFFFFF"
              />
            </Ligne>
          );
        })}
      </Section>

      <Section titre="Lecture">
        <Ligne libelle="Taille du texte">
          {pas(
            `${Math.round(reglages.taillePolice * 100)} %`,
            () => modifier({ taillePolice: borner(reglages.taillePolice - 0.05, 0.85, 1.4) }),
            () => modifier({ taillePolice: borner(reglages.taillePolice + 0.05, 0.85, 1.4) }),
          )}
        </Ligne>
        <Ligne libelle="Vitesse de la voix">
          {pas(
            `× ${reglages.vitesseLecture.toFixed(1)}`,
            () => modifier({ vitesseLecture: borner(reglages.vitesseLecture - 0.1, 0.6, 1.6) }),
            () => modifier({ vitesseLecture: borner(reglages.vitesseLecture + 0.1, 0.6, 1.6) }),
          )}
        </Ligne>
        {bouton("Tester la voix", () =>
          Speech.speak(
            reglages.langue === "en" ? "This is the voice and reading speed you chose." : "Voici la voix et la vitesse de lecture choisies.",
            { language: VOIX[reglages.langue], rate: reglages.vitesseLecture },
          ),
        )}
      </Section>

      <Section titre="Adresse des éditions">
        <TextInput
          value={url}
          onChangeText={setUrl}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          placeholder="https://utilisateur.github.io/actu-quotidienne"
          placeholderTextColor={p.secondaire}
          style={[styles.champ, { color: p.texte, borderColor: p.filet, backgroundColor: p.surface }]}
        />
        {bouton("Tester et enregistrer", testerAdresse)}
        {etatUrl ? <Text style={[styles.aide, { color: p.secondaire }]}>{etatUrl}</Text> : null}
      </Section>

      <Section titre="Données">
        {bouton(occupe ? "Téléchargement…" : "Tout retélécharger (30 jours)", toutRetelecharger, occupe)}
        {bouton("Charger l'édition de démonstration", async () => {
          await chargerDemonstration(db);
          Alert.alert("Démonstration", "L'édition de démonstration est dans l'onglet Édition.");
        })}
      </Section>

      <Section titre="À propos">
        <Text style={[styles.aide, { color: p.secondaire }]}>
          Version {Constants.expoConfig?.version ?? "?"}. Les articles sont rédigés automatiquement à partir de sources
          vérifiées. La voix est celle du téléphone : elle reste robotique, et elle n'a pas de commandes sur l'écran
          verrouillé. L'écran reste allumé pendant l'écoute pour ne pas l'interrompre.
        </Text>
      </Section>
    </ScrollView>
  );
}

function Section({ titre, children }: { titre: string; children: ReactNode }) {
  const p = usePalette();
  return (
    <View style={styles.section}>
      <Text style={[styles.titreSection, { color: p.accent }]}>{titre}</Text>
      {children}
    </View>
  );
}

function Ligne({ libelle, children }: { libelle: string; children: ReactNode }) {
  const p = usePalette();
  return (
    <View style={[styles.ligne, { borderColor: p.filet }]}>
      <Text style={[styles.libelle, { color: p.texte }]}>{libelle}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: 16, paddingBottom: 120, gap: 8 },
  section: { marginBottom: 20, gap: 10 },
  titreSection: { fontSize: 13, fontWeight: "700", textTransform: "uppercase", letterSpacing: 0.6 },
  ligne: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingVertical: 8, borderBottomWidth: StyleSheet.hairlineWidth },
  libelle: { fontSize: 16 },
  aide: { fontSize: 14, lineHeight: 20 },
  choix: { flexDirection: "row", gap: 8 },
  option: { flex: 1, paddingVertical: 8, borderWidth: 1, borderRadius: 8, alignItems: "center" },
  pas: { flexDirection: "row", alignItems: "center", gap: 12 },
  boutonPas: { width: 36, height: 36, borderRadius: 18, borderWidth: 1, alignItems: "center", justifyContent: "center" },
  textePas: { fontSize: 20, fontWeight: "700" },
  valeurPas: { minWidth: 64, textAlign: "center", fontSize: 16, fontVariant: ["tabular-nums"] },
  bouton: { paddingVertical: 10, borderRadius: 8, borderWidth: 1, alignItems: "center" },
  texteBouton: { fontSize: 15, fontWeight: "600" },
  champ: { paddingHorizontal: 12, paddingVertical: 10, borderWidth: 1, borderRadius: 8, fontSize: 15 },
  jeton: { padding: 12, borderRadius: 8, borderWidth: 1, gap: 10 },
});
