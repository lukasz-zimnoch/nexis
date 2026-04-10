# --- Stage 1: build the React SPA ---
FROM node:20-slim AS frontend-build

WORKDIR /frontend

# Install dependencies first for layer caching
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy the rest of the frontend sources and build
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python app ---
FROM python:3.11-slim AS app

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install Python dependencies first for layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and install the project
COPY src/ src/
RUN uv sync --frozen --no-dev

# Copy the built SPA into the location server.py expects
COPY --from=frontend-build /frontend/dist/ /app/frontend/dist/

ENV PORT=8000

EXPOSE ${PORT}

# Cloud Run Service entrypoint. The Cloud Run Job overrides this CMD with
# `uv run python -m nexis.job_runner`.
CMD uv run uvicorn nexis.server:app --host 0.0.0.0 --port $PORT
