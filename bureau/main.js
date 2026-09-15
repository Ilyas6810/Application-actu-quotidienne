// Application de bureau (Windows) : la version web de l'app dans une fenêtre Electron.
// Les fichiers de web/ (export Expo) passent par un protocole interne : aucun serveur local.

const { app, BrowserWindow, Menu, nativeTheme, protocol, shell } = require("electron");
const fs = require("node:fs/promises");
const path = require("node:path");

const SCHEMA = "actu";
const ORIGINE = `${SCHEMA}://app`;
const RACINE = path.join(__dirname, "web");
const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json",
  ".wasm": "application/wasm",
  ".css": "text/css",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".ttf": "font/ttf",
  ".ico": "image/x-icon",
  ".svg": "image/svg+xml",
};

// Dossier de données séparé pour les essais, pour ne pas toucher à celui de l'application installée.
if (process.env.ACTU_DONNEES) app.setPath("userData", process.env.ACTU_DONNEES);

// « standard » et « secure » donnent à la page une vraie origine : stockage (OPFS) et workers.
protocol.registerSchemesAsPrivileged([
  {
    scheme: SCHEMA,
    privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true, stream: true, codeCache: true },
  },
]);

// Éditions produites sur cet ordinateur : le dossier docs/ du projet, noté par preparer-web.js.
const PREFIXE_EDITIONS = "/editions-locales/";
const DOSSIER_EDITIONS = (() => {
  try {
    return require("./local.json").editions;
  } catch {
    return null;
  }
})();

async function servirEdition(relatif) {
  const introuvable = new Response(null, { status: 404 });
  if (!DOSSIER_EDITIONS) return introuvable;
  const fichier = path.join(DOSSIER_EDITIONS, relatif);
  if (!fichier.startsWith(DOSSIER_EDITIONS + path.sep) || path.extname(fichier) !== ".json") return introuvable;
  try {
    return new Response(await fs.readFile(fichier), {
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return introuvable;
  }
}

async function servir(requete) {
  const chemin = decodeURIComponent(new URL(requete.url).pathname);
  if (chemin.startsWith(PREFIXE_EDITIONS)) return servirEdition(chemin.slice(PREFIXE_EDITIONS.length));
  let fichier = path.join(RACINE, chemin);
  if (!fichier.startsWith(RACINE + path.sep)) return new Response(null, { status: 403 });
  let contenu;
  try {
    contenu = await fs.readFile(fichier);
  } catch {
    // Application monopage : les adresses de l'app (/archives, /article/…) reçoivent index.html.
    fichier = path.join(RACINE, "index.html");
    contenu = await fs.readFile(fichier);
  }
  return new Response(contenu, {
    headers: {
      "Content-Type": TYPES[path.extname(fichier)] ?? "application/octet-stream",
      // expo-sqlite (wasm dans un worker) exige une page isolée
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "credentialless",
    },
  });
}

let fenetre = null;

function ouvrirFenetre() {
  fenetre = new BrowserWindow({
    width: 480,
    height: 900,
    minWidth: 360,
    minHeight: 560,
    title: "Actu quotidienne",
    backgroundColor: nativeTheme.shouldUseDarkColors ? "#121212" : "#F7F5F0",
    autoHideMenuBar: true,
    webPreferences: { contextIsolation: true, sandbox: true },
  });
  fenetre.on("page-title-updated", (evenement) => evenement.preventDefault());
  // Les liens vers les sources s'ouvrent dans le navigateur habituel.
  fenetre.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
    return { action: "deny" };
  });
  fenetre.webContents.on("will-navigate", (evenement, url) => {
    if (url.startsWith(ORIGINE)) return;
    evenement.preventDefault();
    if (/^https?:\/\//.test(url)) shell.openExternal(url);
  });
  fenetre.on("closed", () => {
    fenetre = null;
  });
  fenetre.loadURL(`${ORIGINE}/`);
}

// Une seule fenêtre : deux pages ne peuvent pas ouvrir la même base SQLite en même temps.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!fenetre) return;
    if (fenetre.isMinimized()) fenetre.restore();
    fenetre.focus();
  });
  app.whenReady().then(() => {
    Menu.setApplicationMenu(null);
    protocol.handle(SCHEMA, servir);
    ouvrirFenetre();
  });
  app.on("window-all-closed", () => app.quit());
}
