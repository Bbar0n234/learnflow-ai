#!/bin/bash
set -e

# The image ships a runtime-only venv (uv sync --no-dev --package). Without this,
# `uv run` re-syncs the environment on container start and pulls the dev group back.
export UV_NO_SYNC=1

echo "Running database migrations..."
uv run alembic -c backend/alembic.ini upgrade head

echo "Starting server..."
exec uv run --package learnflow-backend uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --app-dir backend
