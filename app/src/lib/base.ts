// Base SQLite locale : éditions des 30 derniers jours, recherche plein texte (FTS5),
// favoris (copie complète, conservée après la purge), alertes, réglages.

import type { SQLiteDatabase } from "expo-sqlite";
import { Platform } from "react-native";

import { aujourdhui, decaler } from "./dates";
import type { Alerte, Article, ArticleDate, Edition, NiveauConfiance, Format, Rubrique, Source, Traduction } from "./types";

let ftsDisponible = false;

export async function migrer(db: SQLiteDatabase): Promise<void> {
  await db.execAsync("PRAGMA journal_mode = WAL;");
  const version = await db.getFirstAsync<{ user_version: number }>("PRAGMA user_version");
  if ((version?.user_version ?? 0) < 1) {
    await db.execAsync(`
CREATE TABLE IF NOT EXISTS editions (date TEXT PRIMARY KEY NOT NULL, genere_a TEXT, une TEXT NOT NULL,
  rubriques TEXT NOT NULL, recue_a TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS articles (id TEXT PRIMARY KEY NOT NULL, date TEXT NOT NULL, rang INTEGER NOT NULL,
  rubrique TEXT NOT NULL, format TEXT NOT NULL, titre TEXT NOT NULL, chapeau TEXT NOT NULL, corps TEXT NOT NULL,
  niveau TEXT NOT NULL, sources TEXT NOT NULL, premiere_parution TEXT, suite_de TEXT);
CREATE INDEX IF NOT EXISTS articles_par_date ON articles (date, rang);
CREATE TABLE IF NOT EXISTS favoris (id TEXT PRIMARY KEY NOT NULL, ajoute_a TEXT NOT NULL, date TEXT NOT NULL,
  article TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS alertes (id TEXT PRIMARY KEY NOT NULL, date TEXT NOT NULL, publiee_a TEXT,
  titre TEXT NOT NULL, texte TEXT NOT NULL, sources TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reglages (cle TEXT PRIMARY KEY NOT NULL, valeur TEXT NOT NULL);
PRAGMA user_version = 1;
`);
  }
  if ((version?.user_version ?? 0) < 2) {
    // Version 2 : traduction anglaise des articles (JSON {titre, chapeau, corps})
    try {
      await db.execAsync("ALTER TABLE articles ADD COLUMN en TEXT;");
    } catch {
      // colonne déjà présente
    }
    await db.execAsync("PRAGMA user_version = 2;");
  }
  try {
    await db.execAsync(
      "CREATE VIRTUAL TABLE IF NOT EXISTS recherche USING fts5(id UNINDEXED, date UNINDEXED, titre, chapeau, corps, " +
        "tokenize = 'unicode61 remove_diacritics 2');",
    );
    ftsDisponible = true;
  } catch {
    ftsDisponible = false; // SQLite sans FTS5 : la recherche passe par LIKE
  }
}

function lireJson<T>(texte: string | null | undefined, defaut: T): T {
  if (!texte) return defaut;
  try {
    return JSON.parse(texte) as T;
  } catch {
    return defaut;
  }
}

interface LigneArticle {
  id: string;
  date: string;
  rubrique: string;
  format: string;
  titre: string;
  chapeau: string;
  corps: string;
  niveau: string;
  sources: string;
  premiere_parution: string | null;
  suite_de: string | null;
  en: string | null;
}

function versArticle(l: LigneArticle): ArticleDate {
  return {
    id: l.id,
    date: l.date,
    rubrique: l.rubrique,
    format: l.format as Format,
    titre: l.titre,
    chapeau: l.chapeau,
    corps: l.corps,
    niveau_de_confiance: l.niveau as NiveauConfiance,
    sources: lireJson<Source[]>(l.sources, []),
    premiere_parution: l.premiere_parution,
    suite_de: l.suite_de,
    en: lireJson<Traduction | null>(l.en, null),
  };
}

// --- Éditions --------------------------------------------------------------------

/** Transaction exclusive sur le téléphone ; simple sur le web, où l'exclusive n'existe pas. */
async function transaction(db: SQLiteDatabase, tache: (txn: SQLiteDatabase) => Promise<void>): Promise<void> {
  if (Platform.OS === "web") await db.withTransactionAsync(() => tache(db));
  else await db.withExclusiveTransactionAsync((txn) => tache(txn));
}

