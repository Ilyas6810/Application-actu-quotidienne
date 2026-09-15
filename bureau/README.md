# Application de bureau (Windows)

La version web de l'app dans une fenêtre Electron : mêmes écrans, même base SQLite locale,
lecture hors connexion. Les fichiers passent par un protocole interne (`actu://app`), sans
serveur local.

Sans réglage, l'app lit les éditions du dossier `docs/` du projet, celles que fabrique
`Mettre à jour l'édition.cmd`. Leur adresse est `actu://app/editions-locales`, et le chemin du
dossier est noté dans `local.json` au moment de fabriquer l'installateur. Pour lire plutôt
celles de GitHub Pages, change l'adresse dans Réglages.

## Installer

1. Double-clique `dist/Actu-quotidienne-1.0.0-installation.exe`. L'installation se fait dans
   ton compte Windows (sans droits d'administrateur) et crée un raccourci sur le bureau et dans
   le menu Démarrer.
2. L'installateur n'est pas signé : Windows affiche « Windows a protégé votre ordinateur ».
   Clique « Informations complémentaires », puis « Exécuter quand même ».
3. Pour désinstaller : *Paramètres > Applications > Applications installées > Actu quotidienne*.

## Refaire l'installateur après une modification de l'app

Dans ce dossier :

```
npm install
npm run installateur
```

`npm run installateur` exporte la version web de `../app` dans `web/`, puis fabrique
l'installateur dans `dist/`. Pour ouvrir l'app sans l'installer (`npm run demarrer`), télécharge
d'abord Electron une fois : `node node_modules/electron/install.js`.

## Différences avec le téléphone

- Pas de notification de 6 h : expo-notifications ne marche pas sur ordinateur.
- La lecture audio prend la voix française par défaut de Windows. Electron ne donne pas la liste
  des voix, on ne peut donc pas en choisir une autre.
- Les données restent dans `%APPDATA%\Actu quotidienne`, à part de celles du téléphone : les
  favoris ne se partagent pas.
- Pas de mise à jour automatique : il faut installer le nouvel installateur par-dessus.
- L'icône est celle du gabarit Expo.
