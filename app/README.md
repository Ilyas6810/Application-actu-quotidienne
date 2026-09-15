# Application Android

Lit l'édition publiée par le pipeline, hors connexion : les 30 derniers jours, la recherche
plein texte, les favoris, l'écoute avec la voix du téléphone et la notification de 6 h.

## Essayer tout de suite avec Expo Go (sans compilation)

1. Installe Expo Go depuis le Play Store.
2. Dans ce dossier : `npm install`, puis `npx expo start`.
3. Scanne le QR code avec Expo Go (téléphone et ordinateur sur le même Wi-Fi).
4. Onglet Réglages, « Adresse des éditions » : `https://Ilyas6810.github.io/Application-actu-quotidienne`, puis
   « Tester et enregistrer ». Avant la première édition, « Charger l'édition de démonstration ».

Dans Expo Go, la notification locale de 6 h marche. Les notifications push (alertes, titres
de 6 h) ne marchent pas : Expo Go ne les prend plus en charge sur Android depuis le SDK 53.

## Installer la vraie application (APK, gratuit)

1. Crée un compte gratuit sur expo.dev.
2. `npx eas-cli login`, puis `npx eas-cli init` : l'identifiant du projet s'ajoute dans `app.json`.
3. Dans `app.json`, remplace l'adresse `extra.urlEditions` par la tienne.
4. `npx eas-cli build -p android --profile apk`. La compilation tourne chez Expo (quota
   gratuit mensuel) ; le lien de l'APK arrive à la fin.
5. Sur le téléphone, ouvre le lien et autorise l'installation depuis cette source.

## Notifications push (facultatif : alertes et titres de 6 h)

1. Crée un projet Firebase gratuit, ajoute une application Android avec le nom de paquet
   `fr.actuquotidienne.app`, télécharge `google-services.json` dans ce dossier et ajoute
   `"googleServicesFile": "./google-services.json"` dans la section `android` de `app.json`.
2. Donne à EAS la clé du compte de service FCM : `npx eas-cli credentials`, Android,
   Push Notifications (FCM V1).
3. Recompile l'APK. Dans Réglages, choisis « Push », touche « Afficher mon jeton de
   notification » et copie-le dans le secret GitHub `EXPO_PUSH_TOKEN`.

## Lire en anglais

Dans Réglages, « Langue des articles » : English. Les cartes et les articles s'affichent dans
la traduction que le pipeline ajoute (`pipeline/traduction.py`), et la voix lit en anglais. Un
article pas encore traduit reste en français. Sur la page d'un article, le bouton
English / Français change la langue de cet article seulement. Les menus restent en français.

## Limites

- La voix est la synthèse du système : robotique, sans pause ni commandes sur l'écran
  verrouillé (expo-speech n'ouvre pas de session média). L'écran reste allumé pendant l'écoute
  pour que la lecture d'une rubrique ne s'interrompe pas.
- L'icône est celle du gabarit Expo, à remplacer dans `assets/`.
