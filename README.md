# hbntory

Système de gestion d'inventaire pour une entreprise de retail **multi-boutiques**.
Deux faces :

- un **Backoffice** interne (authentifié) où les employés gèrent le stock de leur
  boutique et où l'admin gère les utilisateurs ;
- une **interface publique** où un visiteur pose des questions en langage naturel
  sur les produits et le stock, et où un **agent IA** répond en s'appuyant
  **uniquement** sur des outils — sans jamais inventer.

Les informations produit ne sont pas stockées localement : elles proviennent d'une
**API Produit externe** (fournie). La base ne garde que l'identifiant produit (SKU).

## Composants

| Composant | Dossier | Techno | Rôle |
|---|---|---|---|
| **Backoffice** | [`backoffice/`](backoffice/) | FastAPI + SQLAlchemy | API interne (auth JWT, users, stock) + son interface web (`login.html`, `employee.html`, `admin.html`) |
| **Client public** | [`backoffice/`](backoffice/) | HTML/CSS/JS | Page de questions en langage naturel (`index.html`), sans authentification |
| **Base de données** | `backoffice/inventory.db` | SQLite | users, boutiques, stock (par SKU) — aucun détail produit |
| **Serveur MCP** | [`product_mcp_server/`](product_mcp_server/) | FastMCP | Pont : 5 outils (produits via l'API externe, stock via la base) |
| **Service IA** | [`ai_service/`](ai_service/) | Flask + Groq | Agent (boucle d'outils) exposé en REST : `POST /ask` |
| **API Produit** | *(fournie)* | — | Catalogue produit externe, lecture seule |

Documentation d'architecture et décisions : [`docs/`](docs/) (`architecture.md`,
`communication-decisions.md`, `mvp.md`). Authentification & autorisation :
[`docs/auth.md`](docs/auth.md).

### Organisation du dépôt

```
backoffice/           API interne (FastAPI) + base SQLite + front public
product_mcp_server/   serveur MCP : 5 outils (produits + stock)
ai_service/           service IA indépendant : agent + POST /ask
docs/                 architecture, décisions, MVP, authentification
presentation/         support de soutenance (Task 8)
scripts/              test de bout en bout
```

> **Pourquoi pas de dossier `client_web/` ?** L'énoncé propose cette structure
> mais autorise une autre organisation justifiée. Le front public
> (`index.html`, `app.js`, `style.css`) est un trio de fichiers statiques sans
> build ni dépendance : il vit dans `backoffice/`, servi par le même
> `python -m http.server` que le reste du front. Un dossier séparé n'aurait
> contenu que ces trois fichiers. La **frontière logique** reste stricte : le
> front public ne parle qu'au Service IA (`POST /ask`), jamais au Backoffice,
> et n'exige aucune authentification.

> **Architecture agnostique du modèle :** seul `ai_service/agent.py` dépend du
> fournisseur d'IA (le projet a migré Anthropic → Gemini → **Groq** sans toucher au
> reste). Et l'IA accède au stock **uniquement** via les outils du serveur MCP —
> jamais la base en direct.

## Prérequis

- Python 3.10+ (Docker **optionnel** — pratique pour l'API Produit et la variante
  conteneurs, mais tout peut tourner en Python pur).
