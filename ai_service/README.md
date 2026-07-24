# Service IA (Task 5)

Backend indépendant qui répond aux questions publiques sur produits et stock,
via un agent connecté au serveur MCP produit.

- Modèle : **Groq** (`llama-3.3-70b-versatile` par défaut), SDK `groq==1.5.0`.
- Endpoint : Flask, `POST /ask` (REST).
- Agent : boucle d'outils manuelle (voir `agent.py`), affiche chaque appel d'outil.
- Types de questions supportés : voir `supported_questions.md`.

> **Agnostique du fournisseur :** seul `agent.py` dépend du modèle. Le serveur
> MCP, ses 5 outils et l'endpoint Flask ne changent pas si on change de modèle
> ou de fournisseur. Le projet a d'ailleurs migré Anthropic → Gemini → Groq
> sans toucher au reste.

> **Contrat avec le front :** le Client Web (réalisé par la binôme) appelle
> `POST /ask`. Les en-têtes CORS de `app.py` sont là pour ça, car la page est
> servie sur un autre port.

## Clé API (gratuite, sans carte bancaire)

1. Va sur **https://console.groq.com/keys** et crée une clé (elle commence par `gsk_`).
2. À la racine du dépôt : `cp .env.example .env`, puis colle ta clé dans `.env`
   (`GROQ_API_KEY=gsk_...`). Le fichier `.env` est gitignoré.

## Lancer (3 terminaux, depuis la racine du dépôt, venv actif)

```bash
# 1. API Produit (conteneur fourni)
docker compose -f /home/xom/hbntory-products-api/docker-compose.yml up -d

# 2. Serveur MCP (produits + stock)
python -m product_mcp_server.server

# 3. Service IA
export GROQ_API_KEY="gsk_..."
python -m ai_service.app
```

## Tester

```bash
# Test complet en une commande (lit la clé depuis .env) :
./.venv/bin/python scripts/e2e_test.py

# Ou directement l'agent en ligne de commande :
export GROQ_API_KEY="gsk_..."
python -m ai_service.agent "Quelle boutique a du HB-LAP-1001 ?"

# Ou via l'endpoint HTTP :
curl -s -X POST http://127.0.0.1:8001/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Quels produits trouve-t-on a Lyon Part-Dieu ?"}'
```
