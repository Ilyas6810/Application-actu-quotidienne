// Modèle de données de l'édition (section 7 du cahier des charges).

export type NiveauConfiance = "confirme" | "partiel" | "conteste";
export type Format = "breve" | "standard" | "fond";

export interface Source {
  nom: string;
  url: string;
}

/** Traduction anglaise, ajoutée par le pipeline (traduction.py). */
export interface Traduction {
  titre: string;
  chapeau: string;
  corps: string;
}

export interface Article {
  id: string;
  rubrique: string;
  format: Format;
  titre: string;
  chapeau: string;
  corps: string;
  niveau_de_confiance: NiveauConfiance;
  sources: Source[];
  premiere_parution: string | null;
  suite_de: string | null;
  mots?: number;
  modele?: string;
  en?: Traduction | null;
}

/** Article accompagné de la date de l'édition qui le contient. */
export type ArticleDate = Article & { date: string };

export interface Rubrique {
  id: string;
  nom: string;
}

export interface Edition {
  date: string;
  genere_a: string;
  rubriques: Rubrique[];
  articles: Article[];
  une: string[];
}

export interface ResumeEdition {
  date: string;
  genere_a: string | null;
  articles: number;
  une: string[];
}

export interface IndexEditions {
  maj: string | null;
  derniere: string | null;
  editions: ResumeEdition[];
}

export interface Alerte {
  id: string;
  date: string;
  publiee_a: string | null;
  titre: string;
  texte: string;
  sources: Source[];
}

export const RUBRIQUES: Rubrique[] = [
  { id: "une", nom: "À la une" },
  { id: "monde", nom: "Monde" },
  { id: "france", nom: "France" },
  { id: "geopolitique", nom: "Géopolitique" },
  { id: "economie", nom: "Économie" },
  { id: "tech", nom: "Tech / IA" },
  { id: "sciences", nom: "Sciences" },
  { id: "sante", nom: "Santé" },
  { id: "sport", nom: "Sport" },
  { id: "culture", nom: "Culture" },
];

export function nomRubrique(id: string): string {
  return RUBRIQUES.find((r) => r.id === id)?.nom ?? id;
}
