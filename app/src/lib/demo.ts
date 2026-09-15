// Édition de démonstration, pour essayer l'application avant que le pipeline publie.
// Les textes décrivent l'application : aucun n'est une information.

import type { SQLiteDatabase } from "expo-sqlite";

import { enregistrerEdition } from "./base";
import { aujourdhui } from "./dates";
import { RUBRIQUES, type Article, type Format, type NiveauConfiance } from "./types";

const SOURCES = [
  { nom: "Exemple A", url: "https://example.org/" },
  { nom: "Exemple B", url: "https://example.com/" },
];

interface Texte {
  titre: string;
  chapeau: string;
  corps: string[];
}

export async function chargerDemonstration(db: SQLiteDatabase): Promise<void> {
  const date = aujourdhui();
  const article = (rubrique: string, numero: number, format: Format, niveau: NiveauConfiance, fr: Texte, en: Texte): Article => ({
    id: `${date}-${rubrique}-demo${numero}`,
    rubrique,
    format,
    titre: fr.titre,
    chapeau: fr.chapeau,
    corps: fr.corps.join("\n\n"),
    niveau_de_confiance: niveau,
    sources: SOURCES,
    premiere_parution: null,
    suite_de: null,
    en: { titre: en.titre, chapeau: en.chapeau, corps: en.corps.join("\n\n") },
  });

  const articles: Article[] = [
    article("monde", 1, "fond", "confirme",
      {
        titre: "Démonstration : voici la place d'un article de fond dans l'édition",
        chapeau: "Ce texte n'est pas une information. Il montre la mise en page d'un article de fond, réservé aux sujets suivis par au moins cinq sources indépendantes.",
        corps: [
          "Chaque nuit, le robot lit près de 140 flux de presse et d'institutions. Il regroupe les articles qui parlent du même événement.",
          "Un sujet n'est publié que si deux sources indépendantes au moins le confirment. Deux journaux qui reprennent la même dépêche comptent pour une seule source.",
          "La pastille verte signale un fait confirmé par trois sources ou plus. La pastille orange signale deux sources. La pastille rouge signale des sources qui divergent.",
          "Les liens vers les sources figurent en bas de chaque article.",
        ],
      },
      {
        titre: "Demo: this is where an in-depth article sits in the edition",
        chapeau: "This text is not news. It shows the layout of an in-depth article, reserved for stories followed by at least five independent sources.",
        corps: [
          "Every night, the robot reads nearly 140 feeds from news outlets and institutions. It groups the articles that cover the same event.",
          "A story is published only if at least two independent sources confirm it. Two newspapers that run the same wire story count as a single source.",
          "The green dot marks a fact confirmed by three sources or more. The orange dot marks two sources. The red dot marks sources that disagree.",
          "Links to the sources appear at the bottom of each article.",
        ],
      }),
    article("monde", 2, "breve", "partiel",
      {
        titre: "Démonstration : une brève tient en quelques phrases",
        chapeau: "Ce texte n'est pas une information. Une brève rapporte un fait unique quand les sources donnent peu de contexte.",
        corps: ["Environ vingt-cinq brèves paraissent chaque jour. Elles font entre 150 et 250 mots."],
      },
      {
        titre: "Demo: a brief fits in a few sentences",
        chapeau: "This text is not news. A brief reports a single fact when the sources give little context.",
        corps: ["About twenty-five briefs appear every day. They run between 150 and 250 words."],
      }),
    article("france", 3, "standard", "conteste",
      {
        titre: "Démonstration : un article dont les sources ne disent pas la même chose",
        chapeau: "Ce texte n'est pas une information. Il montre la section que l'article ajoute quand les sources divergent.",
        corps: [
          "Quand les sources ne concordent pas sur un point important, l'article le dit.",
          "## Ce que disent les sources",
          "La source A donne une première version. La source B en donne une autre. L'article attribue chaque version à celui qui la formule.",
        ],
      },
      {
        titre: "Demo: an article whose sources do not say the same thing",
        chapeau: "This text is not news. It shows the section an article adds when its sources disagree.",
        corps: [
          "When the sources disagree on an important point, the article says so.",
          "## What the sources say",
          "Source A gives one version. Source B gives another. The article attributes each version to whoever puts it forward.",
        ],
      }),
    article("tech", 4, "breve", "confirme",
      {
        titre: "Démonstration : le bouton Écouter lit l'article avec la voix du téléphone",
        chapeau: "Ce texte n'est pas une information. La lecture audio marche sans connexion, avec la voix de synthèse du système.",
        corps: ["En tête de chaque rubrique, « Écouter la rubrique » enchaîne tous ses articles. La vitesse se règle dans l'onglet Réglages."],
      },
      {
        titre: "Demo: the Listen button reads the article aloud with the device's voice",
        chapeau: "This text is not news. Audio playback works offline, with the system's synthetic voice.",
        corps: ["At the top of each section, the Écouter button plays all its articles in a row. The speed is set in the Réglages tab."],
      }),
    article("culture", 5, "breve", "partiel",
      {
        titre: "Démonstration : les favoris et les archives restent sur le téléphone",
        chapeau: "Ce texte n'est pas une information. Les trente dernières éditions restent lisibles hors connexion.",
        corps: ["Un article enregistré en favori reste disponible au-delà de trente jours. La recherche porte sur tout ce qui est téléchargé."],
      },
      {
        titre: "Demo: favorites and archives stay on the device",
        chapeau: "This text is not news. The last thirty editions remain readable offline.",
        corps: ["An article saved as a favorite stays available beyond thirty days. Search covers everything that has been downloaded."],
      }),
  ];

  await enregistrerEdition(db, {
    date,
    genere_a: "demonstration",
    rubriques: RUBRIQUES,
    articles,
    une: [articles[0].id, articles[2].id, articles[3].id],
  });
}
