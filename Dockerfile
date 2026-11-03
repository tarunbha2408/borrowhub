# ---------------------------------------------------------------------------
# BorrowHub - production image (PaaS / any container host)
#   docker build -t borrowhub .
#   docker run -p 8000:8000 --env-file .env.production borrowhub
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Build tooling needed by the bcrypt/cryptography wheels (slim image)
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential curl \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt backend/requirements-prod.txt /app/backend/
RUN pip install --upgrade pip \
 && pip install -r backend/requirements.txt -r backend/requirements-prod.txt

COPY . /app

# Run as a non-root user (required by most PaaS platforms)
RUN useradd --create-home --uid 10001 borrowhub \
 && mkdir -p /app/backend/static/uploads /data/uploads \
 && chown -R borrowhub:borrowhub /app/backend/static/uploads /data/uploads
USER borrowhub

ENV UPLOAD_DIR=/data/uploads \
    ENVIRONMENT=production \
    DEBUG=False \
    PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

# The platform provides $PORT; defaults to 8000.
CMD ["sh", "-c", "gunicorn backend.app.main:app -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-2} -b 0.0.0.0:${PORT:-8000} --timeout 120 --access-logfile - --error-logfile -"]
