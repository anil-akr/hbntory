#!/usr/bin/env python3
"""End-to-end test of the AI agent (Task 5).

Starts the product MCP server, sends one realistic question per supported type
to the AI agent, prints the answers, then stops the MCP server.

Requirements:
- GROQ_API_KEY in the .env file at the repo root (the file is gitignored),
- the external Product API running (docker compose ... up).

Run from the repo root:
    ./.venv/bin/python scripts/e2e_test.py
"""
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# Imported after sys.path is set, so the script runs from anywhere. Importing
# the agent also loads the .env file, which is where the API key lives.
from ai_service.agent import MCP_SERVER_URL, ask  # noqa: E402

PRODUCT_API_URL = os.environ.get("PRODUCT_API_URL", "http://localhost:5001")

# Reuse the agent's own URL, so the test can never wait on a different port
# than the one the agent will actually call.
MCP_URL = MCP_SERVER_URL

# One question per supported type (see ai_service/supported_questions.md).
QUESTIONS = [
    "Give me the details of product HB-LAP-1001.",
    "Which branch has stock of HB-LAP-1001?",
    "What products are in stock in Lyon Part-Dieu?",
    "I want 3 units of HB-LAP-1001 and 2 units of HB-MON-2101 "
    "— which branch should I visit?",
]


def wait_until_up(url: str, timeout_seconds: int = 15) -> bool:
    """Wait until a URL answers (any HTTP response counts), or give up."""
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return True
        except urllib.error.HTTPError:
            return True  # the server answered (even an error) -> it is up
        except Exception:
            time.sleep(0.5)
    return False


def main() -> int:
    """Run the whole test and return a shell exit code (0 = success)."""
    if not os.environ.get("GROQ_API_KEY"):
        print("ERROR: GROQ_API_KEY is not set.")
        print("Get a free key from https://console.groq.com/keys, then")
        print("create a .env file at the repo root with:")
        print("    GROQ_API_KEY=gsk_...")
        print("(the .env file is gitignored)")
        return 1

    # Check that the external Product API is running.
    try:
        urllib.request.urlopen(f"{PRODUCT_API_URL}/health", timeout=3)
    except Exception:
        print(f"ERROR: Product API not reachable at {PRODUCT_API_URL}.")
        print("Start it with:")
        print("  docker compose -f /home/xom/hbntory-products-api/docker-compose.yml up -d")
        return 1

    # Reuse an MCP server that is already running (typical when the whole stack
    # is up), otherwise start one for the duration of the test.
    mcp_server = None
    if wait_until_up(MCP_URL, timeout_seconds=1):
        print(f"Using the MCP server already running at {MCP_URL}.\n")
    else:
        print("Starting the product MCP server...")
        mcp_server = subprocess.Popen(
            [sys.executable, "-m", "product_mcp_server.server"], cwd=REPO_ROOT
        )
        if not wait_until_up(MCP_URL):
            print("ERROR: the MCP server did not start in time.")
            mcp_server.terminate()
            return 1
        print("MCP server ready.\n")

    try:

        failures = 0
        for question in QUESTIONS:
            print("=" * 70)
            print("Q:", question)
            # One failing question should not hide the other results, so we
            # report it and keep going.
            try:
                print("A:", ask(question))
            except Exception as error:
                failures += 1
                print(f"ERROR: {type(error).__name__}: {error}")
            print()
    finally:
        # Only stop the server if this script is the one that started it.
        if mcp_server is not None:
            mcp_server.terminate()
            mcp_server.wait()
            print("MCP server stopped.")

    print(f"{len(QUESTIONS) - failures}/{len(QUESTIONS)} questions answered.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
