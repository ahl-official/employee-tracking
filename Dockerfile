# syntax=docker/dockerfile:1

# --- frontend build ---
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- runtime ---
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DESKTRACK_ENV=production \
    HOST=0.0.0.0 \
    PORT=8000 \
    RELOAD=false \
    SEED_DEMO=false \
    HTTPS_ONLY=false

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY analytics.py config.py database.py detector.py face_id.py main.py models.py passwords.py ./
COPY --from=frontend /app/frontend/dist ./frontend/dist

# Models download on first start if missing; optional pre-bake via volume
RUN mkdir -p yolo_model data face_models

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
