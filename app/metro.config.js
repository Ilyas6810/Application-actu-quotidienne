// Configuration Metro. Les deux ajouts ne servent qu'à l'aperçu dans un navigateur
// (expo-sqlite sur le web) : fichiers .wasm, et en-têtes d'isolation qui autorisent
// SharedArrayBuffer. Ils n'ont aucun effet sur l'application Android.
const { getDefaultConfig } = require("expo/metro-config");

const config = getDefaultConfig(__dirname);

config.resolver.assetExts.push("wasm");
config.server.enhanceMiddleware = (middleware) => (req, res, next) => {
  res.setHeader("Cross-Origin-Embedder-Policy", "credentialless");
  res.setHeader("Cross-Origin-Opener-Policy", "same-origin");
  middleware(req, res, next);
};

module.exports = config;
