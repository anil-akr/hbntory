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
import urllib.error
import urllib.parse
import urllib.request

from mcp.server.fastmcp import FastMCP

# URL of the external Product API (provided Docker container, read-only).
PRODUCT_API_URL = os.environ.get("PRODUCT_API_URL", "http://localhost:5001")
REQUEST_TIMEOUT_SECONDS = 5

# The inventory file lives next to this module.
STOCK_FILE = os.path.join(os.path.dirname(__file__), "stock_data.json")

# The MCP server. The name is shown on the agent side.
mcp = FastMCP("hbntory-products")


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
# database directly. For now the data comes from stock_data.json, which stands
# in for the shared inventory database owned by the Backoffice. At integration
# time only _load_branches() changes: the tool names and return shapes stay the
# same, so the AI agent is not affected.
# ---------------------------------------------------------------------------


def _load_branches() -> dict:
    """Load the inventory as {branch_name: {sku: quantity}}."""
    with open(STOCK_FILE, "r", encoding="utf-8") as stock_file:
        return json.load(stock_file)["branches"]


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


@mcp.tool()
def check_shopping_list(items: list) -> dict:
    """Check which branch(es) can satisfy a shopping list.

    Argument:
    - items: list of {"sku": <sku>, "quantity": <int>} the customer wants.

    Returns {"fully_satisfied_by": [branch, ...], "per_branch": [...]}:
    - fully_satisfied_by lists the branches that alone cover every item;
    - per_branch details, for each branch, which items it can or cannot cover.
    """
    for item in items:
        if "sku" not in item or "quantity" not in item:
            raise ValueError("Each item needs a 'sku' and a 'quantity'.")

    branches = _load_branches()
    per_branch = []
    fully_satisfied_by = []
    for branch_name, stock in branches.items():
        lines = []
        covers_all = True
        for item in items:
            available = stock.get(item["sku"], 0)
            enough = available >= item["quantity"]
            if not enough:
                covers_all = False
            lines.append(
                {
                    "sku": item["sku"],
                    "wanted": item["quantity"],
                    "available": available,
                    "enough": enough,
                }
            )
        per_branch.append({"branch": branch_name, "items": lines})
        if covers_all:
            fully_satisfied_by.append(branch_name)
    return {"fully_satisfied_by": fully_satisfied_by, "per_branch": per_branch}


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
