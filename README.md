# MatchScope

Application web Python pour parcourir les matchs de football et consulter des analyses statistiques, des probabilités de marchés et, lorsqu'elles sont disponibles, des cotes 1X2.

## Fonctionnalités

- Interface organisée en onglets Calendrier, Pronostics et Performance, avec navigation clavier, historique précédent/suivant et liens profonds par fragment d’URL.
- Calendrier des matchs, recherche et filtres par date, pays, compétition, statut et disponibilité des données.
- Analyse de buts attendus avec un modèle Poisson et correction Dixon-Coles, forme récente et ajustement heuristique des blessures.
- Marchés dérivés : 1X2, double chance, totaux, BTTS, scores exacts, handicaps, mi-temps, corners et cartons lorsque les données le permettent.
- Cotes 1X2 de The Odds API affichées dans la fiche du match, avec les bookmakers disponibles et les meilleures cotes.
- Suggestions quotidiennes de simples et de combinés prudents (2 à 10), moyens (10 à 100) et grosses cotes (100+), limitées aux cotes 1X2 explicitement identifiées comme provenant de 1xBet.
- Enregistrement local SQLite des simples présentés, règlement automatique après récupération du score final et tableau de résultats historiques (réussite, Brier, log-loss et rendement simulé).
- Cache local des réponses fournisseurs et analyse des matchs déjà présents dans le cache sans nouveaux appels API.
- Limites de fréquence locales par route API et déduplication des requêtes Odds API concurrentes.
- Favoris, notifications de changements et rafraîchissement du calendrier en direct dans le navigateur.

Les probabilités sont des estimations statistiques, pas des garanties ni des conseils de mise. Une compétition peut ne pas être couverte par les sources ou ne pas avoir de cotes disponibles.

## Configuration locale

1. Copier `.env.example` vers `.env`.
2. Renseigner au minimum `FC_API_KEY`. `LIVE_FOOTBALL_KEY` active le calendrier global et les données live; `ODDS_API_KEY` active les cotes. `ODDS_API_KEY` est facultative.
3. Installer les dépendances listées dans `requirements.txt`.
4. Démarrer le serveur avec `python web_app.py`, puis ouvrir `http://localhost:8765`.

Ne jamais committer `.env` ni publier une vraie clé dans `.env.example` ou dans le code. Le fichier `.env` est ignoré par Git.

## Cotes

Les cotes sont demandées lorsqu'une fiche de match est ouverte. Le serveur met les réponses en cache pendant 90 secondes par compétition afin de limiter les appels payants. Le bouton d'actualisation force une nouvelle demande. The Odds API ne fournit pas nécessairement les cotes de toutes les compétitions ni des matchs terminés.

Le fournisseur retourne les cotes disponibles pour son marché 1X2; la couverture des bookmakers dépend de la région (`eu`) et de l'événement. Les cotes restent distinctes des probabilités calculées par le modèle.

Le générateur quotidien n'utilise que les profils d'équipe déjà en cache, afin d'éviter de déclencher une série d'appels Football-Charts. Il ne produit pas de proposition pour les marchés ou matchs non couverts, et peut retourner moins de cinq combinés par niveau, voire aucun. Un combiné ne répète ni équipe ni rencontre. Les probabilités combinées sont le produit des probabilités du modèle, sous hypothèse d'indépendance entre matchs; elles ne sont pas calibrées sur les résultats réels des paris 1xBet et ne garantissent aucun gain.

Les trois probabilités 1/N/2 et les simples affichés sont enregistrés séparément dans `data/predictions.sqlite3`. Le premier snapshot d'une sélection pour une version de modèle est conservé; une actualisation ultérieure ne remplace pas rétroactivement ses cotes ou probabilités. Le score final est associé automatiquement lorsqu'un calendrier contenant le match terminé est chargé. Brier, log-loss et calibration évaluent le résultat 1X2 complet; réussite et rendement simulé sont calculés séparément sur les simples effectivement proposés. Les métriques affichent le volume réglé et restent indicatives tant qu'il est faible. La base locale est ignorée par Git.

## Gestion des requêtes

Les routes API ont des plafonds locaux glissants par adresse cliente : calendrier (20/min), cotes (12/min), analyse d'un match (8/min), pronostics quotidiens (1/30 s), analyse du cache (2/15 s) et statistiques (30/min). Un dépassement renvoie HTTP `429` avec `Retry-After`. Les demandes Odds API simultanées pour la même compétition partagent un chargement, puis réutilisent le cache de 90 secondes.

Ces limites sont conservées en mémoire du processus : elles conviennent à l'application personnelle sur une instance locale. Elles ne coordonnent pas plusieurs processus et se réinitialisent au redémarrage.

## Déploiement Render

Le Blueprint est défini dans `render.yaml`. Configurer dans Render les secrets `FC_API_KEY`, `LIVE_FOOTBALL_KEY` et `ODDS_API_KEY`, puis déployer le service. Le serveur écoute sur `0.0.0.0` et utilise la variable `PORT` fournie par la plateforme.

Le site et ses routes API sont publics, sans authentification. Toute personne qui connaît l'URL peut consulter les matchs et déclencher les appels fournisseurs; surveiller les quotas et ne pas y exposer de données privées. Sur le plan gratuit, le cache local et la base `data/predictions.sqlite3` peuvent être perdus au redémarrage ou au redéploiement; les performances historiques ne sont alors pas conservées sans stockage persistant.

Les détails de publication sont dans [DEPLOY.md](DEPLOY.md).

## Tests

Les tests automatisés du dépôt se lancent avec `python -m unittest`. Ils vérifient des invariants des marchés, l'analyse depuis le cache, le calcul des moyennes domicile/extérieur et quelques comportements des routes web.