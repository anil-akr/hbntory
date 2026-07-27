"""Product MCP server — the bridge between the AI agent and our data.

Exposes 5 tools to the AI agent:

Product tools (relayed to the external Product API, read-only):
- list_products : list products (simple search + limit).
- get_product   : details of one product by SKU (or numeric id).

Stock tools (read from the local inventory data):
- stock_for_product   : in which branches a product is available.
- stock_in_branch     : what one branch currently holds.
- check_shopping_list : which branch(es) can satisfy a list of items.

The server keeps nothing of its own: product data is relayed from the external
API and never stored, stock is read from the inventory data. If a product is not
found or the API is unreachable, it returns a clear error — never a silent
failure.

Run the server (from the repo root, with the venv active):
    python -m product_mcp_server.server
It listens over Streamable HTTP at http://127.0.0.1:8000/mcp
"""
import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request

from mcp.server.fastmcp import FastMCP

# URL of the external Product API (provided Docker container, read-only).
PRODUCT_API_URL = os.environ.get("PRODUCT_API_URL", "http://localhost:5001")
REQUEST_TIMEOUT_SECONDS = 5

# Stock data source. If STOCK_DB_PATH points to the Backoffice SQLite database,
# the stock tools read the real inventory (read-only). Otherwise they read the
# local stand-in file, so the AI service can still run on its own.
STOCK_FILE = os.path.join(os.path.dirname(__file__), "stock_data.json")
STOCK_DB_PATH = os.environ.get("STOCK_DB_PATH")

# The MCP server. The name is shown on the agent side.
# Bind to 127.0.0.1 for local dev; docker-compose sets MCP_HOST=0.0.0.0 so the
# AI service container can reach this server over the Compose network.
mcp = FastMCP("hbntory-products", host=os.environ.get("MCP_HOST", "127.0.0.1"))


# ---------------------------------------------------------------------------
# Product tools — everything here comes from the external Product API
# ---------------------------------------------------------------------------


class ProductApiError(Exception):
    """Clear error raised when the Product API is not found or unreachable."""


def _get_json(path: str) -> dict:
    """Call the Product API and return the JSON, or raise a clear error.

    This is the only place that talks to the network, so error handling is
    centralized here (404 = product not found, other status = API error,
    network/timeout = API unreachable) and every tool returns clear messages.
    """
    url = f"{PRODUCT_API_URL}{path}"
    try:
        with urllib.request.urlopen(url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as http_error:
        if http_error.code == 404:
            raise ProductApiError("Product not found in the catalog.") from http_error
        raise ProductApiError(
            f"The Product API responded with status {http_error.code}."
        ) from http_error
    except (urllib.error.URLError, TimeoutError) as network_error:
        raise ProductApiError("The Product API is unreachable.") from network_error


@mcp.tool()
def list_products(search: str = "", limit: int = 20) -> dict:
    """List products from the external catalog.

    Arguments:
    - search: text to search for (name, SKU, description, tag). Empty = whole catalog.
    - limit:  maximum number of products returned (clamped between 1 and 100).

    Returns: {"count": <total found>, "products": [{sku, name, category,
    unit_price, currency}, ...]}. Only these useful fields are exposed.
    """
    safe_limit = max(1, min(limit, 100))
    query = f"/api/v1/products?limit={safe_limit}"
    if search:
        query += "&q=" + urllib.parse.quote(search)

    data = _get_json(query)
    products = [
        {
            "sku": product["sku"],
            "name": product["name"],
            "category": product["category"],
            "unit_price": product["unit_price"],
            "currency": product["currency"],
        }
        for product in data["results"]
    ]
    return {"count": data["count"], "products": products}


@mcp.tool()
def get_product(identifier: str) -> dict:
    """Return the details of one product by SKU (e.g. 'HB-LAP-1001') or numeric id.

    Returns: the public fields of the product (sku, name, description, category,
    brand, unit_price, currency, supplier_name, tags). Raises a clear error if
    the product does not exist.
    """
    data = _get_json(f"/api/v1/products/{urllib.parse.quote(identifier)}")
    return {
        "sku": data["sku"],
        "name": data["name"],
        "description": data["description"],
        "category": data["category"],
        "brand": data["brand"],
        "unit_price": data["unit_price"],
        "currency": data["currency"],
        "supplier_name": data["supplier_name"],
        "tags": data["tags"],
    }


# ---------------------------------------------------------------------------
# Stock tools — the AI reads stock through this server, never through the
# database directly. `_load_branches()` is the single source of stock data:
# it reads the Backoffice database when STOCK_DB_PATH is set, otherwise the
# local stand-in file. The 5 tools below only call _load_branches(), so they
# (and the AI agent) never change when we switch the data source.
# ---------------------------------------------------------------------------


def _load_branches() -> dict:
    """Load the inventory as {branch_name: {product_id: quantity}}.

    Reads the real Backoffice database when STOCK_DB_PATH points to it, and
    falls back to the local stand-in file otherwise. This is the only function
    to change when wiring the AI to the shared inventory database.
    """
    if STOCK_DB_PATH:
        return _load_branches_from_db(STOCK_DB_PATH)
    return _load_branches_from_file()


def _load_branches_from_file() -> dict:
    """Load the stand-in inventory from the local JSON file."""
    with open(STOCK_FILE, "r", encoding="utf-8") as stock_file:
        return json.load(stock_file)["branches"]


def _load_branches_from_db(db_path: str) -> dict:
    """Read branch stock from the Backoffice SQLite database (read-only).

    Joins `inventories` with `branches` to build the exact shape the tools
    expect: {branch_name: {product_id: quantity}}. The connection is opened
    read-only (mode=ro), so the MCP server can never modify the Backoffice data.
    """
    branches: dict = {}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT b.name, i.product_id, i.quantity "
            "FROM inventories i JOIN branches b ON b.id = i.branch_id"
        )
        for branch_name, product_id, quantity in rows:
            branches.setdefault(branch_name, {})[product_id] = quantity
    finally:
        connection.close()
    return branches


