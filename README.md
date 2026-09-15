# Actu quotidienne

Application d'actualité quotidienne autonome, à budget nul. Chaque nuit, un robot lit près de
140 flux de presse et d'institutions (46 sources), regroupe les informations qui parlent du même événement,
garde celles que confirment au moins deux sources indépendantes et rédige une cinquantaine
d'articles. L'édition est en ligne avant 6 h (UTC+4) ; l'application Android la télécharge et
la lit hors ligne.

Le cahier des charges reste la référence. Ce fichier dit comment faire tourner le projet et où
il s'en écarte.

## Organisation

| Chemin | Rôle |
|---|---|
| `pipeline/collecte.py` | Étape 1 : flux RSS normalisés dans le pool (72 heures glissantes) |
| `pipeline/radar_gdelt.py`, `pipeline/portail_wikipedia.py` | Étape 2 : radar mondial et filet de sécurité |
| `pipeline/cluster.py` | Étape 3 : regroupement par événement, sources indépendantes, rubrique, score |
| `pipeline/redaction.py`, `pipeline/llm.py` | Étape 4 : choix des sujets, rédaction par la cascade de modèles gratuits |
| `pipeline/controle.py`, `pipeline/publie.py` | Étape 5 : contrôles automatiques, publication |
| `pipeline/traduction.py` | Traduction anglaise des articles, pour l'option « English » de l'application. Ajout par rapport au cahier des charges |
| `pipeline/alertes.py`, `pipeline/notifier.py` | Alertes urgentes (trois par jour au plus), notifications push |
| `pipeline/edition.py` | Tout l'enchaînement du matin |
| `pipeline/config/` | Sources, modèles, réglages, mots interdits |
| `pipeline/etat/` | État entre deux passages : pool, groupes, rapports. Jamais commité |
| `docs/` | Racine du site GitHub Pages : `editions/AAAA-MM-JJ.json`, `index.json`, `alertes.json` |
| `.github/workflows/` | Collecte toutes les 3 heures, édition à 00:30 UTC |
| `app/` | Étape 6 : application Android (Expo SDK 57). Installation et push : `app/README.md` |
| `bureau/` | La même application pour Windows (Electron). Installateur : `bureau/README.md` |

## Faire tourner les étapes 1 à 5 sur ta machine

1. Installe Python 3.12 depuis python.org (coche « Add python.exe to PATH »).
2. Dans un terminal ouvert dans le dossier `pipeline` :

   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   python -m pytest tests
   ```

3. Enchaîne les étapes. Chacune se vérifie seule.

| Étape | Commande | Ce qu'on doit voir |
|---|---|---|
| 1 | `python collecte.py --rss-seulement` | Des centaines d'items, zéro doublon d'URL. `etat/sante_flux.json` liste les flux en panne |
| 2 | `python radar_gdelt.py` puis `python collecte.py` | Des événements repris en espagnol, en indonésien… |
| 3 | `python cluster.py` | Dans `etat/rapport_clusters.md`, un groupe = un événement. Ajuste `seuil` dans `config/pipeline.yaml`, ou essaie `python cluster.py --seuil 0.5` |
| 4 | `python redaction.py --nombre 10` | Dix articles lisibles dans `etat/brouillons.md` |
| 5 | `python publie.py` | `docs/editions/AAAA-MM-JJ.json` et `docs/index.json` |

Sans clé d'API, `python redaction.py --nombre 3 --factice` teste la mécanique avec un faux
modèle (textes vides de sens). `python edition.py` fait tout d'un coup, comme GitHub Actions
le matin.

### Clés d'API gratuites

Copie `pipeline/.env.exemple` en `pipeline/.env` et colle au moins une clé. Le fichier `.env`
n'est jamais commité.

| Variable | Où la créer |
|---|---|
| `GEMINI_API_KEY` | aistudio.google.com, bouton « Get API key » |
| `GROQ_API_KEY` | console.groq.com |
| `OPENROUTER_API_KEY` | openrouter.ai |
| `MISTRAL_API_KEY` | console.mistral.ai (offre Experiment, numéro de téléphone demandé) |

## Utiliser l'application sur cet ordinateur, sans GitHub

1. Installe l'application de bureau (`bureau/README.md`). Elle lit directement les éditions du
   dossier `docs/`, sans serveur.
2. Colle au moins une clé d'API dans `pipeline/.env`.
3. Double-clique `Mettre à jour l'édition.cmd`, à la racine du projet. Il enchaîne collecte,
   regroupement, rédaction et publication dans `docs/` : compte une vingtaine de minutes pour
   une édition complète. Rouvre ensuite l'application.

