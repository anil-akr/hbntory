# Explication du code — pour défendre à l'oral

Ce document explique **chaque bloc** des 3 fichiers de la partie IA (Anil) :

| Fichier | Rôle en une phrase |
|---|---|
| `product_mcp_server/server.py` | Le serveur MCP : expose 5 **outils** que l'agent appelle. |
| `ai_service/agent.py` | L'**agent** : parle au modèle, exécute les outils (la « boucle d'outils »). |
| `ai_service/app.py` | L'**API web** (Flask) : reçoit les questions du public sur `POST /ask`. |

> Astuce oral : si on te montre une ligne, dis d'abord **ce qu'elle fait**, puis **pourquoi elle est là**.

---

## Concepts Python à connaître (le jury peut demander)

- **`@mcp.tool()` (un « décorateur »)** : une étiquette au-dessus d'une fonction. Ici, elle **enregistre la fonction comme un outil** utilisable par l'agent. Sans elle, ce serait une fonction normale, invisible pour l'IA.
- **`async def` / `await` / `async with`** : du code **asynchrone**. On l'utilise pour parler sur le réseau (au MCP) **sans bloquer** le programme pendant qu'on attend la réponse.
- **`asyncio.run(...)`** : lance une fonction `async` depuis du code normal (synchrone). C'est le « pont » entre les deux mondes.
- **Liste en compréhension** `[x for e in liste if condition]` : une façon courte de construire une liste. Ex. « pour chaque boutique, garde celles qui ont le produit ».
- **`os.environ.get("X", défaut)`** : lit une variable d'environnement `X`, avec une valeur par défaut si elle n'existe pas. Sert à configurer sans écrire en dur dans le code.
- **`try / except ... from e`** : gestion d'erreur. Le `from e` garde la trace de l'erreur d'origine (chaînage).
- **f-string** `f"...{x}..."` : insère la valeur de `x` dans une chaîne de texte.

---

# 1) `product_mcp_server/server.py`

## Imports et configuration

```python
import json, os, urllib.error, urllib.parse, urllib.request
from mcp.server.fastmcp import FastMCP

PRODUCT_API_URL = os.environ.get("PRODUCT_API_URL", "http://localhost:5001")
REQUEST_TIMEOUT_SECONDS = 5
STOCK_FILE = os.path.join(os.path.dirname(__file__), "stock_data.json")

mcp = FastMCP("hbntory-products", host=os.environ.get("MCP_HOST", "127.0.0.1"))
```

- `json` : lire/écrire du JSON. `urllib` : faire des requêtes HTTP (bibliothèque **standard**, pas de dépendance en plus). `os` : lire l'environnement et construire des chemins.
- `FastMCP` : la classe du SDK MCP qui crée un serveur d'outils.
- `PRODUCT_API_URL` : l'adresse de l'API Produit. Par défaut en local ; on peut la changer avec une variable d'environnement (utile dans Docker).
- `REQUEST_TIMEOUT_SECONDS = 5` : si l'API ne répond pas en 5 s, on abandonne (évite de rester bloqué).
- `STOCK_FILE` : le chemin du fichier de stock, calculé **à côté de ce module** (marche quel que soit le dossier depuis lequel on lance).
- `mcp = FastMCP(...)` : **crée le serveur**. Le `host` par défaut est `127.0.0.1` (local) ; dans Docker on met `0.0.0.0` (via `MCP_HOST`) pour qu'un autre conteneur puisse le joindre.

## L'erreur maison

```python
class ProductApiError(Exception):
    """Clear error raised when the Product API is not found or unreachable."""
```
- On définit **notre propre type d'erreur**. Ça permet de renvoyer un message clair et de distinguer nos erreurs des autres.

## `_get_json` — le seul point qui parle au réseau

```python
def _get_json(path: str) -> dict:
    url = f"{PRODUCT_API_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as http_error:
        if http_error.code == 404:
            raise ProductApiError("Product not found in the catalog.") from http_error
        raise ProductApiError(f"The Product API responded with status {http_error.code}.") from http_error
    except (urllib.error.URLError, TimeoutError) as network_error:
        raise ProductApiError("The Product API is unreachable.") from network_error
```
- **Rôle :** appeler l'API Produit et renvoyer le JSON, ou lever une **erreur claire**.
- Le `_` devant le nom = fonction « privée » (usage interne, pas un outil).
- `urlopen(...)` fait la requête ; `.read().decode()` lit la réponse ; `json.loads(...)` la transforme en dictionnaire Python.
- **Les 3 cas d'erreur, centralisés ici** (c'est le point à souligner : « pas d'échec silencieux ») :
  - `404` → « produit introuvable »,
  - autre code HTTP → « l'API a répondu N »,
  - pas de réseau / timeout → « API injoignable ».
