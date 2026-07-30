"""AI Query Service — public HTTP endpoint for the client web interface.

Exposes one REST endpoint:
    POST /ask   body: {"question": "..."}   ->   {"answer": "..."}

Each request is independent (no conversation history), matching the project's
REST choice for the client <-> AI communication.

CORS headers are added so the client page (served on another port) can call this
endpoint from the browser.

Run (from the repo root, with the venv active):
    python -m ai_service.app
The API key is read automatically from the .env file at the repo root.
"""
import os

from flask import Flask, jsonify, request

from ai_service.agent import ask

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    """Allow the browser-based client page to call this API cross-origin."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    return response


@app.route("/ask", methods=["POST", "OPTIONS"])
def ask_endpoint():
    """Receive a user question and return the agent's grounded answer."""
    # The browser sends a preflight OPTIONS request before the POST; answer it.
    if request.method == "OPTIONS":
        return ("", 204)

    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "Question manquante dans la requête."}), 400

    try:
        answer = ask(question)
    except Exception as error:
        # The agent can fail (missing API key, model or MCP server unavailable).
        # Log the detail for us, return a clear generic message to the client.
        # flush=True so the message appears immediately, even when the output is
        # redirected to a file instead of a terminal.
        print(f"[error] agent failed: {error}", flush=True)
        # The message is shown as-is on the public page, so it is written in
        # French like the rest of the interface.
        return (
            jsonify(
                {"error": "L'assistant est momentanément indisponible. Merci de réessayer."}
            ),
            502,
        )

    return jsonify({"answer": answer})


if __name__ == "__main__":
    # Development server. The client web page will POST to /ask.
    # Binds to 127.0.0.1 for local dev; the Dockerfile sets AI_SERVICE_HOST=0.0.0.0.
    app.run(host=os.environ.get("AI_SERVICE_HOST", "127.0.0.1"), port=8001)
