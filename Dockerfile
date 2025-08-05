FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy the workspace configuration
COPY pyproject.toml uv.lock ./
COPY learnflow/pyproject.toml ./learnflow/

# Install dependencies
RUN uv sync --package learnflow-core --no-dev --frozen

# Copy the application code
COPY learnflow/ ./learnflow/

# Expose port for FastAPI
EXPOSE 8000

# Run the application
CMD ["uv", "run", "--package", "learnflow-core", "python", "-m", "learnflow"] 