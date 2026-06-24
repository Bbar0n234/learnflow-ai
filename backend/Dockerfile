# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Backend + frontend dist
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    wkhtmltopdf curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=backend/pyproject.toml,target=backend/pyproject.toml \
    --mount=type=bind,source=packages/siem-contracts/pyproject.toml,target=packages/siem-contracts/pyproject.toml \
    --mount=type=bind,source=packages/testing/pyproject.toml,target=packages/testing/pyproject.toml \
    --mount=type=bind,source=services/siem-service/pyproject.toml,target=services/siem-service/pyproject.toml \
    --mount=type=bind,source=tools/security-scan/pyproject.toml,target=tools/security-scan/pyproject.toml \
    --mount=type=bind,source=tools/arch-checker/pyproject.toml,target=tools/arch-checker/pyproject.toml \
    uv sync --locked --no-install-workspace --all-packages

# Copy project source
COPY backend/ /app/backend/
COPY packages/ /app/packages/
COPY services/ /app/services/
COPY tools/security-scan/pyproject.toml /app/tools/security-scan/pyproject.toml
COPY tools/arch-checker/pyproject.toml /app/tools/arch-checker/pyproject.toml
COPY configs/ /app/configs/
COPY skills/ /app/skills/
COPY pyproject.toml uv.lock /app/

# Install project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --all-packages

# Copy frontend build output
COPY --from=frontend-build /build/dist /app/frontend/dist

# Entrypoint: migrations + uvicorn
COPY backend/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
