.PHONY: bootstrap docker-up docker-up-db docker-up-redis docker-down docker-build docker-build-executor docker-logs lint format type-check arch-check check ci lint-fe check-fe format-fe build-fe dev dev-remote dev-fe test test-contracts test-parallel test-scope test-cov test-fe migrate migration downgrade migrate-siem sync-prompts security-scan-validate security-scan-redteam security-scan-report grant-admin seed-demo smoke-executor

# Load .env (base) then .env.local (overrides) into shell environment
LOAD_ENV = set -a && [ -f .env ] && . ./.env; [ -f .env.local ] && . ./.env.local; set +a

bootstrap:  ## Install deps in a fresh checkout/worktree (Python venv + frontend node_modules)
	uv sync --all-packages
	cd frontend && npm ci

# smoke-executor passes a placeholder EXECUTOR_AUTH_TOKEN: the smoke scenarios
# call the runner directly (no HTTP, no auth barrier), but `Settings()` has no
# default for the secret and would refuse to build inside the container.
#
# smoke-executor runtime: `runc` is the image-release gate (default, works on
# any dev host with plain Docker); `runsc` is the production bwrap-under-gVisor
# verification, run as a deploy-checklist step on a host that has the runsc
# runtime registered with the Docker daemon.
RUNTIME ?= runc

docker-up:  ## Start full stack (app + db)
	docker compose up -d

docker-up-db:  ## Start only PostgreSQL (for local dev)
	docker compose up -d db

docker-up-redis:  ## Start only Redis (for local dev)
	docker compose up -d redis

docker-down:  ## Stop all containers
	docker compose down

docker-build:  ## Build Docker images
	docker compose build

docker-build-executor:  ## Build the executor image standalone (also built as part of `make docker-build`/`docker-up`, which run docker-compose.yml's own build)
	docker build -f services/executor/Dockerfile -t learnflow-executor:local .

# Executor image release gate: runs services/executor/smoke/run_all.sh (the
# job toolchain + the full unshare/bwrap sandbox prefix) inside the built
# image. Requires `make docker-build-executor` first (not chained here —
# rebuild is an explicit step, not implicit on every smoke run).
#
# `--security-opt seccomp=unconfined --security-opt apparmor=unconfined
# --security-opt systempaths=unconfined`: this dev host's default docker
# seccomp profile blocks the unprivileged userns/proc-mount the bwrap prefix
# needs even under --runtime=runc (T3 track summary, architect escalation
# 2026-08-11) — the actual isolation boundary is gVisor in production plus
# bwrap per job, not the container's own seccomp profile, so relaxing it
# here does not weaken the job sandbox itself.
smoke-executor:  ## Run the executor image smoke suite (release gate). Usage: make smoke-executor [RUNTIME=runc|runsc] — build the image first with make docker-build-executor
	@tmpdir="$$(mktemp -d)" && \
	mkdir -p "$$tmpdir/smoke" && \
	docker run --rm --user 0 -v "$$tmpdir:/workspaces" learnflow-executor:local \
	  chown -R 10001:10001 /workspaces && \
	docker run --rm --runtime=$(RUNTIME) \
	  --security-opt seccomp=unconfined --security-opt apparmor=unconfined --security-opt systempaths=unconfined \
	  -v "$$tmpdir:/workspaces" \
	  -v $(PWD)/skills:/skills:ro \
	  -e EXECUTOR_AUTH_TOKEN=smoke-suite-placeholder \
	  learnflow-executor:local /app/services/executor/smoke/run_all.sh; \
	ec=$$?; \
	docker run --rm --user 0 -v "$$tmpdir:/workspaces" learnflow-executor:local \
	  chown -R $$(id -u):$$(id -g) /workspaces >/dev/null 2>&1 || true; \
	rm -rf "$$tmpdir"; exit $$ec

docker-logs:  ## Show app container logs
	docker compose logs -f app

lint:  ## Run ruff linter
	uv run ruff check --no-cache .

