.PHONY: docker-up docker-down docker-build lint format type-check check lint-fe format-fe dev dev-fe test migrate migration downgrade

docker-up:  ## Start PostgreSQL
	docker compose up -d db

docker-down:  ## Stop all containers
	docker compose down

docker-build:  ## Build Docker images
	docker compose build

lint:  ## Run ruff linter
	uv run ruff check .

format:  ## Format Python code
	uv run ruff format .

type-check:  ## Run mypy type checking
	uv run mypy backend/

check:  ## Run all backend checks (CI gate)
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy backend/

lint-fe:  ## Run ESLint on frontend
	cd frontend && npx eslint .

format-fe:  ## Format frontend code with Prettier
	cd frontend && npx prettier --write .

dev:  ## Run backend dev server
	uv run --package learnflow-backend uvicorn app.main:app --reload --app-dir backend

dev-fe:  ## Run frontend dev server
	@echo "Frontend dev server not yet configured (Phase D)"

test:  ## Run pytest
	uv run pytest -c backend/pyproject.toml --rootdir backend

migrate:  ## Run alembic upgrade head
	cd backend && uv run alembic upgrade head

migration:  ## Create new alembic migration (autogenerate). Usage: make migration msg="description"
	cd backend && uv run alembic revision --autogenerate -m "$(msg)"

downgrade:  ## Run alembic downgrade (one step)
	cd backend && uv run alembic downgrade -1
