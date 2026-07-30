# Backoffice — mémo de lancement

Rappel rapide des commandes. Documentation complète : [README racine](../README.md).

> Toutes les commandes sauf la première se lancent **depuis la racine du dépôt**,
> avec le venv actif (`source .venv/bin/activate`).

## Terminal 1 — Backoffice (`:8000`)

Uvicorn charge `main:app`, il faut donc être **dans ce dossier** :

```bash
cd backoffice
uvicorn main:app --port 8000
```

## Terminal 2 — Serveur MCP (`:8010`)

```bash
STOCK_DB_PATH="$(pwd)/backoffice/inventory.db" python3 -m product_mcp_server.server
```

## Terminal 3 — Service IA (`:8001`)

```bash
python3 -m ai_service.app
```

## Terminal 4 — Pages web (`:8080`)

```bash
python3 -m http.server 8080 --directory backoffice
```

- Backoffice : http://127.0.0.1:8080/login.html
- Client public : http://127.0.0.1:8080/index.html

## Avant la première utilisation

L'API Produit doit tourner sur `:5001`, et la base doit être créée :

```bash
cd backoffice && python3 seed_data.py && cd ..
```

Comptes créés : `admin` / `admin123` et `employe_paris` / `employe123`.
Le script est rejouable : il remet le stock aux valeurs de référence.

`create_admin.py` fait la même chose pour le seul compte administrateur, sans
toucher aux boutiques ni au stock. Utile quand la base existe déjà et qu'on veut
uniquement s'assurer que l'admin est présent :

```bash
cd backoffice && python3 create_admin.py
```

## Tests

```bash
cd backoffice && python3 test_backoffice.py    # 34 tests
```
