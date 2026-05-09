FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Copy workspace root and all packages
COPY pyproject.toml uv.lock ./
COPY packages/siem-contracts ./packages/siem-contracts
COPY packages/siem-service ./packages/siem-service

# Create virtual environment and install packages
RUN uv venv && \
    uv pip install -e ./packages/siem-contracts && \
    uv pip install -e ./packages/siem-service

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8001

# Run uvicorn from the venv
CMD ["uvicorn", "siem_service.main:app", "--host", "0.0.0.0", "--port", "8001"]

# TODO: Опять же, в правильном ли месте сейчас этот Dockerfile? Консистентно ли с остальными сервисами этого репозитория?
