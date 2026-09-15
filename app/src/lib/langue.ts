// Langue d'affichage des articles : le français d'origine ou la traduction anglaise du pipeline.

import { versDate } from "./dates";
import type { Article, Format, NiveauConfiance } from "./types";

export type Langue = "fr" | "en";

export interface Contenu {
  titre: string;
  chapeau: string;
  corps: string;
  /** Langue réellement affichée : le français quand la traduction manque. */
  langue: Langue;
}

export function contenu(article: Article, langue: Langue): Contenu {
  if (langue === "en" && article.en?.titre) {
    return { titre: article.en.titre, chapeau: article.en.chapeau, corps: article.en.corps, langue: "en" };
  }
  return { titre: article.titre, chapeau: article.chapeau, corps: article.corps, langue: "fr" };
}

export const VOIX: Record<Langue, string> = { fr: "fr-FR", en: "en-US" };

/** Libellés de la page d'un article lu en anglais (l'interface reste en français). */
export const ANGLAIS = {
  confiance: { confirme: "Confirmed", partiel: "Partial", conteste: "Disputed" } as Record<NiveauConfiance, string>,
  explications: {
    confirme: "at least three independent sources, or an official source on its own domain",
    partiel: "two independent sources agree on the core facts",
    conteste: "the sources disagree on an important point",
  } as Record<NiveauConfiance, string>,
  formats: { breve: "Brief", standard: "Article", fond: "In-depth" } as Record<Format, string>,
  ecouter: "Listen",
  enregistrer: "Save",
  enregistre: "Saved",
  precedent: "Previous story",
  precedentAbsent: "This article follows a story that is no longer on the device.",
  note: "Article written automatically from these sources, then translated into English.",
};

export function dateLongueAnglais(texte: string): string {
  return new Intl.DateTimeFormat("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" }).format(
    versDate(texte),
  );
}