- **API Produit** (asset pack fourni) lancée sur `:5001`.
- **Clé Groq** gratuite (https://console.groq.com/keys) dans un fichier `.env`
  à la racine : `GROQ_API_KEY=gsk_...` (le `.env` est gitignoré).

## Lancer la stack complète (1 terminal par service)

```bash
# venv + dépendances des 3 services
python3 -m venv .venv && source .venv/bin/activate
pip install -r backoffice/requirements.txt \
            -r product_mcp_server/requirements.txt \
            -r ai_service/requirements.txt

# 1. API Produit (fournie) -> :5001
#    a) avec Docker :
docker compose -f /home/xom/hbntory-products-api/docker-compose.yml up -d
#    b) OU sans Docker (le pack est un simple app.py, aucune dépendance) :
#       depuis le dossier du pack :  HBN_PRODUCTS_PORT=5001 python3 app.py

# 2. Backoffice : remplir la base une fois, puis lancer l'API -> :8000
cd backoffice && python seed_data.py && uvicorn main:app --port 8000 ; cd ..
#   comptes créés : admin / admin123   et   employe_paris / employe123
#   doc interactive : http://127.0.0.1:8000/docs

# 3. Serveur MCP branché sur la base du Backoffice -> :8010
STOCK_DB_PATH="$(pwd)/backoffice/inventory.db" python -m product_mcp_server.server

# 4. Service IA (lit la clé depuis .env) -> :8001
python -m ai_service.app

# 5. Interfaces web -> :8080
python -m http.server 8080 --directory backoffice
#   Backoffice     : http://127.0.0.1:8080/login.html
#   Client public  : http://127.0.0.1:8080/index.html
```

> Le serveur MCP écoute sur `:8010` par défaut, pour ne pas entrer en conflit
> avec le Backoffice (`:8000`) ; le Service IA l'y cherche par défaut aussi.
> Sans `STOCK_DB_PATH`, l'IA lit un stock d'exemple
> (`product_mcp_server/stock_data.json`) et fonctionne en autonomie.

### Variante Docker (Serveur MCP + Service IA seulement)
```bash
docker compose up --build   # MCP (:8010, interne) + Service IA (:8001)
```

## Tester

```bash
# Outils MCP seuls (aucune clé requise)
python -m product_mcp_server.test_client

# Agent complet (démarre le MCP, pose les 4 types de questions)
python scripts/e2e_test.py
```

## Exemples de questions (interface publique)

À taper dans le front (`:8080`) — un type de question par ligne :

| Question | Ce qu'elle démontre |
|---|---|
| « Donne-moi les détails du produit HB-MON-2101 » | Détails produit, venus de l'API externe |
| « Quelle boutique a du HB-LAP-1001 et en quelle quantité ? » | Disponibilité d'un produit dans toutes les boutiques |
| « Quels produits trouve-t-on à Lyon Part-Dieu ? » | Contenu du stock d'une boutique |
| « Je veux 3 HB-LAP-1001, 2 HB-MON-2101 et 4 HB-CAM-5101 : quelle boutique ou boutiques dois-je visiter ? » | Liste d'achats, une ou plusieurs boutiques |
| « Avez-vous des iPhone 15 Pro en stock ? » | Hors catalogue : l'agent dit qu'il n'a pas l'information |

Détail des types supportés et des outils appelés :
[`ai_service/supported_questions.md`](ai_service/supported_questions.md).

## Démonstration : couvre les points de l'énoncé

Interface Backoffice → `http://127.0.0.1:8080/login.html`

- **Authentification** : `employe_paris` / `employe123` arrive sur l'écran employé,
  `admin` / `admin123` sur l'écran administrateur (la redirection suit le rôle
  porté par le jeton).
- **Stock par un employé** : sa boutique est la seule proposée ; le tableau
  affiche le SKU, **le nom du produit venu de l'API externe** et la quantité.
  Une quantité négative ou un SKU absent du catalogue sont refusés.
- **Utilisateurs par l'admin** : création, modification (mot de passe, boutique),
  désactivation. Un compte désactivé reste visible, grisé, et ne peut plus se
  connecter. L'admin n'a aucun bouton de stock — et l'API le lui refuse aussi.
- **Questions produits & stock** : client public sur
  `http://127.0.0.1:8080/index.html` → réponses ancrées de l'agent.

L'API reste explorable sur `http://127.0.0.1:8000/docs`.

## Équipe
Projet réalisé en binôme :

- **Anil Aker** — Serveur MCP (produits + stock) et Service IA (agent + API REST).
- **Marie Lopez** — Backoffice (auth, utilisateurs, stock), base de données et front public.

## Limitations connues
- **API Produit externe requise :** les infos produit ne sont pas mises en cache. Si
  l'API (`:5001`) est indisponible, le Backoffice et l'agent renvoient une erreur
  claire (502/503) au lieu d'inventer. Conséquence assumée : **enregistrer du stock
  exige que l'API réponde**, car le SKU est validé auprès du catalogue avant
  écriture (un identifiant inconnu est refusé en 400).
- **Groq (offre gratuite) :** quotas et limites de débit ; certaines IP (VPN) peuvent
  être bloquées par Cloudflare (403). Chaque membre utilise sa propre clé.
- **Dépendance `passlib` :** `passlib` 1.7.4 n'est plus maintenu ; `bcrypt` est
  épinglé `< 4.1` dans `requirements.txt` pour rester compatible.
- **Clé de signature :** `SECRET_KEY` a une valeur de **développement** par défaut ;
  il faut définir la variable d'environnement `SECRET_KEY` en production.
- **Révocation partielle des jetons :** désactiver un compte invalide ses jetons
  **immédiatement** (l'utilisateur est rechargé à chaque requête en excluant les
  comptes supprimés). En revanche, un jeton ne peut pas être révoqué pour une
  autre raison — un changement de mot de passe, par exemple — avant son
  expiration (30 min). Pas de refresh token.
- **Base SQLite mono-fichier :** adaptée à la démo, pas à une forte charge concurrente.

## Convention de code
Commentaires et docstrings en anglais ; documentation en français.
