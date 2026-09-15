// Lecture audio avec la voix du téléphone (expo-speech) : un article ou une rubrique entière.
//
// Limites d'expo-speech sur Android : pas de pause (seulement arrêt), pas de contrôles sur
// l'écran verrouillé (aucune session média). L'écran reste allumé pendant la lecture pour
// que l'enchaînement des articles ne s'interrompe pas au verrouillage.

import * as Speech from "expo-speech";
import { activateKeepAwakeAsync, deactivateKeepAwake } from "expo-keep-awake";
import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";

import { contenu, VOIX, type Langue } from "./langue";
import { useReglages } from "./reglages";
import type { Article } from "./types";

const CLE_ECRAN = "lecture";
// Le moteur Android refuse les textes trop longs (souvent 4 000 caractères).
const LIMITE = Math.min(3000, (Speech.maxSpeechInputLength || 4000) - 100);

export interface EtatLecture {
  article: Article;
  position: number;
  total: number;
  langue: Langue;
}

interface ValeurLecteur {
  etat: EtatLecture | null;
  lire: (articles: Article[], depart?: number, langue?: Langue) => Promise<void>;
  suivant: () => Promise<void>;
  arreter: () => Promise<void>;
}

export function textePourLecture(article: Article, langue: Langue = "fr"): string {
  const t = contenu(article, langue);
  return `${t.titre}.\n${t.chapeau}\n${t.corps.replace(/^## /gm, "")}`;
}

/** Découpe par paragraphes, puis par phrases, sous la limite du moteur. */
export function decouper(texte: string, limite: number = LIMITE): string[] {
  const morceaux: string[] = [];
  for (const paragraphe of texte.split(/\n+/)) {
    let reste = paragraphe.trim();
    while (reste.length > limite) {
      let coupe = reste.lastIndexOf(". ", limite);
      if (coupe < limite / 2) coupe = reste.lastIndexOf(" ", limite);
      if (coupe <= 0) coupe = limite;
      morceaux.push(reste.slice(0, coupe + 1).trim());
      reste = reste.slice(coupe + 1).trim();
    }
    if (reste) morceaux.push(reste);
  }
  return morceaux;
}

const Contexte = createContext<ValeurLecteur | null>(null);

export function FournisseurLecteur({ children }: { children: ReactNode }) {
  const { reglages } = useReglages();
  const [etat, setEtat] = useState<EtatLecture | null>(null);
  const file = useRef<Article[]>([]);
  const position = useRef(0);
  const morceau = useRef(0);
  const generation = useRef(0); // invalide les rappels d'une lecture interrompue
  const vitesse = useRef(reglages.vitesseLecture);
  vitesse.current = reglages.vitesseLecture;
  const langueChoisie = useRef(reglages.langue);
  langueChoisie.current = reglages.langue;
  const langueLecture = useRef<Langue>(reglages.langue);

  const jouer = useRef<() => void>(() => undefined);
  jouer.current = () => {
    const article = file.current[position.current];
    if (!article) {
      setEtat(null);
      deactivateKeepAwake(CLE_ECRAN).catch(() => undefined);
      return;
    }
    const langue = contenu(article, langueLecture.current).langue; // français si la traduction manque
    const morceaux = decouper(textePourLecture(article, langue));
    if (morceau.current >= morceaux.length) {
      position.current += 1;
      morceau.current = 0;
      jouer.current();
      return;
    }
    setEtat({ article, position: position.current, total: file.current.length, langue });
    const numero = generation.current;
    Speech.speak(morceaux[morceau.current], {
      language: VOIX[langue],
      rate: vitesse.current,
      onDone: () => {
        if (numero !== generation.current) return;
        morceau.current += 1;
        jouer.current();
      },
      onError: () => {
        if (numero !== generation.current) return;
        position.current += 1;
        morceau.current = 0;
        jouer.current();
      },
    });
  };

  const lire = useCallback(async (articles: Article[], depart = 0, langue?: Langue) => {
    generation.current += 1;
    await Speech.stop();
    langueLecture.current = langue ?? langueChoisie.current;
    file.current = articles;
    position.current = depart;
    morceau.current = 0;
    await activateKeepAwakeAsync(CLE_ECRAN).catch(() => undefined);
    jouer.current();
  }, []);

  const suivant = useCallback(async () => {
    generation.current += 1;
    await Speech.stop();
    position.current += 1;
    morceau.current = 0;
    jouer.current();
  }, []);

  const arreter = useCallback(async () => {
    generation.current += 1;
    await Speech.stop();
    setEtat(null);
    deactivateKeepAwake(CLE_ECRAN).catch(() => undefined);
  }, []);

  return <Contexte.Provider value={{ etat, lire, suivant, arreter }}>{children}</Contexte.Provider>;
}

export function useLecteur(): ValeurLecteur {
  const valeur = useContext(Contexte);
  if (!valeur) throw new Error("useLecteur doit être appelé sous FournisseurLecteur");
  return valeur;
}
