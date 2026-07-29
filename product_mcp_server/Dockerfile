# Product MCP server image.
# Build context is the repo root (see docker-compose.yml).
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached between code changes.
COPY product_mcp_server/requirements.txt ./product_mcp_server/requirements.txt
RUN pip install --no-cache-dir -r product_mcp_server/requirements.txt

# Copy the server code and its stand-in stock data.
COPY product_mcp_server/ ./product_mcp_server/

# Listen on all interfaces so the AI service container can reach us.
ENV MCP_HOST=0.0.0.0
EXPOSE 8010

CMD ["python", "-m", "product_mcp_server.server"]
