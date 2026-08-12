# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /build
ARG VITE_SIEM_ENABLED=true
ENV VITE_SIEM_ENABLED=$VITE_SIEM_ENABLED
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Backend + frontend dist
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer).
# Production image: runtime deps of this service only. CI deliberately differs
# (`uv sync --all-packages` with the dev group — see .github/workflows/ci.yml):
# there the dev toolchain is the point, here it is dead weight and attack
# surface. Both `uv sync` invocations below must carry --no-dev --package:
# what this layer installs stays in the image even if the final sync prunes it.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=backend/pyproject.toml,target=backend/pyproject.toml \
    --mount=type=bind,source=packages/siem-contracts/pyproject.toml,target=packages/siem-contracts/pyproject.toml \
    --mount=type=bind,source=packages/testing/pyproject.toml,target=packages/testing/pyproject.toml \
    --mount=type=bind,source=services/siem-service/pyproject.toml,target=services/siem-service/pyproject.toml \
    --mount=type=bind,source=services/executor/pyproject.toml,target=services/executor/pyproject.toml \
    --mount=type=bind,source=tools/security-scan/pyproject.toml,target=tools/security-scan/pyproject.toml \
    --mount=type=bind,source=tools/arch-checker/pyproject.toml,target=tools/arch-checker/pyproject.toml \
    uv sync --locked --no-dev --no-install-workspace --package learnflow-backend

# Copy project source
COPY backend/ /app/backend/
COPY packages/ /app/packages/
COPY services/ /app/services/
COPY tools/security-scan/pyproject.toml /app/tools/security-scan/pyproject.toml
COPY tools/arch-checker/pyproject.toml /app/tools/arch-checker/pyproject.toml
COPY configs/ /app/configs/
COPY skills/ /skills/
COPY pyproject.toml uv.lock /app/

# Install project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package learnflow-backend

# Copy frontend build output
COPY --from=frontend-build /build/dist /app/frontend/dist

# Entrypoint: migrations + uvicorn
COPY backend/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Non-root: uid 10001 is shared with the executor and the job sandbox it
# spawns (cross-track contract — see design brief § Executor / ADR-031, spike
# spikes/spike-bwrap-gvisor.md). Ownership must cover /app (venv + source) so
# `uv run`/alembic work without root; mirrors services/executor/Dockerfile.
RUN useradd -u 10001 -m -d /home/app app \
    && chown -R app:app /app

# Pre-create the named-volume mount point owned by uid 10001: a fresh
# `workspaces` volume otherwise gets created root:root on first use (Docker
# copies ownership of the image path at mount time), and this non-root user
# can't mkdir under it. Both app and executor images must do this — whichever
# container starts first stamps the volume's owner (architect escalation,
# tracks/T1/summary.md § T1.11).
RUN mkdir -p /workspaces && chown 10001:10001 /workspaces

USER 10001

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