@mcp.tool()
def stock_for_product(sku: str) -> dict:
    """Show how much of a product is available in each branch.

    Returns {"sku": <sku>, "availability": [{branch, quantity}, ...]}, listing
    only the branches that currently hold this product.
    """
    branches = _load_branches()
    availability = [
        {"branch": branch_name, "quantity": stock[sku]}
        for branch_name, stock in branches.items()
        if stock.get(sku, 0) > 0
    ]
    return {"sku": sku, "availability": availability}


@mcp.tool()
def stock_in_branch(branch: str) -> dict:
    """List the products (and quantities) currently in stock in one branch.

    Returns {"branch": <branch>, "products": [{sku, quantity}, ...]}, or an
    empty list if the branch is unknown or holds nothing.
    """
    branches = _load_branches()
    stock = branches.get(branch, {})
    products = [
        {"sku": sku, "quantity": quantity}
        for sku, quantity in stock.items()
        if quantity > 0
    ]
    return {"branch": branch, "products": products}


def _coverage(stock: dict, remaining: dict) -> int:
    """How many still-needed units a branch can provide."""
    return sum(min(stock.get(sku, 0), quantity) for sku, quantity in remaining.items())


def _greedy_plan(branches: dict, wanted: dict) -> list:
    """Choose branches to visit so the whole list is covered.

    Simple greedy heuristic: repeatedly go to the branch that covers the most of
    what is still missing, until nothing is missing. Not guaranteed to be the
    smallest possible set of branches, but easy to follow and good enough.
    Returns [{"branch": name, "take": {sku: quantity}}, ...].
    """
    remaining = dict(wanted)
    unused = dict(branches)
    plan = []
    while any(quantity > 0 for quantity in remaining.values()) and unused:
        best_branch = max(unused, key=lambda name: _coverage(unused[name], remaining))
        stock = unused.pop(best_branch)
        if _coverage(stock, remaining) == 0:
            break  # no remaining branch can help
        take = {}
        for sku, quantity in remaining.items():
            amount = min(stock.get(sku, 0), quantity)
            if amount > 0:
                take[sku] = amount
                remaining[sku] -= amount
        plan.append({"branch": best_branch, "take": take})
    return plan


@mcp.tool()
def check_shopping_list(items: list) -> dict:
    """Find where to buy a shopping list: one branch, or several combined.

    Argument:
    - items: list of {"sku": <sku>, "quantity": <int>} the customer wants.

    Returns:
    - fully_satisfied_by: branches that alone cover the whole list (best case);
    - satisfiable: whether all branches together hold enough of every item;
    - plan: when no single branch is enough, a short list of branches to visit
      with what to buy at each (empty if one branch already works, or if the
      list cannot be satisfied at all);
    - missing: when not satisfiable, how many units are missing per product.
    """
    for item in items:
        if "sku" not in item or "quantity" not in item:
            raise ValueError("Each item needs a 'sku' and a 'quantity'.")

    branches = _load_branches()
    wanted = {item["sku"]: item["quantity"] for item in items}

    # Branches that alone cover the whole list.
    fully_satisfied_by = [
        name
        for name, stock in branches.items()
        if all(stock.get(sku, 0) >= quantity for sku, quantity in wanted.items())
    ]

    # Can the list be satisfied at all, using every branch together?
    total_available = {
        sku: sum(stock.get(sku, 0) for stock in branches.values()) for sku in wanted
    }
    missing = {
        sku: quantity - total_available[sku]
        for sku, quantity in wanted.items()
        if total_available[sku] < quantity
    }
    satisfiable = not missing

    # Only compute a multi-branch plan when it is needed and possible.
    plan = []
    if satisfiable and not fully_satisfied_by:
        plan = _greedy_plan(branches, wanted)

    return {
        "fully_satisfied_by": fully_satisfied_by,
        "satisfiable": satisfiable,
        "plan": plan,
        "missing": missing,
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
