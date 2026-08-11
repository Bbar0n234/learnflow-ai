FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /uvx /bin/

# bubblewrap + util-linux (unshare): sandbox runtime for job execution.
# pandoc + fonts: job toolchain (markdown -> docx, glyph coverage incl.
# Cyrillic/math). fontconfig: font enumeration/matching (fc-list, fc-match)
# that matplotlib/pandoc rely on to find the fonts below — font packages
# alone don't pull it in on slim. curl: compose healthcheck.
# ca-certificates: TLS trust. tini: init process for PID 1 (reaps orphans —
# see ENTRYPOINT below).
RUN apt-get update && apt-get install -y --no-install-recommends \
    bubblewrap \
    util-linux \
    tini \
    pandoc \
    curl \
    fontconfig \
    fonts-dejavu \
    fonts-liberation2 \
    fonts-noto-core \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer).
# Production image: runtime deps of this service only (job toolchain +
# service deps, both live in [project.dependencies] of executor's
# pyproject.toml). CI deliberately differs (`uv sync --all-packages` with the
# dev group — see .github/workflows/ci.yml): there the dev toolchain is the
# point, here it is dead weight and attack surface. Both `uv sync`
# invocations below must carry --no-dev --package: what this layer installs
# stays in the image even if the final sync prunes it. --package also keeps
# the backend's LangChain/LangGraph/Langfuse stack and siem-service's stack
# out — this image never runs that code.
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
    uv sync --locked --no-dev --no-install-workspace --package executor

# Copy project source
COPY packages/ /app/packages/
COPY services/ /app/services/
COPY tools/security-scan/pyproject.toml /app/tools/security-scan/pyproject.toml
COPY tools/arch-checker/pyproject.toml /app/tools/arch-checker/pyproject.toml
COPY pyproject.toml uv.lock /app/
# uv requires every workspace member declared in the root pyproject to exist
# on disk; copy backend's pyproject only (no source) to satisfy the workspace
# resolver without bloating the image with backend code.
COPY backend/pyproject.toml /app/backend/pyproject.toml

# Install project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --package executor

# Executor is the one service that runs untrusted job code (via bwrap). It
# never runs as root: uid 10001 is shared with the job sandbox and the
# backend's shared workspace volume (cross-track contract — see design brief
# § Executor, uid must match across app/executor/job).
RUN useradd -u 10001 -m -d /home/executor executor \
    && chown -R executor:executor /app

# Pre-create the named-volume mount point owned by uid 10001: a fresh
# `workspaces` volume otherwise gets created root:root on first use (Docker
# copies ownership of the image path at mount time), and this non-root user
# can't mkdir under it. Both app and executor images must do this — whichever
# container starts first stamps the volume's owner (architect escalation,
# tracks/T1/summary.md § T1.11).
RUN mkdir -p /workspaces && chown 10001:10001 /workspaces

USER 10001

ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8002

# tini as PID 1: every job leaves a `bwrap` child that outlives its wrapper and
# reparents to PID 1. uvicorn is not an init — it never reaps, so each job used
# to leak one zombie, draining the container's `pids_limit` slot by slot.
# The init lives in the image, not in `init: true` per compose service: the
# guarantee must hold wherever this image runs. tini forwards signals to the
# CMD process untouched, so the executor's own kill contract is unaffected.
# No entrypoint script beyond it: the service has no migrations to run.
ENTRYPOINT ["tini", "--"]
CMD ["uvicorn", "executor.main:app", "--host", "0.0.0.0", "--port", "8002", "--app-dir", "services/executor"]
