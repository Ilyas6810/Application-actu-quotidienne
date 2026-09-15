// Téléchargement des éditions publiées sur GitHub Pages.

import type { SQLiteDatabase } from "expo-sqlite";

import { enregistrerAlertes, enregistrerEdition, purger, versionsLocales } from "./base";
import { aujourdhui, decaler } from "./dates";
import type { Alerte, Edition, IndexEditions } from "./types";

export const JOURS_CONSERVES = 30;

export interface ResultatSynchro {
  ok: boolean;
  nouvelles: number;
  erreur?: string;
}

async function lireJson<T>(url: string, delaiMs = 20000): Promise<T> {
  const controleur = new AbortController();
  const minuterie = setTimeout(() => controleur.abort(), delaiMs);
  try {
    const reponse = await fetch(url, { signal: controleur.signal, headers: { "Cache-Control": "no-cache" } });
    if (!reponse.ok) throw new Error(`HTTP ${reponse.status}`);
    return (await reponse.json()) as T;
  } finally {
    clearTimeout(minuterie);
  }
}

export function racine(url: string): string {
  return url.trim().replace(/\/+$/, "");
}

export function adresseValide(url: string): boolean {
  // actu:// : éditions du dossier docs/ lues par l'application de bureau (voir bureau/main.js)
  return /^(https?|actu):\/\/\S+$/.test(url.trim()) && !url.includes("UTILISATEUR");
}

export async function lireIndex(url: string): Promise<IndexEditions> {
  // Paramètre unique : le cache de GitHub Pages (10 minutes) ne sert pas une vieille version.
  return lireJson<IndexEditions>(`${racine(url)}/index.json?t=${Date.now()}`);
}

/**
 * Télécharge les éditions des 30 derniers jours absentes ou changées, la plus récente
 * d'abord, puis les alertes. `apresChaque` est appelé après chaque édition enregistrée.
 */
export async function synchroniser(
  db: SQLiteDatabase,
  url: string,
  apresChaque?: (date: string) => void,
): Promise<ResultatSynchro> {
  if (!adresseValide(url)) {
    return { ok: false, nouvelles: 0, erreur: "adresse des éditions à renseigner dans Réglages" };
  }
  try {
    const index = await lireIndex(url);
    const locales = await versionsLocales(db);
    const limite = decaler(aujourdhui(), -JOURS_CONSERVES);
    const manquantes = (index.editions ?? [])
      .filter((e) => e.date >= limite && locales.get(e.date) !== (e.genere_a ?? ""))
      .sort((a, b) => b.date.localeCompare(a.date));
    let nouvelles = 0;
    for (const resume of manquantes) {
      const version = encodeURIComponent(resume.genere_a ?? "");
      const edition = await lireJson<Edition>(`${racine(url)}/editions/${resume.date}.json?v=${version}`);
      await enregistrerEdition(db, edition);
      nouvelles += 1;
      apresChaque?.(resume.date);
    }
    try {
      const donnees = await lireJson<{ alertes?: Alerte[] }>(`${racine(url)}/alertes.json?t=${Date.now()}`);
      await enregistrerAlertes(db, donnees.alertes ?? []);
    } catch {
      // les alertes sont facultatives
    }
    await purger(db, JOURS_CONSERVES);
    return { ok: true, nouvelles };
  } catch (e) {
    const erreur = e instanceof Error ? (e.name === "AbortError" ? "délai dépassé" : e.message) : String(e);
    return { ok: false, nouvelles: 0, erreur };
  }
}