format:  ## Format Python code (auto-fix safe lint issues + format)
	uv run ruff check --fix .
	uv run ruff format .

# mypy runs per source root: backend, siem-service and executor each own a
# top-level `tests` package, and a single mypy process rejects two same-named
# modules.
type-check:  ## Run mypy type checking
	uv run mypy backend/
	uv run mypy services/siem-service/
	uv run mypy services/executor/
	uv run mypy tools/security-scan/ tools/arch-checker/

arch-check:  ## Run architecture checks (import-linter contracts + AST asserts)
	PYTHONPATH=backend:services/siem-service uv run lint-imports
	uv run python -m arch_checker

check:  ## Run all backend checks (CI gate)
	uv run ruff check --no-cache .
	uv run ruff format --check .
	uv run mypy backend/
	uv run mypy services/siem-service/
	uv run mypy services/executor/
	uv run mypy tools/security-scan/ tools/arch-checker/
	PYTHONPATH=backend:services/siem-service uv run lint-imports
	uv run python -m arch_checker

lint-fe:  ## Run ESLint on frontend
	cd frontend && npx eslint .

check-fe:  ## Run all frontend checks (CI gate)
	cd frontend && npx tsc -b --noEmit
	cd frontend && npx eslint .
	cd frontend && npx prettier --check .

format-fe:  ## Format frontend code with Prettier
	cd frontend && npx prettier --write .

build-fe:  ## Build frontend production bundle (Vite) — mirrors CI "Frontend build"
	cd frontend && npm run build

# Full local reproduction of the CI pipeline, in CI order, fail-fast on first
# error. Heavy (frontend + docker build + testcontainers, ~5-10 min) — this is
# the pre-push gate, not a per-edit check. Keeping it identical to .github/
# workflows/ci.yml is what makes "green locally" mean "green in CI"; update both
# together when the pipeline changes.
ci:  ## Full local CI reproduction (heavy) — run before push
	@$(MAKE) --no-print-directory check
	@$(MAKE) --no-print-directory check-fe
	@$(MAKE) --no-print-directory build-fe
	@[ -f .env ] || cp .env.example .env
	docker compose build
	@$(MAKE) --no-print-directory test
	@$(MAKE) --no-print-directory test-fe

dev:  ## Run backend dev server (localhost only)
	$(LOAD_ENV) && uv run --package learnflow-backend uvicorn app.main:app --reload --app-dir backend

dev-remote:  ## Run backend dev server (accessible by IP)
	$(LOAD_ENV) && uv run --package learnflow-backend uvicorn app.main:app --reload --app-dir backend --host 0.0.0.0

dev-fe:  ## Run frontend dev server
	cd frontend && npx vite

test:  ## Run backend + siem-service + executor + siem-contracts pytest (exit 5 = "no tests collected" is OK)
	@$(LOAD_ENV) && uv run --package learnflow-backend pytest -c backend/pyproject.toml --rootdir backend backend/tests; ec=$$?; [ $$ec -eq 0 ] || [ $$ec -eq 5 ]
	@$(LOAD_ENV) && uv run --package siem-service pytest -c services/siem-service/pyproject.toml --rootdir services/siem-service services/siem-service/tests; ec=$$?; [ $$ec -eq 0 ] || [ $$ec -eq 5 ]
	@$(LOAD_ENV) && uv run --package executor pytest -c services/executor/pyproject.toml --rootdir services/executor services/executor/tests; ec=$$?; [ $$ec -eq 0 ] || [ $$ec -eq 5 ]
	@$(MAKE) --no-print-directory test-contracts

test-contracts:  ## Run siem-contracts library contract tests (Literal <-> constants guards)
	@uv run --package siem-contracts pytest -c packages/siem-contracts/pyproject.toml --rootdir packages/siem-contracts packages/siem-contracts/tests; ec=$$?; [ $$ec -eq 0 ] || [ $$ec -eq 5 ]