- **Pourquoi centraliser ?** Tous les outils passent par cette fonction → un seul endroit gère les erreurs, messages cohérents.

## Outil `list_products`

```python
@mcp.tool()
def list_products(search: str = "", limit: int = 20) -> dict:
    safe_limit = max(1, min(limit, 100))
    query = f"/api/v1/products?limit={safe_limit}"
    if search:
        query += "&q=" + urllib.parse.quote(search)
    data = _get_json(query)
    products = [
        {"sku": p["sku"], "name": p["name"], "category": p["category"],
         "unit_price": p["unit_price"], "currency": p["currency"]}
        for p in data["results"]
    ]
    return {"count": data["count"], "products": products}
```
- `@mcp.tool()` : cette fonction devient un **outil** pour l'agent.
- `search=""`, `limit=20` : arguments avec valeurs par défaut (l'agent peut ne pas les donner).
- `safe_limit = max(1, min(limit, 100))` : on **borne** entre 1 et 100 (sécurité : évite qu'on demande 10 000 produits).
- `urllib.parse.quote(search)` : encode le texte pour l'URL (gère les espaces/caractères spéciaux).
- La **liste en compréhension** ne garde **que 5 champs** utiles par produit → on n'expose pas tout le catalogue à l'IA (plus propre, moins de bruit).
- Retour : `{count, products}`.

## Outil `get_product`

```python
@mcp.tool()
def get_product(identifier: str) -> dict:
    data = _get_json(f"/api/v1/products/{urllib.parse.quote(identifier)}")
    return {"sku": ..., "name": ..., "description": ..., "brand": ..., "unit_price": ...,
            "currency": ..., "supplier_name": ..., "tags": ...}
```
- Récupère **un** produit par son SKU (ex. `HB-LAP-1001`) ou son id.
- Si le produit n'existe pas, `_get_json` lève « Product not found » → l'agent le saura.
- On renvoie un sous-ensemble **choisi** de champs (publics).

## `_load_branches` — la source de stock (le point d'intégration)

```python
def _load_branches() -> dict:
    with open(STOCK_FILE, "r", encoding="utf-8") as stock_file:
        return json.load(stock_file)["branches"]
```
- Lit le fichier `stock_data.json` et renvoie `{ boutique: { sku: quantité } }`.
- **Le point clé à dire au jury :** c'est **ici et seulement ici** qu'on lit le stock. À l'intégration, on remplace le contenu de cette fonction par une requête à la vraie base de Marie — **les outils ne changent pas**, donc l'agent non plus.

## Outil `stock_for_product`

```python
@mcp.tool()
def stock_for_product(sku: str) -> dict:
    branches = _load_branches()
    availability = [
        {"branch": branch_name, "quantity": stock[sku]}
        for branch_name, stock in branches.items()
        if stock.get(sku, 0) > 0
    ]
    return {"sku": sku, "availability": availability}
```
- Pour un produit, liste les boutiques qui en ont (**quantité > 0**).
- `stock.get(sku, 0)` : renvoie la quantité, ou `0` si le produit n'est pas dans cette boutique (évite une erreur).

## Outil `stock_in_branch`

```python
@mcp.tool()
def stock_in_branch(branch: str) -> dict:
    branches = _load_branches()
    stock = branches.get(branch, {})
    products = [{"sku": sku, "quantity": q} for sku, q in stock.items() if q > 0]
    return {"branch": branch, "products": products}
```
- Liste ce qu'une boutique a en stock.
- `branches.get(branch, {})` : si la boutique est inconnue → dictionnaire vide → liste vide (**pas de plantage**).

## `_coverage` et `_greedy_plan` — le cerveau de la liste d'achats

```python
def _coverage(stock: dict, remaining: dict) -> int:
    return sum(min(stock.get(sku, 0), quantity) for sku, quantity in remaining.items())
```
- **Rôle :** combien d'unités *encore nécessaires* une boutique peut fournir.
- Pour chaque produit voulu, on prend le **minimum** entre « ce qu'il reste à trouver » et « ce que la boutique a », et on additionne.

```python
def _greedy_plan(branches: dict, wanted: dict) -> list:
    remaining = dict(wanted)     # copie de ce qu'il reste à trouver
    unused = dict(branches)      # boutiques pas encore choisies
    plan = []
    while any(q > 0 for q in remaining.values()) and unused:
        best_branch = max(unused, key=lambda name: _coverage(unused[name], remaining))
        stock = unused.pop(best_branch)
        if _coverage(stock, remaining) == 0:
            break
        take = {}
        for sku, quantity in remaining.items():
            amount = min(stock.get(sku, 0), quantity)
            if amount > 0:
                take[sku] = amount
                remaining[sku] -= amount
        plan.append({"branch": best_branch, "take": take})
    return plan
```
- **Rôle :** choisir quelles boutiques visiter pour couvrir toute la liste (algorithme **glouton**).
- `while ... remaining > 0 and unused` : tant qu'il manque quelque chose ET qu'il reste des boutiques.
- `max(unused, key=lambda ...)` : on choisit la boutique qui **couvre le plus** de ce qui manque (c'est l'idée « gloutonne » : on prend le meilleur à chaque étape).
- `unused.pop(best_branch)` : on la retire (on ne la revisite pas → pas de boucle infinie).
- On note ce qu'on y prend (`take`), on **soustrait** du restant, et on recommence.
- **À dire au jury :** « glouton = simple et efficace ; ce n'est pas forcément le nombre minimal de boutiques, mais c'est clair et ça marche ».

## Outil `check_shopping_list`

```python
@mcp.tool()
def check_shopping_list(items: list) -> dict:
    for item in items:
        if "sku" not in item or "quantity" not in item:
            raise ValueError("Each item needs a 'sku' and a 'quantity'.")
    branches = _load_branches()
    wanted = {item["sku"]: item["quantity"] for item in items}

    fully_satisfied_by = [
        name for name, stock in branches.items()
        if all(stock.get(sku, 0) >= q for sku, q in wanted.items())
    ]
    total_available = {sku: sum(stock.get(sku, 0) for stock in branches.values()) for sku in wanted}
    missing = {sku: q - total_available[sku] for sku, q in wanted.items() if total_available[sku] < q}
    satisfiable = not missing

    plan = []
    if satisfiable and not fully_satisfied_by:
        plan = _greedy_plan(branches, wanted)

    return {"fully_satisfied_by": fully_satisfied_by, "satisfiable": satisfiable,
            "plan": plan, "missing": missing}
```
- **Validation d'entrée** : chaque article doit avoir `sku` et `quantity`, sinon erreur claire (pas de plantage bizarre).
- `wanted` : transforme la liste en `{ sku: quantité }`.
- `fully_satisfied_by` : boutiques qui couvrent **tout à elles seules** (`all(...)` = « tous les produits en quantité suffisante »).
- `total_available` : somme d'un produit sur **toutes** les boutiques → sert à savoir si c'est faisable.
- `missing` : ce qui manque sur tout le réseau ; `satisfiable = not missing` (vrai s'il ne manque rien).
- `plan` : on ne calcule la **combinaison** que si nécessaire (aucune boutique seule ne suffit) et possible.
- **Répond au « quelle(s) boutique(s) » (pluriel) de l'énoncé.**

## Lancement

```python
if __name__ == "__main__":
    mcp.run(transport="streamable-http")
```
- Si on lance ce fichier directement, on **démarre le serveur** en Streamable HTTP (sur `:8000/mcp`).

---

# 2) `ai_service/agent.py`

## Imports et constantes

```python
import asyncio, json, os
from groq import Groq
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8000/mcp")
MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
MAX_TOOL_ROUNDS = 5
SYSTEM_PROMPT = ("You are the HBntory assistant. ... Only use the information "
                 "returned by the tools. Never invent ... If the tools do not "
                 "provide the needed information, say clearly that ... unavailable.")
```
- `Groq` : le client du modèle. `ClientSession` + `streamablehttp_client` : le **client MCP** (pour parler au serveur d'outils).
- `MCP_SERVER_URL` : où joindre le MCP (configurable pour Docker).
- `MODEL` : le modèle utilisé (vérifié comme existant sur l'API). Configurable.
- `MAX_TOOL_ROUNDS = 5` : nombre max de tours d'outils → **jamais de boucle infinie**.
- `SYSTEM_PROMPT` : **le garde-fou anti-invention** : « utilise seulement les outils, n'invente jamais, dis si l'info manque ». C'est ce qui garantit le *grounding*.

## `_load_env_file` — lire la clé sans dépendance

```python
def _load_env_file() -> None:
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(repo_root, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())

_load_env_file()
```
- Lit le fichier `.env` (à la racine) et met chaque `CLÉ=VALEUR` dans l'environnement.
- On ignore les lignes vides et les commentaires (`#`).
- `setdefault` : ne remplace pas une variable déjà définie.
- Appelée **à l'import** → la clé est dispo pour l'app web ET la ligne de commande, sans `export` manuel.
- **Pourquoi maison ?** Pour ne pas ajouter une bibliothèque juste pour lire un petit fichier.

## `_get_api_key`

```python
def _get_api_key() -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set. Put it in a .env file at the repo root.")
    return api_key
```
- Récupère la clé, ou lève une erreur **claire** si elle manque (message qui dit quoi faire).

## `_to_groq_tools` — traduire les outils MCP pour le modèle

```python
def _to_groq_tools(mcp_tools):
    return [
        {"type": "function",
         "function": {"name": tool.name,
                      "description": (tool.description or "").strip(),
                      "parameters": tool.inputSchema}}
        for tool in mcp_tools
    ]
```
- Le modèle attend les outils dans un format précis (compatible OpenAI). On convertit chaque outil MCP dans ce format.
- **Point malin :** `tool.inputSchema` du MCP est **déjà** du JSON Schema → on le passe tel quel dans `parameters`, **aucune conversion manuelle**.

## `_tool_result_text`

```python
def _tool_result_text(result) -> str:
    if result.content and result.content[0].type == "text":
        return result.content[0].text
    return "(no content)"
```
- Extrait le **texte** du résultat d'un outil (le JSON renvoyé par le MCP), pour le redonner au modèle.

## `answer_question` — LA boucle d'outils (le cœur)

```python
async def answer_question(question: str) -> str:
    client = Groq(api_key=_get_api_key())
    async with streamablehttp_client(MCP_SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = _to_groq_tools((await session.list_tools()).tools)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ]

            for _ in range(MAX_TOOL_ROUNDS):
                response = client.chat.completions.create(
                    model=MODEL, messages=messages, tools=tools, tool_choice="auto")
                message = response.choices[0].message

                if not message.tool_calls:
                    return (message.content or "").strip()      # réponse finale

                messages.append(message.model_dump(exclude_none=True))  # garde la demande d'outil

                for call in message.tool_calls:
                    arguments = json.loads(call.function.arguments or "{}")
                    print(f"[tool call] {call.function.name}({arguments})")
                    result = await session.call_tool(call.function.name, arguments)
                    messages.append({"role": "tool", "tool_call_id": call.id,
                                     "content": _tool_result_text(result)})
            return "Sorry, I could not finish answering this question."
```
Ligne par ligne, l'histoire :
1. `client = Groq(...)` : on prépare le client du modèle avec la clé.
2. `async with streamablehttp_client(...)` puis `ClientSession(...)` : on **ouvre la connexion au serveur MCP**. `await session.initialize()` : poignée de main MCP.
3. `session.list_tools()` : on **demande la liste des outils** au MCP, puis on la traduit pour le modèle.
4. `messages` : l'historique de la conversation. On commence par le **prompt système** (les règles) + la **question** de l'utilisateur.
5. La boucle `for ... range(MAX_TOOL_ROUNDS)` (max 5 tours) :
   - `chat.completions.create(...)` : on envoie tout au modèle. `tool_choice="auto"` = le modèle décide s'il appelle un outil.
   - **Si `message.tool_calls` est vide** → le modèle a fini → on renvoie sa **réponse texte**.
   - **Sinon** : il veut un ou plusieurs outils. On garde sa demande dans l'historique (`messages.append(...)`), puis pour **chaque** appel demandé :
     - `json.loads(...arguments...)` : on lit les arguments (ex. `{"sku": "HB-LAP-1001"}`).
     - `print("[tool call] ...")` : on **affiche** l'appel → observabilité (à montrer en démo).
     - `session.call_tool(...)` : on **exécute vraiment** l'outil via le MCP.
     - On rajoute le résultat dans l'historique avec `role: "tool"` → le modèle le verra au tour suivant.
   - On reboucle : le modèle voit le résultat et, soit rédige la réponse, soit demande un autre outil.
6. Si on dépasse 5 tours (cas anormal) → message de repli.

**À dire au jury :** « c'est ici que se joue le *grounding* : le modèle ne connaît rien du stock, il **demande** un outil (étape `tool_calls`), on lui renvoie le vrai résultat, et il ne répond qu'avec ça. »

## `ask` — entrée synchrone + déballage d'erreur

```python
def ask(question: str) -> str:
    try:
        return asyncio.run(answer_question(question))
    except BaseExceptionGroup as group:
        error = group
        while isinstance(error, BaseExceptionGroup) and error.exceptions:
            error = error.exceptions[0]
        raise error from None
```
- `asyncio.run(...)` : lance la fonction `async` depuis du code normal (l'app Flask est synchrone).
- **Le déballage :** le client MCP enferme les erreurs dans un « groupe d'exceptions » dont le message est inutile (« unhandled errors in a TaskGroup »). La boucle `while` **extrait la vraie erreur** (ex. le refus de l'API modèle) pour qu'on puisse la logger correctement.

## Lancement en ligne de commande

```python
if __name__ == "__main__":
    import sys
    user_question = " ".join(sys.argv[1:]) or "What products are in stock in Lyon Part-Dieu?"
    print(ask(user_question))
```
- Permet de tester l'agent au terminal : `python -m ai_service.agent "ta question"`.

---

# 3) `ai_service/app.py`

## Création de l'app et CORS

```python
import os
from flask import Flask, jsonify, request
from ai_service.agent import ask

app = Flask(__name__)

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response
```
- `Flask` : le micro-framework web. `app` : notre application.
- `@app.after_request` : s'exécute **après chaque réponse** pour y ajouter les en-têtes **CORS**.
- **CORS = quoi ?** Le navigateur interdit par défaut qu'une page (servie sur le port 8080) appelle une API sur un **autre** port (8001). Ces en-têtes **autorisent** cet appel. C'est nécessaire car le front de Marie et notre API sont sur des ports différents.

## L'endpoint `/ask`

```python
@app.route("/ask", methods=["POST", "OPTIONS"])
def ask_endpoint():
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Missing 'question' in request body."}), 400

    try:
        answer = ask(question)
    except Exception as error:
        print(f"[error] agent failed: {error}", flush=True)
        return jsonify({"error": "The assistant is temporarily unavailable. Please try again."}), 502

    return jsonify({"answer": answer})
```
- `@app.route("/ask", methods=["POST", "OPTIONS"])` : cette fonction répond aux requêtes sur `/ask`.
- **`OPTIONS`** : avant un POST « compliqué », le navigateur envoie une requête de vérification (*preflight*). On répond `204` (OK, vide).
- `request.get_json(silent=True) or {}` : lit le corps JSON ; `silent=True` = ne plante pas si ce n'est pas du JSON.
- **Validation :** si pas de question → `400` avec un message clair.
- `try/except` autour de `ask(...)` : si l'agent échoue (clé manquante, MCP ou modèle indisponible), on **logge le détail** (`flush=True` pour que ça s'affiche tout de suite) et on renvoie un **`502` avec un message générique** au client → pas de trace d'erreur brute exposée.
- Succès : `jsonify({"answer": ...})`.

## Lancement

```python
if __name__ == "__main__":
    app.run(host=os.environ.get("AI_SERVICE_HOST", "127.0.0.1"), port=8001)
```
- Démarre le serveur web sur le port **8001**. `host` local par défaut ; `0.0.0.0` dans Docker (via `AI_SERVICE_HOST`).

---

# Questions « code » probables + réponses courtes

- **« C'est quoi `@mcp.tool()` ? »** → un décorateur qui enregistre la fonction comme outil MCP appelable par l'agent.
- **« Pourquoi de l'`async` ? »** → pour parler au serveur MCP sur le réseau sans bloquer ; `asyncio.run` fait le pont avec Flask (synchrone).
- **« Où l'IA pourrait-elle inventer ? »** → nulle part : elle n'a aucune donnée, elle doit appeler un outil ; le prompt système l'interdit ; sinon elle dit « info indisponible ».
- **« Pourquoi borner la boucle à 5 ? »** → sécurité, éviter une boucle d'outils infinie.
- **« Pourquoi une classe `ProductApiError` ? »** → pour un message d'erreur clair et distinguable, centralisé dans `_get_json`.
- **« Comment on brancherait la vraie base ? »** → on ne change que `_load_branches()` ; les outils et l'agent restent identiques.
- **« Pourquoi CORS ? »** → le front (autre port) doit être autorisé à appeler l'API depuis le navigateur.
- **« Pourquoi renvoyer 502 et pas planter ? »** → dégrader proprement : le client reçoit un message clair, on logge le vrai détail côté serveur.
