# Implementation Plan: chore-003 — Makefile + Dev Workflow

## Context

Итерация `chore-003` завершает Phase C (Infrastructure Setup). Цель — единая точка входа для dev-команд через Makefile, инфраструктура для тестов (pytest), README с инструкцией запуска. Зависимость от chore-002 (code quality tooling) закрыта.

## Текущее состояние

- **uv** 0.9.30, workspace с member `backend`
- **Docker Compose** v2 (`docker compose`, не `docker-compose`)
- **ruff** 0.15.5, **mypy** 1.19.1 — в root `[dependency-groups] dev`
- **ESLint** 10.0.3, **Prettier** 3.8.1 — в frontend devDependencies
- **pytest** — не установлен
- Makefile, tests/ — не существуют
- README — есть, минимальный (заглушка "Quick Start > Coming soon")

## Шаги реализации

### 1. Добавить pytest в зависимости

**Файл:** `pyproject.toml` (root)

Добавить `"pytest>=9.0"` в `[dependency-groups] dev` (единообразно с ruff, mypy, pre-commit).

```toml
[dependency-groups]
dev = ["ruff>=0.15", "mypy>=1.19", "pre-commit>=4.5", "pytest>=9.0"]
```

Выполнить `uv sync` для установки.

### 2. Настроить pytest

**Файл:** `backend/pyproject.toml`

Добавить секцию:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

### 3. Создать директорию для тестов

**Файл:** `backend/tests/__init__.py`

Пустой файл. Директория внутри `backend/` — pytest-конфиг в `backend/pyproject.toml`, тесты для backend-кода.

### 4. Создать Makefile

**Файл:** `Makefile` (root)

```makefile
.PHONY: docker-up docker-down docker-build lint format type-check check lint-fe format-fe dev dev-fe test

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
	@echo "Backend dev server not yet configured (Phase D)"

dev-fe:  ## Run frontend dev server
	@echo "Frontend dev server not yet configured (Phase D)"

test:  ## Run pytest
	uv run pytest -c backend/pyproject.toml --rootdir backend
```

**Детали:**

- `check` — три команды последовательно, make остановится на первой ошибке (AND-семантика)
- `format` — fix mode (пишет файлы), `check` использует `ruff format --check` (read-only)
- `format-fe` — fix mode (`--write`)
- `test` — `-c backend/pyproject.toml` указывает конфиг, `--rootdir backend` задаёт корень для разрешения путей
- `dev` / `dev-fe` — заглушки, будут обновлены в Phase D (не входят в критерии приёмки)

**Известные ограничения (текущий пустой проект):**
- `make type-check` / `make check` → mypy вернёт ошибку "no .py files" до появления Python-кода в backend/. Ожидаемо (задокументировано в chore-002 summary). Решится само при старте Phase D.
- `make test` → pytest вернёт exit 5 (no tests collected). Ожидаемо — "пустой прогон, 0 тестов".

### 5. Обновить README

**Файл:** `README.md`

Содержание:

1. **Заголовок и описание** (существующие)
2. **Prerequisites** — Python 3.12+, uv, Docker, Node.js/npm
3. **Quick Start**
   - Clone + `uv sync`
   - `cp .env.local.example .env.local`
   - `make docker-up`
   - (backend/frontend запуск — Phase D)
4. **Development**
   - Таблица make-команд с описаниями
   - Два режима: Docker (`.env`) / Local dev (`.env.local`)
5. **Documentation** (ссылка на doc/)
6. **License**

### 6. Git workflow

- `git checkout develop && git pull origin develop` (подтянуть актуальный develop с chore-002)
- `git checkout -b chore/003-dev-workflow`
- Коммит: `chore(infra): add Makefile, pytest config, and dev README`
- PR → develop

### 7. Post-implementation

- Обновить `doc/tech/conventions.md`: секция Makefile — добавить `lint-fe`, `format-fe` в список dev-команд
- Обновить `doc/tasks/tasklist-infra.md`: статус chore-003 → ✅ Done, заполнить артефакты
- Создать `doc/tasks/iterations/infra/chore-003-dev-workflow/summary.md`

## Файлы для модификации

| Файл | Действие |
|------|----------|
| `pyproject.toml` | Edit — добавить pytest в dev deps |
| `backend/pyproject.toml` | Edit — добавить `[tool.pytest.ini_options]` |
| `backend/tests/__init__.py` | Create — пустой файл |
| `Makefile` | Create |
| `README.md` | Rewrite |
| `uv.lock` | Auto-update via `uv sync` |
| `doc/tech/conventions.md` | Edit — добавить lint-fe, format-fe в секцию Makefile |
| `doc/tasks/tasklist-infra.md` | Edit — статус + артефакты |
| `doc/tasks/iterations/infra/chore-003-dev-workflow/summary.md` | Create |

## Верификация

```bash
# 1. Критерий: make check запускает lint + format-check + type-check
make check
# Ожидаемо: ruff check и ruff format --check пройдут, mypy вернёт ошибку (no .py files)

# 2. Критерий: make docker-up поднимает PostgreSQL
make docker-up
docker compose ps  # db running
make docker-down

# 3. Критерий: make test запускает pytest
make test
# Ожидаемо: pytest запускается, 0 тестов (exit 5)

# 4. Критерий: README содержит инструкцию запуска
# Ручная проверка содержания

# 5. Дополнительно: все make-таргеты существуют
make -n lint
make -n format
make -n lint-fe
make -n format-fe
```

## Принятые решения

- **Ветка:** chore-002 уже смержен в develop (PR #5). Ветка chore-003 от `origin/develop`.
