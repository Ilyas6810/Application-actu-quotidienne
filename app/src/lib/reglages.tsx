import Constants from "expo-constants";
import { useSQLiteContext } from "expo-sqlite";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import type { Langue } from "./langue";

export type ModeNotification = "locale" | "push" | "aucune";

export interface Reglages {
  heureNotification: string;
  notification: ModeNotification;
  rubriquesMasquees: string[];
  taillePolice: number;
  vitesseLecture: number;
  urlEditions: string;
  langue: Langue;
}

const extra = (Constants.expoConfig?.extra ?? {}) as { urlEditions?: string };

export const REGLAGES_DEFAUT: Reglages = {
  heureNotification: "06:00",
  notification: "locale",
  rubriquesMasquees: [],
  taillePolice: 1,
  vitesseLecture: 1,
  // EXPO_PUBLIC_URL_EDITIONS est fixée à l'export par bureau/preparer-web.js
  urlEditions: process.env.EXPO_PUBLIC_URL_EDITIONS || extra.urlEditions || "",
  langue: "fr",
};

interface ValeurReglages {
  reglages: Reglages;
  modifier: (changements: Partial<Reglages>) => Promise<void>;
}

const Contexte = createContext<ValeurReglages | null>(null);

export function FournisseurReglages({ children }: { children: ReactNode }) {
  const db = useSQLiteContext();
  const [reglages, setReglages] = useState<Reglages>(REGLAGES_DEFAUT);
  const [pret, setPret] = useState(false);

  useEffect(() => {
    let actif = true;
    db.getAllAsync<{ cle: string; valeur: string }>("SELECT cle, valeur FROM reglages").then((lignes) => {
      const lus: Record<string, unknown> = {};
      for (const ligne of lignes) {
        try {
          lus[ligne.cle] = JSON.parse(ligne.valeur);
        } catch {
          // valeur illisible : on garde celle par défaut
        }
      }
      if (actif) {
        setReglages({ ...REGLAGES_DEFAUT, ...(lus as Partial<Reglages>) });
        setPret(true);
      }
    });
    return () => {
      actif = false;
    };
  }, [db]);

  const modifier = useCallback(
    async (changements: Partial<Reglages>) => {
      setReglages((actuels) => ({ ...actuels, ...changements }));
      for (const [cle, valeur] of Object.entries(changements)) {
        await db.runAsync("INSERT OR REPLACE INTO reglages (cle, valeur) VALUES (?, ?)", cle, JSON.stringify(valeur));
      }
    },
    [db],
  );

  if (!pret) return null;
  return <Contexte.Provider value={{ reglages, modifier }}>{children}</Contexte.Provider>;
}

export function useReglages(): ValeurReglages {
  const valeur = useContext(Contexte);
  if (!valeur) throw new Error("useReglages doit être appelé sous FournisseurReglages");
  return valeur;
}
