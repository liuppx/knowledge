# syntax=docker/dockerfile:1

# ---- Stage 1: build the React console -------------------------------------
FROM node:24-alpine AS web
WORKDIR /src/web
COPY web/package.json web/package-lock.json web/.npmrc ./
RUN npm ci
COPY web/ ./
RUN npm run build

# ---- Stage 2: API + worker runtime ----------------------------------------
# The same image serves the API (default CMD) and the import worker
# (`python -m knowledge.workers.runner`); compose.yaml wires both.
FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY alembic.ini ./
COPY knowledge/ knowledge/
COPY migrations/ migrations/
# TOML config layer added in 483dc7f: defaults.toml + local.toml. Without these
# the image can only start in development (the conftest.py / dev workaround
# relies on missing files gracefully, but production hits the production-config
# guard and the service refuses to start).
COPY config/ config/
# routes_console resolves web/dist relative to the package: /app/web/dist.
COPY --from=web /src/web/dist web/dist

RUN useradd --create-home --uid 10001 knowledge \
    && mkdir -p /data \
    && chown -R knowledge:knowledge /app /data
USER knowledge

EXPOSE 8002
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8002/health || exit 1

# Migrations run on startup (knowledge.main lifespan -> ensure_database_schema).
CMD ["uvicorn", "knowledge.main:app", "--host", "0.0.0.0", "--port", "8002"]
