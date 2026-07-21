# Registre de décisions — Stratégies de communication (Task 0)

Ce document répond à la sous-tâche 2 de la Task 0 : pour chaque point de communication
du système, on indique **l'option retenue**, son **bénéfice principal** et son
**principal compromis (trade-off) / limite**.

Principe directeur (rappelé par l'énoncé) : *« You are not expected to choose the most
complex option »*. On choisit ce qui correspond au besoin réel et à la capacité de l'équipe.

---

## Décision 1 — Backoffice : rendu des pages

**Option retenue : REST + HTML/CSS/JS.**
Le Backoffice expose une API REST (JSON) et un front-end en HTML/CSS/JavaScript
consomme cette API (`fetch`) et met à jour la page sans rechargement complet.

- **Bénéfice principal :** séparation nette front / back, interface plus fluide (pas de
  rechargement de page), et une API structurée et testable indépendamment.
- **Trade-off / limite :** plus de travail qu'un rendu côté serveur (SSR) — il faut
  construire l'API **et** le front **et** gérer l'état + l'authentification côté
  JavaScript. À noter : cette API du Backoffice n'est consommée que par son propre
  front-end (aucun autre service ne l'appelle — le Service IA lit le stock via le
  Serveur MCP, pas via le Backoffice). Ce coût est assumé pour garder un front dynamique.

---

## Décision 2 — Client Web ↔ Service IA

**Option retenue : REST.**
Chaque question du visiteur est envoyée en une requête HTTP (POST) au Service IA, qui
renvoie une réponse JSON. Une question = une requête = une réponse.

- **Bénéfice principal :** simplicité maximale et sans état. Cela colle exactement à
  l'énoncé, qui précise que **chaque question est indépendante** et qu'aucun historique de
  conversation n'est requis. Facile à implémenter, à tester (curl) et à déboguer.
- **Trade-off / limite :** pas de streaming de la réponse. L'utilisateur attend la réponse
  **complète** (qui peut prendre quelques secondes, car l'agent appelle plusieurs outils)
  sans retour intermédiaire, et il n'y a pas d'effet « chat en direct » token par token.
  Un passage à WebSocket/SSE reste possible plus tard si on veut du streaming.

---

## Décision 3 — Service IA ↔ outils MCP

**Option retenue : MCP via Streamable HTTP.**
Le Serveur MCP tourne comme un **service réseau indépendant** (son propre conteneur dans
le docker-compose). Le Service IA s'y connecte comme **client MCP** via le transport HTTP.

- **Bénéfice principal :** le Serveur MCP reste une brique indépendante et déployable
  seule, cohérente avec l'architecture (composant séparé) et avec un docker-compose
  multi-conteneurs. Depuis le réseau Compose, le MCP peut joindre à la fois le Product API
  (HTTP) et la base de données. Le découplage est propre : le Service IA ne touche jamais
  la base directement, il passe toujours par les outils MCP.
- **Trade-off / limite :** un peu plus de configuration (un port, une URL de service, le
  réseau) que le transport **stdio**, où le Service IA lancerait le Serveur MCP comme
  simple sous-processus — plus rapide à câbler, mais alors couplé au même conteneur et non
  déployable séparément. On accepte ce léger surcoût pour préserver l'indépendance des services.

---

## Décision liée — Accès de l'IA aux données de stock

Rappel (déjà tranché dans `architecture.md`, §5, exigence MCP) : l'IA accède au stock en
**étendant notre propre Serveur MCP** avec des outils de stock en lecture, plutôt que
d'utiliser un MCP tiers de base de données. Bénéfice : un seul composant à maintenir et une
frontière unique et contrôlée. Trade-off : ces outils de stock sont à écrire par l'équipe.
