# Serveur MCP produit (Task 4 + outils stock de la Task 5)

Pont (**bridge**) entre le système IA et les données. L'agent appelle des
**outils MCP** au lieu d'inventer. Le serveur ne garde rien : les données
produit sont relayées depuis l'API Produit externe (lecture seule), le stock est
lu depuis l'inventaire.

- Techno : SDK MCP Python (`mcp==1.28.1`), classe `FastMCP`.
- Transport : **Streamable HTTP**, sur `http://127.0.0.1:8000/mcp`.
- Appels réseau : `urllib` (bibliothèque standard), comme l'API Produit elle-même.
- Tout tient dans un seul fichier : `server.py`. Chaque fonction décorée
  `@mcp.tool()` devient un outil disponible pour l'agent.

## Les 5 outils exposés

### Outils produit (relayés vers l'API externe)

**`list_products(search="", limit=20)`** — liste les produits du catalogue.
- Entrée : `search` (nom / SKU / description / tag ; vide = tout), `limit` (1 à 100).
- Sortie : `{ "count": <total>, "products": [ { sku, name, category, unit_price, currency }, ... ] }`

**`get_product(identifier)`** — détails d'un produit par SKU (ex. `HB-LAP-1001`) ou id.
- Sortie : `{ sku, name, description, category, brand, unit_price, currency, supplier_name, tags }`

> On n'expose **que** ces champs utiles : on évite de relayer tout le comportement
> de l'API Produit (pagination avancée, tri, filtres prix…).

### Outils stock (lus depuis l'inventaire)

**`stock_for_product(sku)`** — dans quelles boutiques le produit est disponible.
- Sortie : `{ "sku": ..., "availability": [ { branch, quantity }, ... ] }` (boutiques à 0 exclues)

**`stock_in_branch(branch)`** — ce qu'une boutique a en stock.
- Sortie : `{ "branch": ..., "products": [ { sku, quantity }, ... ] }`

**`check_shopping_list(items)`** — où acheter une liste : une boutique, ou plusieurs combinées.
- Entrée : `items` = liste de `{ "sku": ..., "quantity": ... }`
- Sortie : `{ "fully_satisfied_by": [boutiques qui suffisent seules], "satisfiable": bool, "plan": [{ branch, take: {sku: qté} }], "missing": {sku: manque} }`
- `plan` propose une **combinaison de boutiques** (heuristique gloutonne) quand aucune ne suffit à elle seule ; `missing` liste ce qui manque si la liste n'est pas satisfaisable sur tout le réseau.

> **Source du stock (`STOCK_DB_PATH`) :** par défaut, les outils stock lisent
> `stock_data.json` (bouchon, pour tourner en autonomie). Si la variable
> d'environnement `STOCK_DB_PATH` pointe vers la base du Backoffice
> (`inventory.db`), ils lisent le **vrai stock**, en **lecture seule**. Seule la
> fonction `_load_branches()` diffère selon la source ; les noms d'outils et les
> formats de sortie sont identiques, donc l'agent n'est jamais impacté.

## Format des réponses

Les outils renvoient un `dict` Python. Le serveur le sérialise en **JSON envoyé
en contenu texte** — c'est le format standard MCP, et c'est ce que lit l'agent.

## Lancer

```bash
# 1. L'API Produit doit tourner (depuis le dépôt du pack) :
docker compose -f /home/xom/hbntory-products-api/docker-compose.yml up -d

# 2a. Serveur MCP avec le stock d'exemple (autonome) :
python -m product_mcp_server.server

# 2b. OU serveur MCP branché sur la VRAIE base du Backoffice (stock réel, lecture seule) :
STOCK_DB_PATH=/chemin/vers/backoffice/inventory.db python -m product_mcp_server.server

# Conflit avec le Backoffice (lui aussi sur :8000) ? Change le port du MCP :
#   MCP_PORT=8010 python -m product_mcp_server.server
#   puis lance le Service IA avec  MCP_SERVER_URL=http://127.0.0.1:8010/mcp
```

## Tester manuellement (preuve de test)

Serveur MCP lancé, dans un autre terminal :

```bash
python -m product_mcp_server.test_client
```

Sortie réelle obtenue :

```
=== 1. Available tools ===
- list_products : List products from the external catalog.
- get_product : Return the details of one product by SKU (e.g. 'HB-LAP-1001') or numeric id.
- stock_for_product : Show how much of a product is available in each branch.
- stock_in_branch : List the products (and quantities) currently in stock in one branch.
- check_shopping_list : Check which branch(es) can satisfy a shopping list.

=== 2. list_products(search='keyboard', limit=5) ===
{ "count": 2, "products": [ {"sku": "HB-KBD-4102", "name": "Compact Keyboard ES", ...},
                            {"sku": "HB-KBD-4101", "name": "Mechanical Keyboard EN", ...} ] }

=== 3. get_product('HB-LAP-1001') ===
{ "sku": "HB-LAP-1001", "name": "Holberton Student Laptop 14", "unit_price": 799.0,
  "supplier_name": "Holberton Tools Co.", ... }

=== 4. get_product('NOPE-999') -> clear error expected ===
isError = True
message = Error executing tool get_product: Product not found in the catalog.
```

Cas limites également vérifiés :

```
API Produit arrêtée      -> ProductApiError: The Product API is unreachable.
check_shopping_list avec un item sans 'quantity'
                         -> isError = True
                            Error executing tool check_shopping_list:
                            Each item needs a 'sku' and a 'quantity'.
stock_in_branch('Nowhere')   -> {"branch": "Nowhere", "products": []}
stock_for_product('FAKE-000')-> {"sku": "FAKE-000", "availability": []}
```

## Gestion des erreurs (jamais d'échec silencieux)

Toute la logique réseau passe par une seule fonction (`_get_json`), qui traduit
chaque problème en message clair renvoyé à l'agent :

| Situation | Message renvoyé |
|---|---|
| Produit inexistant (404) | `Product not found in the catalog.` |
| API en erreur (autre code HTTP) | `The Product API responded with status N.` |
| API injoignable (réseau / timeout) | `The Product API is unreachable.` |
| Item de liste d'achats incomplet | `Each item needs a 'sku' and a 'quantity'.` |

Quand un outil lève une erreur, FastMCP la renvoie au client avec `isError = True`
et le message ci-dessus : l'agent sait que l'appel a échoué **et pourquoi**.
