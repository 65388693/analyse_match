# Publier MatchScope sur Internet

## Avant de commencer

Les clés API ont été trouvées en clair dans les anciens scripts. Il faut les révoquer/remplacer chez leurs fournisseurs avant publication. Déplacer une clé dans une variable d'environnement ne retire pas son ancienne valeur de l'historique Git.

Prépare:
- un compte GitHub avec ce projet dans un dépôt privé;
- un compte Render;
- des clés Football-Charts, Live Football et The Odds API valides;

Ne mets jamais les vraies clés dans `.env.example`, `render.yaml`, le code ou le dépôt.

## Déploiement Render

1. Vérifie que `.env` est ignoré par `.gitignore`. N'ajoute aucun cache contenant des données privées ou jetons au dépôt.
2. Envoie le code sans `.env` vers un dépôt GitHub privé.
3. Dans Render, choisis **New > Blueprint** et connecte ce dépôt. Render lit `render.yaml`.
4. Dans les variables d'environnement du service, saisis `FC_API_KEY`, `LIVE_FOOTBALL_KEY` et `ODDS_API_KEY`. Ces valeurs restent dans Render, pas dans Git.
5. Déploie le service. Render affiche une adresse HTTPS telle que `https://matchscope-football.onrender.com`.
6. Ouvre cette adresse. Le site est accessible sans compte.

Le service utilise automatiquement `PORT` et écoute sur `0.0.0.0`. `/health`, le site et ses API sont publics, sans authentification.

## Limites à connaître

Le Blueprint utilise actuellement le plan `free`: selon les conditions Render en vigueur, le service peut s'endormir après une période sans trafic et mettre du temps à redémarrer. Le système de fichiers du service gratuit est éphémère: le cache local peut disparaître après un redéploiement ou redémarrage. Ne considère pas ce cache comme permanent.

Toute personne qui connaît l'adresse du service peut accéder au site et appeler ses API. Un dépôt GitHub privé ne rend pas l'application Render privée. Ne publie pas de données ou fonctions qui doivent rester réservées à certaines personnes.

Le calendrier, les analyses et les cotes consomment les quotas API habituels. Les cotes 1X2 sont récupérées à l'ouverture de la fiche du match et gardées en cache côté serveur pendant 90 secondes par compétition. Le service ne comporte pas de contrôle d'accès ni de limite d'appels par utilisateur.

Les simples proposés et leurs résultats sont conservés dans `data/predictions.sqlite3`. Le plan gratuit utilise un stockage éphémère : cette base peut disparaître lors d'un redémarrage ou redéploiement. Pour conserver l'historique de performance, configurer un stockage persistant avant de s'y fier.

## Exécution locale

Pour développer en local, copie `.env.example` vers `.env`, renseigne les clés localement et lance:

```powershell
.\.venv\Scripts\python.exe main.py
```

Ne publie jamais ton `.env`.
