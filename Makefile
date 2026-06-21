.PHONY: docker-up docker-up-db docker-up-redis docker-down docker-build docker-logs lint format type-check arch-check check lint-fe check-fe format-fe dev dev-remote dev-fe test test-cov test-fe migrate migration downgrade migrate-siem sync-prompts security-scan-validate security-scan-redteam security-scan-report

# Load .env (base) then .env.local (overrides) into shell environment
LOAD_ENV = set -a && [ -f .env ] && . ./.env; [ -f .env.local ] && . ./.env.local; set +a

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

docker-logs:  ## Show app container logs
	docker compose logs -f app

lint:  ## Run ruff linter
	uv run ruff check .

format:  ## Format Python code (auto-fix safe lint issues + format)
	uv run ruff check --fix .
	uv run ruff format .

# mypy runs per source root: backend and siem-service each own a top-level
# `tests` package, and a single mypy process rejects two same-named modules.
type-check:  ## Run mypy type checking
	uv run mypy backend/
	uv run mypy services/siem-service/
	uv run mypy tools/security-scan/ tools/arch-checker/

arch-check:  ## Run architecture checks (import-linter contracts + AST asserts)
	PYTHONPATH=backend:services/siem-service uv run lint-imports
	uv run python -m arch_checker

check:  ## Run all backend checks (CI gate)
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy backend/
	uv run mypy services/siem-service/
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

dev:  ## Run backend dev server (localhost only)
	$(LOAD_ENV) && uv run --package learnflow-backend uvicorn app.main:app --reload --app-dir backend

dev-remote:  ## Run backend dev server (accessible by IP)
	$(LOAD_ENV) && uv run --package learnflow-backend uvicorn app.main:app --reload --app-dir backend --host 0.0.0.0

dev-fe:  ## Run frontend dev server
	cd frontend && npx vite

test:  ## Run backend + siem-service pytest (exit 5 = "no tests collected" is OK)
	@$(LOAD_ENV) && uv run --package learnflow-backend pytest -c backend/pyproject.toml --rootdir backend backend/tests; ec=$$?; [ $$ec -eq 0 ] || [ $$ec -eq 5 ]
	@$(LOAD_ENV) && uv run --package siem-service pytest -c services/siem-service/pyproject.toml --rootdir services/siem-service services/siem-service/tests; ec=$$?; [ $$ec -eq 0 ] || [ $$ec -eq 5 ]

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

downgrade:  ## Run alembic downgrade (one step)
	$(LOAD_ENV) && uv run alembic -c backend/alembic.ini downgrade -1

sync-prompts:  ## Sync prompts from Langfuse to local files
	$(LOAD_ENV) && uv run python backend/scripts/sync_prompts.py --label production

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
