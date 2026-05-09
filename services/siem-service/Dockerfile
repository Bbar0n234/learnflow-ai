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
    uv sync --locked --no-install-workspace --all-packages

# Copy project source
COPY packages/ /app/packages/
COPY services/ /app/services/
COPY pyproject.toml uv.lock /app/

# Install project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --all-packages

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8001

CMD ["uvicorn", "siem_service.main:app", "--host", "0.0.0.0", "--port", "8001"]
