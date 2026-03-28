#!/bin/bash
set -e

echo "Running database migrations..."
uv run alembic -c backend/alembic.ini upgrade head

echo "Starting server..."
exec uv run --package learnflow-backend uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --app-dir backend
