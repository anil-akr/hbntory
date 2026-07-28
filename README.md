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
| **Backoffice** | [`backoffice/`](backoffice/) | FastAPI + SQLAlchemy | API interne (auth JWT, users, stock), + le front public (`index.html`) |
| **Base de données** | `backoffice/inventory.db` | SQLite | users, boutiques, stock (par SKU) — aucun détail produit |
| **Serveur MCP** | [`product_mcp_server/`](product_mcp_server/) | FastMCP | Pont : 5 outils (produits via l'API externe, stock via la base) |
| **Service IA** | [`ai_service/`](ai_service/) | Flask + Groq | Agent (boucle d'outils) exposé en REST : `POST /ask` |
| **API Produit** | *(fournie)* | — | Catalogue produit externe, lecture seule |

Documentation d'architecture et décisions : [`docs/`](docs/) (`architecture.md`,
`communication-decisions.md`, `mvp.md`). Authentification & autorisation :
[`docs/auth.md`](docs/auth.md).

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
STOCK_DB_PATH="$(pwd)/backoffice/inventory.db" MCP_PORT=8010 \
  python -m product_mcp_server.server

# 4. Service IA (lit la clé depuis .env) -> :8001
MCP_SERVER_URL="http://127.0.0.1:8010/mcp" python -m ai_service.app

# 5. Front public -> :8080  (ouvrir http://127.0.0.1:8080/index.html)
python -m http.server 8080 --directory backoffice
```

> Le serveur MCP tourne sur `:8010` pour ne pas entrer en conflit avec le
> Backoffice (`:8000`). Sans `STOCK_DB_PATH`, l'IA lit un stock d'exemple
> (`product_mcp_server/stock_data.json`) et fonctionne en autonomie.

### Variante Docker (Serveur MCP + Service IA seulement)
```bash
docker compose up --build   # MCP (:8000, interne) + Service IA (:8001)
```

## Tester

```bash
# Outils MCP seuls (aucune clé requise)
python -m product_mcp_server.test_client

# Agent complet (démarre le MCP, pose les 4 types de questions)
python scripts/e2e_test.py
```

## Démonstration : couvre les points de l'énoncé
- **Auth Backoffice** + **gestion du stock par un employé** (`employe_paris`, limité à sa boutique) + **gestion des utilisateurs par l'admin** (`admin`) → via `http://127.0.0.1:8000/docs`.
- **Questions produits & stock** via le front (`:8080`) → réponses ancrées de l'agent (produit + stock).

## Équipe
Projet réalisé en binôme :

- **Anil Aker** — Serveur MCP (produits + stock) et Service IA (agent + API REST).
- **Marie Lopez** — Backoffice (auth, utilisateurs, stock), base de données et front public.

## Limitations connues
- **API Produit externe requise :** les infos produit ne sont pas mises en cache. Si
  l'API (`:5001`) est indisponible, le Backoffice et l'agent renvoient une erreur
  claire (502/503) au lieu d'inventer.
- **Groq (offre gratuite) :** quotas et limites de débit ; certaines IP (VPN) peuvent
  être bloquées par Cloudflare (403). Chaque membre utilise sa propre clé.
- **Dépendance `passlib` :** `passlib` 1.7.4 n'est plus maintenu ; `bcrypt` est
  épinglé `< 4.1` dans `requirements.txt` pour rester compatible.
- **Clé de signature :** `SECRET_KEY` a une valeur de **développement** par défaut ;
  il faut définir la variable d'environnement `SECRET_KEY` en production.
- **Jetons JWT non révocables :** un jeton reste valide jusqu'à son expiration
  (30 min). Le soft delete bloque au login, mais un jeton déjà émis reste utilisable
  jusqu'à expiration. Pas de refresh token.
- **Base SQLite mono-fichier :** adaptée à la démo, pas à une forte charge concurrente.

## Convention de code
Commentaires et docstrings en anglais ; documentation en français.
