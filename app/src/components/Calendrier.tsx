// Calendrier d'un mois : les jours qui ont une édition sur le téléphone sont cliquables.

import { Pressable, StyleSheet, Text, View } from "react-native";

import { majuscule, nomMois, versTexte } from "../lib/dates";
import { usePalette } from "../lib/theme";

const INITIALES = ["L", "M", "M", "J", "V", "S", "D"];

interface Props {
  annee: number;
  mois: number;
  disponibles: Set<string>;
  onChoisir: (date: string) => void;
  onChanger: (decalage: number) => void;
}

export default function Calendrier({ annee, mois, disponibles, onChoisir, onChanger }: Props) {
  const p = usePalette();
  const decalage = (new Date(annee, mois, 1).getDay() + 6) % 7; // lundi en premier
  const jours = new Date(annee, mois + 1, 0).getDate();
  const cases: (number | null)[] = [
    ...Array<null>(decalage).fill(null),
    ...Array.from({ length: jours }, (_, i) => i + 1),
  ];
  while (cases.length % 7 !== 0) cases.push(null);
  const semaines = Array.from({ length: cases.length / 7 }, (_, i) => cases.slice(i * 7, i * 7 + 7));

  return (
    <View style={[styles.calendrier, { backgroundColor: p.surface, borderColor: p.filet }]}>
      <View style={styles.entete}>
        <Pressable onPress={() => onChanger(-1)} hitSlop={12} accessibilityLabel="Mois précédent">
          <Text style={[styles.fleche, { color: p.accent }]}>‹</Text>
        </Pressable>
        <Text style={[styles.mois, { color: p.texte }]}>{majuscule(nomMois(annee, mois))}</Text>
        <Pressable onPress={() => onChanger(1)} hitSlop={12} accessibilityLabel="Mois suivant">
          <Text style={[styles.fleche, { color: p.accent }]}>›</Text>
        </Pressable>
      </View>
      <View style={styles.semaine}>
        {INITIALES.map((initiale, i) => (
          <Text key={i} style={[styles.case, styles.initiale, { color: p.secondaire }]}>{initiale}</Text>
        ))}
      </View>
      {semaines.map((semaine, i) => (
        <View key={i} style={styles.semaine}>
          {semaine.map((jour, j) => {
            if (jour === null) return <View key={j} style={styles.case} />;
            const date = versTexte(new Date(annee, mois, jour));
            const disponible = disponibles.has(date);
            return (
              <Pressable
                key={j}
                disabled={!disponible}
                onPress={() => onChoisir(date)}
                style={[styles.case, disponible && { backgroundColor: p.accentDoux, borderRadius: 18 }]}
                accessibilityLabel={disponible ? `Édition du ${jour}` : undefined}
              >
                <Text style={[styles.jour, { color: disponible ? p.accent : p.secondaire, fontWeight: disponible ? "700" : "400" }]}>
                  {jour}
                </Text>
              </Pressable>
            );
          })}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  calendrier: { margin: 16, padding: 12, borderRadius: 8, borderWidth: StyleSheet.hairlineWidth },
  entete: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", marginBottom: 8 },
  fleche: { fontSize: 28, paddingHorizontal: 12 },
  mois: { fontSize: 17, fontWeight: "700" },
  semaine: { flexDirection: "row" },
  case: { flex: 1, height: 38, alignItems: "center", justifyContent: "center" },
  initiale: { fontSize: 12, textAlign: "center", lineHeight: 38 },
  jour: { fontSize: 15 },
});
