# hbntory

Système de gestion d'inventaire pour une entreprise de retail multi-boutiques.
Un visiteur peut poser des questions en langage naturel sur les **produits** et
le **stock** ; un agent IA répond en s'appuyant **uniquement** sur des outils, sans
rien inventer.

Ce dépôt (branche `ai-service`) contient **la partie IA du projet**. Le Backoffice,
la base de données et le front (Client Web) sont réalisés par la binôme, sur sa
branche. La documentation d'architecture complète est dans [`docs/`](docs/).

## Composants de cette branche

| Composant | Dossier | Rôle |
|---|---|---|
| **Serveur MCP produit** | [`product_mcp_server/`](product_mcp_server/) | Pont vers l'API Produit externe + accès stock. Expose 5 outils. |
| **Service IA** | [`ai_service/`](ai_service/) | Agent (boucle d'outils) exposé en REST : `POST /ask`. |
| Test de bout en bout | [`scripts/e2e_test.py`](scripts/e2e_test.py) | Pose une question de chaque type à l'agent. |

Les 5 outils MCP : `list_products`, `get_product` (produits, relayés depuis l'API
externe) et `stock_for_product`, `stock_in_branch`, `check_shopping_list` (stock).

> **Architecture agnostique du modèle :** seul `ai_service/agent.py` dépend du
> fournisseur d'IA. Le serveur MCP, ses outils et l'API REST ne changent pas si on
> change de modèle — le projet a migré Anthropic → Gemini → **Groq** sans toucher
> au reste.

## Prérequis

1. **API Produit** (fournie, conteneur Docker de l'asset pack) lancée sur le port 5001 :
   ```bash
   docker compose -f /home/xom/hbntory-products-api/docker-compose.yml up -d
   ```
2. **Clé Groq** (gratuite, sans carte) : https://console.groq.com/keys
   ```bash
   cp .env.example .env      # puis colle ta clé : GROQ_API_KEY=gsk_...
   ```
   Le fichier `.env` est gitignoré.

## Lancer — option A : Docker Compose (recommandé)

```bash
docker compose up --build
```
Lance les deux services : le MCP (`:8000`) et le Service IA (`:8001`). Le Service IA
interroge le MCP par le réseau Compose, et le MCP tape l'API Produit sur l'hôte.

## Lancer — option B : à la main (3 terminaux)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r product_mcp_server/requirements.txt -r ai_service/requirements.txt

# terminal 1 : serveur MCP
python -m product_mcp_server.server
# terminal 2 : service IA
python -m ai_service.app
```

Poser une question :
```bash
curl -s -X POST http://127.0.0.1:8001/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Which branch has stock of HB-LAP-1001?"}'
```

## Tester

```bash
# Outils MCP seuls (pas de clé requise) :
python -m product_mcp_server.test_client

# Agent complet (démarre le MCP, pose les 4 types de questions) :
./.venv/bin/python scripts/e2e_test.py
```

## À savoir

- **Le stock est un bouchon.** Les outils `stock_*` lisent
  `product_mcp_server/stock_data.json`, qui remplace temporairement la base
  d'inventaire partagée (côté Backoffice). À l'intégration, seule la fonction
  `_load_branches()` change ; les outils et leurs formats restent identiques.
- **Convention de code :** commentaires et docstrings en anglais ; documentation
  en français.
