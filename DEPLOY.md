# Publier MatchScope sur Internet

## Avant de commencer

Les clés API ont été trouvées en clair dans les anciens scripts. Il faut les révoquer/remplacer chez leurs fournisseurs avant publication. Déplacer une clé dans une variable d'environnement ne retire pas son ancienne valeur de l'historique Git.

Prépare:
- un compte GitHub avec ce projet dans un dépôt privé;
- un compte Render;
- une clé Football-Charts et une clé Live Football valides;
- un identifiant et un mot de passe longs réservés à MatchScope.

Ne mets jamais les vraies clés dans `.env.example`, `render.yaml`, le code ou le dépôt.

## Déploiement Render

1. Vérifie que `.env` est ignoré par `.gitignore`. N'ajoute aucun cache contenant des données privées ou jetons au dépôt.
2. Envoie le code sans `.env` vers un dépôt GitHub privé.
3. Dans Render, choisis **New > Blueprint** et connecte ce dépôt. Render lit `render.yaml`.
4. Dans les variables d'environnement du service, saisis `FC_API_KEY`, `LIVE_FOOTBALL_KEY`, `WEB_AUTH_USERNAME` et `WEB_AUTH_PASSWORD`. Ces valeurs restent dans Render, pas dans Git.
5. Déploie le service. Render affiche une adresse HTTPS telle que `https://matchscope-football.onrender.com`.
6. Ouvre cette adresse. Le navigateur demande l'identifiant et le mot de passe configurés.

Le service utilise automatiquement `PORT` et écoute sur `0.0.0.0`. `/health` est le contrôle de santé public; l'application et toutes ses API sont protégées par HTTP Basic Auth en production.

## Limites à connaître

Le Blueprint utilise actuellement le plan `free`: selon les conditions Render en vigueur, le service peut s'endormir après une période sans trafic et mettre du temps à redémarrer. Le système de fichiers du service gratuit est éphémère: le cache local peut disparaître après un redéploiement ou redémarrage. Ne considère pas ce cache comme permanent.

Le passage au public rend le service accessible depuis Internet, mais ne donne pas une adresse IP privée à chaque utilisateur. Le mot de passe est commun au service; ne le partage qu'avec les personnes autorisées. Pour plusieurs utilisateurs, il faudra une vraie gestion de comptes.

Le flux de matchs et les analyses continuent à consommer les quotas API habituels. L'authentification protège l'accès; elle ne limite pas encore le nombre d'appels par utilisateur.

## Exécution locale

Pour développer en local, copie `.env.example` vers `.env`, renseigne les clés localement et lance:

```powershell
.\.venv\Scripts\python.exe main.py
```

Les variables d'authentification ne sont obligatoires qu'en production. Ne publie jamais ton `.env`.
