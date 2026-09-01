# Cascade backend — FastAPI + the exported model artifacts.
# The image NEVER trains: artifacts are produced offline by tools/export_artifacts.py
# and mounted in read-only (Architecture & Workflow §7 / §8).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# libGL/libglib are needed by opencv, which ultralytics pulls in
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch keeps the image an order of magnitude smaller than the CUDA build
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY tools /app/tools

# Written to by the running container; both are also mounted as volumes in compose
RUN mkdir -p /app/data /app/config

ENV CASCADE_ARTIFACTS_DIR=/app/artifacts \
    CASCADE_CONFIG_DIR=/app/config \
    CASCADE_DATA_DIR=/app/data \
    CASCADE_DATABASE_URL=sqlite:////app/data/cascade.db

EXPOSE 8000

HEALTHCHECK --interval=20s --timeout=5s --start-period=90s --retries=5 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
