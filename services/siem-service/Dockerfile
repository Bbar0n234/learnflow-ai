FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.10.2 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=backend/pyproject.toml,target=backend/pyproject.toml \
    --mount=type=bind,source=packages/siem-contracts/pyproject.toml,target=packages/siem-contracts/pyproject.toml \
    --mount=type=bind,source=services/siem-service/pyproject.toml,target=services/siem-service/pyproject.toml \
    --mount=type=bind,source=tools/security-scan/pyproject.toml,target=tools/security-scan/pyproject.toml \
    uv sync --locked --no-install-workspace --all-packages

# Copy project source
COPY packages/ /app/packages/
COPY services/ /app/services/
COPY tools/security-scan/pyproject.toml /app/tools/security-scan/pyproject.toml
COPY pyproject.toml uv.lock /app/
# uv requires every workspace member declared in the root pyproject to exist
# on disk; copy backend's pyproject only (no source) to satisfy the workspace
# resolver without bloating the image with backend code.
COPY backend/pyproject.toml /app/backend/pyproject.toml

# Install project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --all-packages

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8001

# Entrypoint: migrations + uvicorn (mirrors backend/entrypoint.sh)
COPY services/siem-service/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