test-parallel:  ## Run backend + siem-service + executor pytest under xdist (-n auto, container per worker)
	@$(LOAD_ENV) && uv run --package learnflow-backend pytest -c backend/pyproject.toml --rootdir backend -n auto backend/tests; ec=$$?; [ $$ec -eq 0 ] || [ $$ec -eq 5 ]
	@$(LOAD_ENV) && uv run --package siem-service pytest -c services/siem-service/pyproject.toml --rootdir services/siem-service -n auto services/siem-service/tests; ec=$$?; [ $$ec -eq 0 ] || [ $$ec -eq 5 ]
	@$(LOAD_ENV) && uv run --package executor pytest -c services/executor/pyproject.toml --rootdir services/executor -n auto services/executor/tests; ec=$$?; [ $$ec -eq 0 ] || [ $$ec -eq 5 ]
	@$(MAKE) --no-print-directory test-contracts

test-scope:  ## Run a subset of backend tests under Docker. Usage: make test-scope P=backend/tests/auth
	@$(LOAD_ENV) && uv run --package learnflow-backend pytest -c backend/pyproject.toml --rootdir backend $(P); ec=$$?; [ $$ec -eq 0 ] || [ $$ec -eq 5 ]

test-cov:  ## Run backend pytest with branch coverage (per-package, term-missing)
	@$(LOAD_ENV) && uv run --package learnflow-backend pytest -c backend/pyproject.toml --rootdir backend backend/tests \
	  --cov=app --cov-branch --cov-report=term-missing; ec=$$?; [ $$ec -eq 0 ] || [ $$ec -eq 5 ]

test-fe:  ## Run frontend tests (Vitest, jsdom)
	cd frontend && npx vitest run

migrate:  ## Run alembic upgrade head
	$(LOAD_ENV) && uv run alembic -c backend/alembic.ini upgrade head

migration:  ## Create new alembic migration (autogenerate). Usage: make migration msg="description"
	$(LOAD_ENV) && uv run alembic -c backend/alembic.ini revision --autogenerate -m "$(msg)"

migrate-siem:  ## Run alembic upgrade head for SIEM service
	$(LOAD_ENV) && cd services/siem-service && uv run alembic upgrade head

grant-admin:  ## Grant admin to existing user. Usage: make grant-admin USER=<username>
	@if [ "$(origin USER)" != "command line" ]; then echo "Usage: make grant-admin USER=<username>"; exit 1; fi
	$(LOAD_ENV) && cd backend && PYTHONPATH=. uv run --package learnflow-backend python scripts/grant_admin.py "$(USER)"

seed-demo:  ## Seed deterministic demo data for visual review (dev/test-only, idempotent)
	$(LOAD_ENV) && cd backend && PYTHONPATH=. uv run --package learnflow-backend python scripts/seed_demo.py

downgrade:  ## Run alembic downgrade (one step)
	$(LOAD_ENV) && uv run alembic -c backend/alembic.ini downgrade -1

sync-prompts:  ## Sync prompts from Langfuse to local files
	$(LOAD_ENV) && cd backend && PYTHONPATH=. uv run --package learnflow-backend python scripts/sync_prompts.py --label production

security-scan-validate:  ## Validate Promptfoo config for tools/security-scan
	cd tools/security-scan && npx promptfoo@latest validate

security-scan-redteam:  ## Run baseline redteam scan. Usage: make security-scan-redteam RUN_ID=<id>
	@if [ "$(origin RUN_ID)" != "command line" ]; then echo "Usage: make security-scan-redteam RUN_ID=<id>"; exit 1; fi
	$(LOAD_ENV) && cd tools/security-scan && \
	  LEARNFLOW_SCAN_RUN_ID=$(RUN_ID) \
	  npx promptfoo@latest redteam run \
	    --output reports/$(RUN_ID)/results.json

security-scan-report:  ## View latest Promptfoo report (no auto-open)
	cd tools/security-scan && npx promptfoo@latest view --no-browser
