"""AI agent that answers questions using the product MCP server.

Flow (a "tool loop"):
1. connect to the MCP server and list its tools (products + stock),
2. send the user's question to the model together with those tools,
3. whenever the model asks to call a tool, run it through the MCP server and
   send the result back,
4. repeat until the model returns a final text answer.

The agent never invents data: it can only answer from the MCP tool results.
Every tool call is printed so we can observe what the agent does.

Requires a free Groq API key: GROQ_API_KEY, read from the .env file at the repo
root. Only this file depends on the model provider — the MCP server, its tools
and the Flask endpoint stay unchanged if the provider changes.
"""
import asyncio
import json
import os

from groq import BadRequestError, Groq
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

# Default port is 8010: the Backoffice already uses 8000.
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "http://127.0.0.1:8010/mcp")

# Model id verified against the live API (GET /openai/v1/models).
# llama-3.3-70b-versatile was dropped: it regularly emits malformed tool calls
# ("<function=get_product{...}"), which the API rejects with tool_use_failed.
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

# Safety bound: stop after this many tool rounds so we can never loop forever.
# Listing a branch takes one call for the stock plus one per product to get its
# name, so a branch with a few products already needs more than five rounds.
MAX_TOOL_ROUNDS = 10

# The system prompt keeps the agent grounded in real data.
SYSTEM_PROMPT = (
    "You are the HBntory assistant. You answer questions about products and "
    "stock across the company's branches. "
    "Only use the information returned by the tools. Never invent product "
    "names, prices, stock quantities, or branch availability. "
    "If the tools do not provide the needed information, say clearly that the "
    "information is not available. "
    "Always answer in the language of the question. "
    "Write plain text only: no Markdown, no asterisks for bold, no pipe "
    "tables. To list several branches or products, use one short line per "
    "item, starting with a dash. The client page displays your answer as raw "
    "text, so any formatting mark would show up as-is. "
    "When calling a tool, always produce a complete and valid JSON object for "
    "the arguments, with every brace closed."
)


def _load_env_file() -> None:
    """Load KEY=VALUE lines from the .env file at the repo root, if present.

    This keeps the API key out of the code and out of git, without adding a
    dependency just to read a small file.
    """
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


# Load .env as soon as this module is imported, so the web app and the CLI both
# find the API key without the user having to export it manually.
_load_env_file()


def _get_api_key() -> str:
    """Return the Groq API key, or raise a clear error."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is not set. Put it in a .env file at the repo root."
        )
    return api_key


def _to_groq_tools(mcp_tools):
    """Convert MCP tool definitions into the Groq (OpenAI-compatible) tools format.

    The MCP input schema is already JSON Schema, so it is passed straight
    through as the function parameters — no manual conversion needed.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": (tool.description or "").strip(),
                "parameters": tool.inputSchema,
            },
        }
        for tool in mcp_tools
    ]


def _ask_model(client, messages, tools):
    """Ask the model for its next step, retrying once on a malformed tool call.

    A model sometimes writes a tool call the API cannot parse, and the API
    answers with a 400 "tool_use_failed". Asking again is enough in practice,
    and it keeps a single bad generation from breaking the whole answer.
    """
    last_error = None
    for attempt in range(2):
        try:
            return client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=tools,
                tool_choice="auto",
            )
        except BadRequestError as error:
            if "tool_use_failed" not in str(error):
                raise
            print(f"[retry] malformed tool call (attempt {attempt + 1})", flush=True)
            last_error = error
    raise last_error


def _tool_result_text(result) -> str:
    """Extract a text payload from an MCP tool result to send back to the model."""
    if result.content and result.content[0].type == "text":
        return result.content[0].text
    return "(no content)"


async def answer_question(question: str) -> str:
    """Answer one question using the model and the MCP tools."""
    client = Groq(api_key=_get_api_key())

    # The client yields three values: the two streams, plus a getter for the
    # session id that we do not need here.
    async with streamable_http_client(MCP_SERVER_URL) as (
        read_stream,
        write_stream,
        _unused_session_id,
    ):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            tools = _to_groq_tools((await session.list_tools()).tools)

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ]

            for tool_round in range(MAX_TOOL_ROUNDS):
                response = _ask_model(client, messages, tools)
                message = response.choices[0].message

                if not message.tool_calls:
                    # The model is done: return its final text answer.
                    return (message.content or "").strip()

                # Keep the assistant message that asked for the tools, converted
                # back into a plain dict for the next request.
                messages.append(message.model_dump(exclude_none=True))

                # Run each requested tool through the MCP server.
                for call in message.tool_calls:
                    arguments = json.loads(call.function.arguments or "{}")
                    # flush=True so the call shows up immediately, even when the
                    # service output is piped to a file or read from Docker logs.
                    print(f"[tool call] {call.function.name}({arguments})", flush=True)
                    result = await session.call_tool(call.function.name, arguments)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.id,
                            "content": _tool_result_text(result),
                        }
                    )

            return "Sorry, I could not finish answering this question."


def ask(question: str) -> str:
    """Synchronous entry point used by the web endpoint.

    The MCP client runs its work in a task group, so any failure comes back
    wrapped in an ExceptionGroup whose message is just "unhandled errors in a
    TaskGroup". We unwrap it so callers get the real error (for example the
    model API refusing the request) and can log something useful.
    """
    try:
        return asyncio.run(answer_question(question))
    except BaseExceptionGroup as group:
        error = group
        while isinstance(error, BaseExceptionGroup) and error.exceptions:
            error = error.exceptions[0]
        raise error from None


if __name__ == "__main__":
    import sys

    user_question = (
        " ".join(sys.argv[1:])
        or "What products are in stock in Lyon Part-Dieu?"
    )
    print(ask(user_question))
