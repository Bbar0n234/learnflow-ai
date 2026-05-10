.PHONY: docker-up docker-up-db docker-up-redis docker-down docker-build docker-logs lint format type-check check lint-fe check-fe format-fe dev dev-remote dev-fe test migrate migration downgrade migrate-siem sync-prompts security-scan-validate security-scan-redteam security-scan-report

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

type-check:  ## Run mypy type checking
	uv run mypy backend/ services/siem-service/ tools/security-scan/

check:  ## Run all backend checks (CI gate)
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy backend/ services/siem-service/ tools/security-scan/

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

test:  ## Run pytest
	$(LOAD_ENV) && uv run --package learnflow-backend pytest -c backend/pyproject.toml --rootdir backend

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
