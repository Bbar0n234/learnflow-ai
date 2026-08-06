#!/bin/bash
set -e

# The image ships a runtime-only venv (uv sync --no-dev --package). Without this,
# `uv run` re-syncs the environment on container start and pulls the dev group back.
export UV_NO_SYNC=1

echo "Running siem-service database migrations..."
cd /app/services/siem-service && uv run --package siem-service alembic upgrade head

echo "Starting siem-service..."
cd /app
exec uv run --package siem-service uvicorn siem_service.main:app \
    --host 0.0.0.0 --port 8001 --app-dir services/siem-service
