// Exporte la version web de l'app (dossier ../app) dans web/, que l'application de bureau embarque.
// Sur ordinateur, l'app lit les éditions du dossier docs/ du projet, produites par le pipeline :
// local.json note ce dossier, et l'adresse des éditions par défaut pointe vers lui.
const { execSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const sortie = path.join(__dirname, "web");
fs.rmSync(sortie, { recursive: true, force: true });
fs.writeFileSync(
  path.join(__dirname, "local.json"),
  JSON.stringify({ editions: path.resolve(__dirname, "..", "docs") }, null, 2) + "\n",
);
execSync(`npx expo export --platform web --clear --output-dir "${sortie}"`, {
  cwd: path.join(__dirname, "..", "app"),
  stdio: "inherit",
  env: { ...process.env, EXPO_PUBLIC_URL_EDITIONS: "actu://app/editions-locales" },
});
