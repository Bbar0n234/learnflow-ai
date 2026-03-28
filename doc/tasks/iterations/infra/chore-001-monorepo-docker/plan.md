# Plan: chore-001 — Monorepo + Docker + Environment

## Context

Первая итерация Phase C (Infrastructure Setup). Без рабочей инфраструктуры невозможно начинать реализацию кода. Нужно поднять uv workspace (monorepo), Docker с PostgreSQL, структуру env-файлов.

**Ветка:** `chore/001-monorepo-docker` (от `develop`)

## Состав работ

### 1. Корневой `pyproject.toml` (workspace root)

**Файл:** `/pyproject.toml`

```toml
[project]
name = "learnflow-ai"
version = "0.1.0"
description = "AI-powered learning assistant"
requires-python = ">=3.12"

[tool.uv.workspace]
members = ["backend"]
```

- Workspace root — сам является member (требование uv)
- `members = ["backend"]` — frontend не член workspace (Node.js, управляется npm)
- Без `[build-system]` — root не является пакетом для сборки

### 2. `backend/pyproject.toml` (workspace member)

**Файл:** `/backend/pyproject.toml`

```toml
[project]
name = "learnflow-backend"
version = "0.1.0"
description = "LearnFlowAI backend"
requires-python = ">=3.12"
dependencies = []
```

- Минимальный каркас: имя + Python version
- Без `[build-system]` — app, не library (default `--app --no-package`)
- Зависимости пустые — добавляются в следующих итерациях

### 3. `frontend/package.json` (Node.js scaffold)

**Файл:** `/frontend/package.json`

```json
{
  "name": "learnflow-frontend",
  "version": "0.1.0",
  "private": true,
  "description": "LearnFlowAI frontend"
}
```

- Минимальный каркас, managed by npm
- `private: true` — не публикуется в npm

### 4. `docker-compose.yml`

**Файл:** `/docker-compose.yml`

```yaml
services:
  db:
    image: postgres:17
    restart: unless-stopped
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-learnflow}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-learnflow}
      POSTGRES_DB: ${POSTGRES_DB:-learnflow}
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

- PostgreSQL 17 (latest stable)
- Переменные с дефолтами — работает и без .env
- Named volume `pgdata` для персистентности

### 5. `Dockerfile` (backend)

**Файл:** `/Dockerfile`

```dockerfile
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install dependencies (cached layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=backend/pyproject.toml,target=backend/pyproject.toml \
    uv sync --locked --no-install-project

# Copy project source
COPY . /app

# Install project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

CMD ["uv", "run", "python", "-c", "print('LearnFlowAI backend')"]
```

- Base: `python:3.12-slim` (рекомендация uv docs)
- uv binary из официального образа
- Двухфазная установка: deps → source (Docker layer caching)
- CMD — placeholder, заменится на `uvicorn` в feat-итерации

### 6. `.env.example` + `.env.local.example`

**Файл:** `/.env.example` (Docker mode)
```
# Database
DATABASE_URL=postgresql://learnflow:learnflow@db:5432/learnflow
POSTGRES_USER=learnflow
POSTGRES_PASSWORD=learnflow
POSTGRES_DB=learnflow
POSTGRES_PORT=5432

# LLM
LLM_API_KEY=your-api-key-here
LLM_MODEL=claude-sonnet-4-20250514
```

**Файл:** `/.env.local.example` (local dev mode)
```
# Database (PostgreSQL in Docker, app locally)
DATABASE_URL=postgresql://learnflow:learnflow@localhost:5432/learnflow
POSTGRES_USER=learnflow
POSTGRES_PASSWORD=learnflow
POSTGRES_DB=learnflow
POSTGRES_PORT=5432

# LLM
LLM_API_KEY=your-api-key-here
LLM_MODEL=claude-sonnet-4-20250514
```

- Разница — `db` vs `localhost` в DATABASE_URL
- `.env` и `.env.local` уже в `.gitignore` — example-файлы коммитятся

### 7. `.dockerignore`

**Файл:** `/.dockerignore`

```
.git
.venv
__pycache__
*.pyc
.env
.env.local
node_modules
doc/
.claude/
.mypy_cache
.ruff_cache
.pytest_cache
.gitignore
LICENSE
README.md
```

### 8. `.gitignore` — дополнение

Добавить `node_modules/` в существующий `.gitignore` (Python-шаблон не содержит Node.js записей).

## Заметки

- **Dockerfile `uv:latest`** — для scaffold допустимо. При переходе к реальным сборкам зафиксировать версию (e.g. `uv:0.9`).

## Порядок выполнения

1. Создать ветку `chore/001-monorepo-docker` от `develop`
2. Добавить `node_modules/` в `.gitignore`
3. Создать `backend/pyproject.toml`
4. Создать `frontend/package.json`
5. Создать корневой `pyproject.toml` (workspace)
6. Запустить `uv sync` — проверить что проходит
7. Создать `.env.example`, `.env.local.example`
8. Создать `docker-compose.yml`
9. Создать `.dockerignore`
10. Создать `Dockerfile`
11. Проверить `docker compose up db` + подключение psql
12. Обновить статус в tasklist

## Verification

```bash
# 1. uv sync проходит без ошибок
uv sync

# 2. PostgreSQL поднимается и доступен
docker compose up -d db
# подождать старта, затем:
docker compose exec db psql -U learnflow -d learnflow -c "SELECT 1;"

# 3. Проверить содержимое .env.example
grep -E "DATABASE_URL|LLM_API_KEY|LLM_MODEL" .env.example

# 4. Проверить содержимое .env.local.example
grep -E "DATABASE_URL|LLM_API_KEY|LLM_MODEL" .env.local.example
# DATABASE_URL должен содержать localhost

# 5. Docker build (опционально — Dockerfile базовый)
docker compose down
```

## Файлы для создания

| Файл | Действие |
|------|----------|
| `pyproject.toml` | Create |
| `backend/pyproject.toml` | Create |
| `frontend/package.json` | Create |
| `docker-compose.yml` | Create |
| `Dockerfile` | Create |
| `.env.example` | Create |
| `.env.local.example` | Create |
| `.dockerignore` | Create |
| `.gitignore` | Edit (добавить `node_modules/`) |
| `doc/tasks/tasklist-infra.md` | Edit (статус → 🚧) |
