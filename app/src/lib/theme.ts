import { Platform, useColorScheme } from "react-native";

import type { Format, NiveauConfiance } from "./types";

export interface Palette {
  fond: string;
  surface: string;
  texte: string;
  secondaire: string;
  filet: string;
  accent: string;
  accentDoux: string;
  confirme: string;
  partiel: string;
  conteste: string;
}

const CLAIR: Palette = {
  fond: "#F7F5F0",
  surface: "#FFFFFF",
  texte: "#1A1A1A",
  secondaire: "#5E5A54",
  filet: "#E3DED4",
  accent: "#8C1C2B",
  accentDoux: "#F3E4E6",
  confirme: "#2F7D4F",
  partiel: "#A86B12",
  conteste: "#B3364A",
};

const SOMBRE: Palette = {
  fond: "#121212",
  surface: "#1D1C1A",
  texte: "#EDEAE4",
  secondaire: "#A8A29A",
  filet: "#302D29",
  accent: "#E0707E",
  accentDoux: "#3A2226",
  confirme: "#5FBF86",
  partiel: "#E3B25C",
  conteste: "#EE7A8C",
};

export function usePalette(): Palette {
  return useColorScheme() === "dark" ? SOMBRE : CLAIR;
}

/** Police à empattements pour les titres : Noto Serif sur Android. */
export const SERIF = Platform.select({ android: "serif", ios: "Georgia", default: undefined });

export const LIBELLES_CONFIANCE: Record<NiveauConfiance, string> = {
  confirme: "Confirmé",
  partiel: "Partiel",
  conteste: "Contesté",
};

export const EXPLICATIONS_CONFIANCE: Record<NiveauConfiance, string> = {
  confirme: "au moins trois sources indépendantes, ou une source officielle sur son propre domaine",
  partiel: "deux sources indépendantes concordent sur les faits centraux",
  conteste: "les sources divergent sur un point important",
};

export const LIBELLES_FORMAT: Record<Format, string> = {
  breve: "Brève",
  standard: "Article",
  fond: "Article de fond",
};

export function couleurConfiance(p: Palette, niveau: NiveauConfiance): string {
  if (niveau === "confirme") return p.confirme;
  if (niveau === "conteste") return p.conteste;
  return p.partiel;
}
