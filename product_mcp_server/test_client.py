"""Manual test of the product MCP server (test evidence — Tasks 4 and 5).

Connects to the MCP server (Streamable HTTP) and checks the 9 cases:

Product tools (Task 4)
1. list the exposed tools,
2. list_products works,
3. get_product with a valid SKU works,
4. get_product with an invalid SKU returns a clear error (no crash).

Stock tools (Task 5)
5. stock_for_product: the same product across every branch,
6. stock_in_branch: everything a single branch holds,
7. check_shopping_list: which branch covers a list of products,
8. stock_for_product with an unknown SKU stays clear (no invention),
9. stock_in_branch with an unknown branch stays clear.

No AI key is needed here: this test talks to the MCP tools directly, so it also
works when the model provider is unreachable.

Prerequisites:
- the Product API is running (docker compose up),
- the MCP server is running: python -m product_mcp_server.server
  (with STOCK_DB_PATH set, the stock tools read the real Backoffice database)
Then run: python -m product_mcp_server.test_client
"""
import asyncio
import os

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# Same environment variable as the AI service, so the test follows the server
# wherever it runs (the README starts it on 8010 to leave 8000 to the Backoffice).
SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8010/mcp")


def show_result(result):
    """Return the tool result as text.

    Our tools return a plain dict, so the MCP server sends the JSON back as text
    content — that is also what the AI agent reads.
    """
    return result.content[0].text if result.content else "(empty)"


async def main():
    # The client yields three values: the two streams, plus a getter for the
    # session id that we do not need here.
    async with streamable_http_client(SERVER_URL) as (
        read_stream,
        write_stream,
        _unused_session_id,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            print("=== 1. Available tools ===")
            tools = await session.list_tools()
            for tool in tools.tools:
                first_line = (tool.description or "").splitlines()[0]
                print(f"- {tool.name} : {first_line}")

            print("\n=== 2. list_products(search='keyboard', limit=5) ===")
            result = await session.call_tool(
                "list_products", {"search": "keyboard", "limit": 5}
            )
            print(show_result(result))

            print("\n=== 3. get_product('HB-LAP-1001') ===")
            result = await session.call_tool("get_product", {"identifier": "HB-LAP-1001"})
            print(show_result(result))

            print("\n=== 4. get_product('NOPE-999') -> clear error expected ===")
            result = await session.call_tool("get_product", {"identifier": "NOPE-999"})
            print("isError =", result.isError)
            print("message =", show_result(result))

            print("\n=== 5. stock_for_product('HB-LAP-1001') ===")
            result = await session.call_tool("stock_for_product", {"sku": "HB-LAP-1001"})
            print(show_result(result))

            print("\n=== 6. stock_in_branch('Lyon Part-Dieu') ===")
            result = await session.call_tool("stock_in_branch", {"branch": "Lyon Part-Dieu"})
            print(show_result(result))

            print("\n=== 7. check_shopping_list(3 laptops, 2 monitors, 4 cameras) ===")
            result = await session.call_tool(
                "check_shopping_list",
                {
                    "items": [
                        {"sku": "HB-LAP-1001", "quantity": 3},
                        {"sku": "HB-MON-2101", "quantity": 2},
                        {"sku": "HB-CAM-5101", "quantity": 4},
                    ]
                },
            )
            print(show_result(result))

            print("\n=== 8. stock_for_product('NOPE-999') -> no invented stock ===")
            result = await session.call_tool("stock_for_product", {"sku": "NOPE-999"})
            print("isError =", result.isError)
            print("message =", show_result(result))

            print("\n=== 9. stock_in_branch('Boutique Inexistante') -> clear answer ===")
            result = await session.call_tool(
                "stock_in_branch", {"branch": "Boutique Inexistante"}
            )
            print("isError =", result.isError)
            print("message =", show_result(result))


if __name__ == "__main__":
    asyncio.run(main())
