.PHONY: docker-up docker-up-db docker-up-redis docker-down docker-build docker-logs lint format type-check check lint-fe check-fe format-fe dev dev-remote dev-fe test migrate migration downgrade sync-prompts

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
	uv run --package learnflow-backend mypy backend/

check:  ## Run all backend checks (CI gate)
	uv run ruff check .
	uv run ruff format --check .
	uv run --package learnflow-backend mypy backend/

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

downgrade:  ## Run alembic downgrade (one step)
	$(LOAD_ENV) && uv run alembic -c backend/alembic.ini downgrade -1

sync-prompts:  ## Sync prompts from Langfuse to local files
	$(LOAD_ENV) && uv run python backend/scripts/sync_prompts.py --label production