## Mise en ligne

1. Crée un dépôt **public** sur GitHub et pousse ce dossier. GitHub Pages n'est gratuit que
   pour les dépôts publics, et les minutes d'Actions y sont illimitées. Les éditions seront donc
   publiques (le `robots.txt` demande aux moteurs de ne pas les indexer) ; les clés restent dans
   les secrets.
2. Dans *Settings > Secrets and variables > Actions*, ajoute les clés sous les mêmes noms que
   dans `.env`.
3. Dans *Settings > Pages*, choisis *Deploy from a branch*, branche `main`, dossier `/docs`.
4. Dans l'onglet *Actions*, lance « Édition du matin » à la main avec une limite de 5 articles.

L'édition se lit alors à `https://Ilyas6810.github.io/Application-actu-quotidienne/editions/AAAA-MM-JJ.json`.

## Écarts avec le cahier des charges

- **Regroupement multilingue.** TF-IDF seul ne rapproche pas une dépêche française d'une
  dépêche anglaise, et le cahier ne traduisait que les langues « exotiques ». Le regroupement
  mélange TF-IDF et des vecteurs multilingues calculés sur la machine (fastembed : gratuit, sans
  API), ce qui laisse tout le quota des modèles à la rédaction. Si les vecteurs manquent, retour
  au TF-IDF seul avec le seuil de 0,45 du cahier.
- **GDELT par les fichiers bruts.** L'API DOC bloque par adresse IP (refus dès la première
  requête lors des tests du 10 septembre 2026), et GitHub Actions partage ses adresses. Le radar
  lit les fichiers publiés toutes les 15 minutes, sans limite d'accès.
- **Sources.** Testées une par une le 10 septembre 2026. AP, Les Échos, NHK World,
  Mail & Guardian, l'Élysée, l'INSEE, Légifrance, Eurostat, le FMI, l'OCDE, la Banque mondiale,
  l'OTAN et l'OMS n'ont plus de flux exploitable ou bloquent les robots. Elles restent dans
  `sources.yaml`, désactivées, et leurs liens sont reconnus quand GDELT ou Wikipédia les citent.
  Ajouts : Le Figaro (équilibre politique des sources françaises), L'Équipe (sport),
  ONU Info santé (à la place de l'OMS).
- **Modèles.** Llama 3.3 70B n'est plus gratuit chez Groq ni chez OpenRouter. La cascade passe
  par six modèles Gemini. Une seule clé suffit, et chaque modèle a son propre quota gratuit de
  20 requêtes par jour : 3.8, 3.7, 3.6 et 3.5 Flash,
  3.5 et 3.1 Flash-Lite. Les modèles 2.5 ne sont plus ouverts aux nouveaux comptes. Viennent
  ensuite gpt-oss-120b chez Groq, Gemma 4 chez OpenRouter, et
  Mistral en dernier recours.
- **Contrôles.** Un sixième contrôle vérifie que chaque nombre de l'article figure dans les
  sources. Les tirets cadratins sont remplacés par des virgules au lieu de faire rejeter
  l'article. Une longueur hors format reclasse l'article dans un format plus court (marge de
  10 %) au lieu de le rejeter. Une source officielle qui confirme seule un fait la concernant
  suffit avec un seul lien : c'est la règle de la section 4, que le contrôle n° 2 contredisait.
- **Articles de fond.** Réservés aux sujets suivis par au moins cinq sources indépendantes. Un
  résumé RSS fait deux ou trois phrases : 800 mots sans matière pousseraient le modèle à inventer.
- **File d'attente.** Un sujet à une seule source reste 72 heures dans le pool et il est
  réévalué à chaque passage.
- **Pied d'article.** Il liste toutes les sources données au modèle, une par titre de presse.
- **Dépôt public.** Obligatoire pour Pages gratuit : l'option « dépôt privé, quatre cycles » du
  cahier ne donne pas accès à Pages sans abonnement.

## Limites à connaître, en plus de celles du cahier

- Une notification locale programmée pour 6 h ne connaît pas les titres du jour. Pour les
  avoir, le workflow envoie une notification push à 6 h (secret `EXPO_PUSH_TOKEN`, jeton affiché
  par l'application). Sans jeton, l'application garde une notification locale générique.
- expo-speech n'offre pas de contrôles sur l'écran verrouillé (pas de session média). À traiter
  à l'étape 6.
- GitHub désactive les workflows planifiés d'un dépôt public après 60 jours sans activité. Les
  commits quotidiens de l'édition devraient suffire ; sinon, réactive-les dans l'onglet *Actions*.