export async function enregistrerEdition(db: SQLiteDatabase, edition: Edition): Promise<void> {
  await transaction(db, async (txn) => {
    await txn.runAsync("DELETE FROM articles WHERE date = ?", edition.date);
    if (ftsDisponible) await txn.runAsync("DELETE FROM recherche WHERE date = ?", edition.date);
    for (const [rang, a] of edition.articles.entries()) {
      await txn.runAsync(
        "INSERT OR REPLACE INTO articles (id, date, rang, rubrique, format, titre, chapeau, corps, niveau, sources, " +
          "premiere_parution, suite_de, en) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        a.id, edition.date, rang, a.rubrique, a.format, a.titre, a.chapeau ?? "", a.corps ?? "",
        a.niveau_de_confiance, JSON.stringify(a.sources ?? []), a.premiere_parution ?? null, a.suite_de ?? null,
        a.en ? JSON.stringify(a.en) : null,
      );
      if (ftsDisponible) {
        await txn.runAsync(
          "INSERT INTO recherche (id, date, titre, chapeau, corps) VALUES (?, ?, ?, ?, ?)",
          // La traduction est indexée avec le corps : la recherche marche dans les deux langues.
          a.id, edition.date, a.titre, a.chapeau ?? "",
          [a.corps ?? "", a.en ? `${a.en.titre}\n${a.en.chapeau}\n${a.en.corps}` : ""].join("\n").replace(/^## /gm, ""),
        );
      }
    }
    await txn.runAsync(
      "INSERT OR REPLACE INTO editions (date, genere_a, une, rubriques, recue_a) VALUES (?, ?, ?, ?, ?)",
      edition.date, edition.genere_a ?? null, JSON.stringify(edition.une ?? []),
      JSON.stringify(edition.rubriques ?? []), new Date().toISOString(),
    );
  });
}

export async function chargerEdition(db: SQLiteDatabase, date: string): Promise<Edition | null> {
  const e = await db.getFirstAsync<{ date: string; genere_a: string | null; une: string; rubriques: string }>(
    "SELECT date, genere_a, une, rubriques FROM editions WHERE date = ?", date,
  );
  if (!e) return null;
  const lignes = await db.getAllAsync<LigneArticle>("SELECT * FROM articles WHERE date = ? ORDER BY rang", date);
  return {
    date: e.date,
    genere_a: e.genere_a ?? "",
    une: lireJson<string[]>(e.une, []),
    rubriques: lireJson<Rubrique[]>(e.rubriques, []),
    articles: lignes.map(versArticle),
  };
}

export async function dateLaPlusRecente(db: SQLiteDatabase): Promise<string | null> {
  const ligne = await db.getFirstAsync<{ date: string }>("SELECT date FROM editions ORDER BY date DESC LIMIT 1");
  return ligne?.date ?? null;
}

export async function versionsLocales(db: SQLiteDatabase): Promise<Map<string, string>> {
  const lignes = await db.getAllAsync<{ date: string; genere_a: string | null }>("SELECT date, genere_a FROM editions");
  return new Map(lignes.map((l) => [l.date, l.genere_a ?? ""]));
}

export async function editionsDisponibles(db: SQLiteDatabase): Promise<{ date: string; articles: number }[]> {
  return db.getAllAsync<{ date: string; articles: number }>(
    "SELECT e.date AS date, COUNT(a.id) AS articles FROM editions e LEFT JOIN articles a ON a.date = e.date " +
      "GROUP BY e.date ORDER BY e.date DESC",
  );
}

export async function chargerArticle(db: SQLiteDatabase, id: string): Promise<ArticleDate | null> {
  const ligne = await db.getFirstAsync<LigneArticle>("SELECT * FROM articles WHERE id = ?", id);
  if (ligne) return versArticle(ligne);
  const favori = await db.getFirstAsync<{ article: string; date: string }>(
    "SELECT article, date FROM favoris WHERE id = ?", id,
  );
  const article = lireJson<Article | null>(favori?.article, null);
  return article && favori ? { ...article, date: favori.date } : null;
}

export async function purger(db: SQLiteDatabase, jours: number): Promise<void> {
  const limite = decaler(aujourdhui(), -jours);
  await db.runAsync("DELETE FROM articles WHERE date < ?", limite);
  if (ftsDisponible) await db.runAsync("DELETE FROM recherche WHERE date < ?", limite);
  await db.runAsync("DELETE FROM editions WHERE date < ?", limite);
  await db.runAsync("DELETE FROM alertes WHERE date < ?", decaler(aujourdhui(), -7));
}

export async function effacerEditions(db: SQLiteDatabase): Promise<void> {
  await db.execAsync("DELETE FROM articles; DELETE FROM editions;" + (ftsDisponible ? " DELETE FROM recherche;" : ""));
}

// --- Recherche -------------------------------------------------------------------

export interface Resultat {
  id: string;
  date: string;
  titre: string;
  extrait: string;
}

export async function rechercher(db: SQLiteDatabase, texte: string): Promise<Resultat[]> {
  const mots = texte
    .split(/[\s,.;:!?'’"«»()[\]{}/\\-]+/)
    .map((m) => m.trim())
    .filter((m) => m.length >= 2)
    .slice(0, 8);
  if (mots.length === 0) return [];
  if (ftsDisponible) {
    const requete = mots.map((m) => `"${m.replace(/"/g, "")}"*`).join(" ");
    try {
      return await db.getAllAsync<Resultat>(
        "SELECT id, date, titre, snippet(recherche, 4, '', '', '…', 16) AS extrait FROM recherche " +
          "WHERE recherche MATCH ? ORDER BY rank LIMIT 60",
        requete,
      );
    } catch {
      // requête refusée par FTS5 : on retombe sur LIKE
    }
  }
  const conditions = mots.map(() => "(titre LIKE ? OR chapeau LIKE ? OR corps LIKE ?)").join(" AND ");
  const parametres = mots.flatMap((m) => [`%${m}%`, `%${m}%`, `%${m}%`]);
  const lignes = await db.getAllAsync<{ id: string; date: string; titre: string; chapeau: string }>(
    `SELECT id, date, titre, chapeau FROM articles WHERE ${conditions} ORDER BY date DESC LIMIT 60`,
    parametres,
  );
  return lignes.map((l) => ({ id: l.id, date: l.date, titre: l.titre, extrait: l.chapeau }));
}

// --- Favoris ---------------------------------------------------------------------

export async function estFavori(db: SQLiteDatabase, id: string): Promise<boolean> {
  return (await db.getFirstAsync<{ oui: number }>("SELECT 1 AS oui FROM favoris WHERE id = ?", id)) !== null;
}

/** Ajoute ou retire l'article des favoris. Renvoie le nouvel état. */
export async function basculerFavori(db: SQLiteDatabase, article: ArticleDate): Promise<boolean> {
  if (await estFavori(db, article.id)) {
    await db.runAsync("DELETE FROM favoris WHERE id = ?", article.id);
    return false;
  }
  await db.runAsync(
    "INSERT OR REPLACE INTO favoris (id, ajoute_a, date, article) VALUES (?, ?, ?, ?)",
    article.id, new Date().toISOString(), article.date, JSON.stringify(article),
  );
  return true;
}

export async function listerFavoris(db: SQLiteDatabase): Promise<ArticleDate[]> {
  const lignes = await db.getAllAsync<{ article: string; date: string }>(
    "SELECT article, date FROM favoris ORDER BY ajoute_a DESC",
  );
  return lignes.flatMap((l) => {
    const article = lireJson<Article | null>(l.article, null);
    return article ? [{ ...article, date: l.date }] : [];
  });
}

// --- Alertes ---------------------------------------------------------------------

export async function enregistrerAlertes(db: SQLiteDatabase, alertes: Alerte[]): Promise<void> {
  for (const a of alertes) {
    await db.runAsync(
      "INSERT OR REPLACE INTO alertes (id, date, publiee_a, titre, texte, sources) VALUES (?, ?, ?, ?, ?, ?)",
      a.id, a.date, a.publiee_a ?? null, a.titre, a.texte ?? "", JSON.stringify(a.sources ?? []),
    );
  }
}

/** Alertes d'aujourd'hui et d'hier, les plus récentes d'abord. */
export async function alertesRecentes(db: SQLiteDatabase): Promise<Alerte[]> {
  const lignes = await db.getAllAsync<{ id: string; date: string; publiee_a: string | null; titre: string; texte: string; sources: string }>(
    "SELECT * FROM alertes WHERE date >= ? ORDER BY publiee_a DESC LIMIT 3", decaler(aujourdhui(), -1),
  );
  return lignes.map((l) => ({ ...l, sources: lireJson<Source[]>(l.sources, []) }));
}
