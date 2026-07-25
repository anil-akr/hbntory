# AI query service image.
# Build context is the repo root (see docker-compose.yml).
FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer is cached between code changes.
COPY ai_service/requirements.txt ./ai_service/requirements.txt
RUN pip install --no-cache-dir -r ai_service/requirements.txt

# Copy the service code.
COPY ai_service/ ./ai_service/

# Listen on all interfaces so the host (and the web client) can reach us.
ENV AI_SERVICE_HOST=0.0.0.0
EXPOSE 8001

CMD ["python", "-m", "ai_service.app"]
