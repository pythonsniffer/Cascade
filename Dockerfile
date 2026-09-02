# Cascade — all-in-one image: FastAPI serves both the API and the built dashboard.
#
# For single-container hosts (Hugging Face Spaces, `docker run`, any PaaS that gives you
# one port). The two-container split with nginx lives in docker-compose.yml.
#
#   docker build -t cascade .
#   docker run -p 7860:7860 cascade
#
# Nothing here trains a model: artifacts/ is baked in and loaded at startup.

# ── stage 1: build the dashboard ─────────────────────────────────────────
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── stage 2: the app ─────────────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# libGL/libglib are needed by opencv, which ultralytics pulls in
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend  /app/backend
COPY tools    /app/tools
COPY artifacts /app/artifacts
COPY --from=frontend /build/dist /app/frontend/dist

# Hugging Face Spaces runs as a non-root user and expects the app on 7860.
# config/ and data/ are written at runtime, so they must be writable.
RUN mkdir -p /app/config /app/data && chmod -R 777 /app/config /app/data

ENV CASCADE_ARTIFACTS_DIR=/app/artifacts \
    CASCADE_CONFIG_DIR=/app/config \
    CASCADE_DATA_DIR=/app/data \
    CASCADE_DATABASE_URL=sqlite:////app/data/cascade.db \
    CASCADE_FRONTEND_DIST=/app/frontend/dist \
    PORT=7860

EXPOSE 7860

HEALTHCHECK --interval=20s --timeout=5s --start-period=120s --retries=5 \
  CMD curl -fsS http://localhost:${PORT}/healthz || exit 1

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"]
