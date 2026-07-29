"""Manual test of the product MCP server (test evidence — Task 4).

Connects to the MCP server (Streamable HTTP) and checks the 4 required cases:
1. list the exposed tools,
2. list_products works,
3. get_product with a valid SKU works,
4. get_product with an invalid SKU returns a clear error (no crash).

Prerequisites:
- the Product API is running (docker compose up),
- the MCP server is running: python -m product_mcp_server.server
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
    async with streamable_http_client(SERVER_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
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
            print("message =", result.content[0].text if result.content else "(empty)")


if __name__ == "__main__":
    asyncio.run(main())
