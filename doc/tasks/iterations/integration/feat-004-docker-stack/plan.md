# Implementation Plan: feat-004 — Docker Full Stack

## Context

Итерация feat-003 (SSE E2E) завершена, все зависимости feat-004 закрыты. Цель — полный стек в docker-compose: `make docker-up` поднимает рабочее приложение в браузере. Сейчас в docker-compose только PostgreSQL, backend и frontend запускаются локально.

**Референсы:**
- Таск-лист: `doc/tasks/tasklist-integration.md` (feat-004)
- Workflow: `doc/workflow.md`
- Conventions: `doc/tech/conventions.md` (Git, Docker, Makefile, env-файлы)
- Backend spec: `doc/tech/backend.md`
- Frontend spec: `doc/tech/frontend.md`
- Vision: `doc/vision.md` (MVP критерии)

## Архитектурные решения (согласованы с архитектором)

### Single Container (Pattern B)

**Выбор:** Backend служит и API, и фронтенд-статикой из одного контейнера (app + db в docker-compose).

**Обоснование:**
- Frontend SPA после `npm run build` — просто статические файлы (index.html + assets). Vite и Node.js не нужны в runtime
- На VM уже стоит Nginx (basic auth, домен) → один `proxy_pass :8000` → всё работает
- Нет cross-origin проблем — всё на одном origin
- CI/CD: один image, один build, один push
- Переход на отдельные контейнеры (Pattern C) при необходимости — ~30 минут работы

**Следствие:** backend-роуты получают префикс `/api`, чтобы не конфликтовать с SPA-маршрутами фронтенда. Frontend уже использует `/api` как baseURL — **изменения в frontend-коде не нужны**.

**Маршрутизация в FastAPI:**
1. `/api/*` → API routes (зарегистрированы первыми, матчатся первыми)
2. `/health` → Health check (без prefix)
3. `/assets/*` → StaticFiles mount (JS, CSS из Vite build)
4. `/*` → SPA catch-all → index.html

### Одна БД + include_object фильтр

**Выбор:** Одна PostgreSQL база `learnflow` для app-таблиц (Alembic) и LangGraph-таблиц (.setup()). Фильтр `include_object` в `env.py` исключает LangGraph-таблицы из autogenerate.

**Обоснование:**
- Соответствует архитектуре из backend.md: "Одна PostgreSQL база, два механизма управления"
- Минимальное изменение (~10 строк в env.py)
- Отдельная БД для LangGraph (как в скрипте из другого проекта) не даёт преимуществ для MVP
- Решает потенциальный конфликт: autogenerate не пытается удалить LangGraph-таблицы

## Версии инструментов (верифицированы)

| Инструмент | Версия | Примечания |
|-----------|--------|------------|
| Docker Compose | v5.1.0 | Compose Spec (без `version:`), `depends_on.condition`, `healthcheck` |
| Vite | 7.3.1 | `server.proxy` — стабильный API, без breaking changes |
| FastAPI | 0.135.1 | `StaticFiles(html=True)`, `app.mount()` — стандартный Starlette API |
| Node.js | 22.22.0 | Для сборки frontend |

## Шаги реализации

### 0. Ветка

```bash
git fetch origin && git checkout -b feat/004-docker-stack origin/develop
```

### 1. Backend: добавить `/api` prefix

**Файл:** `backend/app/main.py`

Изменить `include_router` — добавить `prefix="/api"` ко всем роутерам:

```python
api_prefix = "/api"
app.include_router(projects.router, prefix=api_prefix)
app.include_router(chats.router, prefix=api_prefix)
app.include_router(messages.router, prefix=api_prefix)
app.include_router(artifacts.router, prefix=api_prefix)
app.include_router(sphere.router, prefix=api_prefix)
```

`GET /health` остаётся на root level (без prefix) — используется для Docker health check.

Swagger UI (`/docs`) тоже на root level — FastAPI генерирует его автоматически, включая `/api`-роуты.

### 2. Backend: serving frontend static files

**Файл:** `backend/app/main.py`

Добавить в `create_app()` после регистрации роутеров:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi import HTTPException

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend" / "dist"

# Serve frontend static files (only when dist exists — Docker mode)
if FRONTEND_DIR.exists():
    frontend_resolved = FRONTEND_DIR.resolve()

    # JS, CSS, images из Vite build
    app.mount("/assets", StaticFiles(directory=str(frontend_resolved / "assets")), name="assets")

    # SPA fallback: любой неизвестный путь → index.html
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str) -> FileResponse:
        # Guard: неизвестные /api/* пути → 404 JSON, а не index.html
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")

        # Path traversal protection: resolve и проверить что внутри FRONTEND_DIR
        file_path = (frontend_resolved / full_path).resolve()
        if file_path.is_file() and file_path.is_relative_to(frontend_resolved):
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_resolved / "index.html"))
```

**Безопасность:** `resolve()` + `is_relative_to()` предотвращает path traversal (`../../etc/passwd`). Guard на `api/` возвращает 404 JSON для неизвестных API-путей вместо index.html.

**Порядок важен:** API routes (с `/api` prefix) регистрируются первыми → Starlette матчит их первыми → catch-all `/{full_path:path}` срабатывает только для фронтенд-маршрутов.

**В dev-режиме** (local dev без Docker): `frontend/dist` не существует → static serving не подключается → backend работает как раньше, фронтенд через Vite dev server с proxy.

### 3. Backend: health check с проверкой DB

**Файл:** `backend/app/main.py`

Заменить текущий health endpoint:

```python
from fastapi import Request

@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    async with request.app.state.engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    return {"status": "ok"}
```

При недоступности DB → исключение → FastAPI вернёт 500 → docker compose health check падает.

### 4. Alembic: include_object фильтр для LangGraph-таблиц

**Файл:** `backend/alembic/env.py`

Добавить фильтр, чтобы `--autogenerate` игнорировал LangGraph-managed таблицы:

```python
LANGGRAPH_TABLES = {
    "checkpoints", "checkpoint_blobs", "checkpoint_writes",
    "checkpoint_migrations", "store", "store_vectors",
}

def include_object(
    object: sa.schema.SchemaItem,
    name: str | None,
    type_: str,
    reflected: bool,
    compare_to: sa.schema.SchemaItem | None,
) -> bool:
    if type_ == "table" and name in LANGGRAPH_TABLES:
        return False
    return True
```

Добавить `include_object=include_object` в оба вызова `context.configure()` (online и offline).

**Важно:** набор таблиц `LANGGRAPH_TABLES` зависит от версии `langgraph-checkpoint-postgres` (сейчас >=2.0). При реализации — верифицировать реальные таблицы через `\dt` в psql после `setup()`, чтобы список был точным.

**Порядок инициализации в Docker:**
1. `entrypoint.sh` → `alembic upgrade head` (создаёт app-таблицы)
2. `uvicorn` → lifespan → `checkpointer.setup()` + `store.setup()` (создаёт LangGraph-таблицы с IF NOT EXISTS)
3. Конфликтов нет — каждый управляет только своими таблицами

### 5. Vite: убрать rewrite из proxy

**Файл:** `frontend/vite.config.ts`

Backend теперь ожидает `/api` prefix. Rewrite больше не нужен:

```typescript
server: {
  proxy: {
    "/api": {
      target: "http://localhost:8000",
      changeOrigin: true,
      // rewrite убран — backend теперь ожидает /api prefix
    },
  },
},
```

### 6. Dockerfile: multi-stage (frontend build + backend)

**Файл:** `Dockerfile` (переписать существующий)

```dockerfile
# Stage 1: Build frontend
FROM node:22-alpine AS frontend-build
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Backend + frontend dist
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && apt-get install -y --no-install-recommends \
    wkhtmltopdf curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=backend/pyproject.toml,target=backend/pyproject.toml \
    uv sync --locked --no-install-project

# Copy project source
COPY backend/ /app/backend/
COPY configs/ /app/configs/
COPY skills/ /app/skills/
COPY pyproject.toml uv.lock /app/

# Install project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

# Copy frontend build output
COPY --from=frontend-build /build/dist /app/frontend/dist

# Entrypoint: migrations + uvicorn
COPY backend/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/app/entrypoint.sh"]
```

**Изменения vs текущий Dockerfile:**
- Добавлен frontend build stage (Node.js остаётся только в build stage, не попадает в финальный image)
- `COPY . /app` заменён на точечные COPY (backend, configs, skills, frontend/dist) — явнее и чище
- Добавлен `curl` для health check
- Добавлен entrypoint script

### 7. Entrypoint script

**Новый файл:** `backend/entrypoint.sh`

```bash
#!/bin/bash
set -e

echo "Running database migrations..."
uv run alembic -c backend/alembic.ini upgrade head

echo "Starting server..."
exec uv run --package learnflow-backend uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --app-dir backend
```

### 8. docker-compose.yml: добавить app service + health checks

**Файл:** `docker-compose.yml`

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
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-learnflow} -d ${POSTGRES_DB:-learnflow}"]
      interval: 5s
      timeout: 5s
      retries: 5

  app:
    build: .
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file:
      - .env
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

volumes:
  pgdata:
```

### 9. Makefile: обновить Docker-команды

**Файл:** `Makefile`

```makefile
docker-up:  ## Start full stack (app + db)
	docker compose up -d

docker-up-db:  ## Start only PostgreSQL (for local dev)
	docker compose up -d db

docker-down:  ## Stop all containers
	docker compose down

docker-build:  ## Build Docker images
	docker compose build

docker-logs:  ## Show app container logs
	docker compose logs -f app
```

`docker-up` теперь поднимает полный стек. Для local dev (DB only) — `docker-up-db`.

### 10. .dockerignore: обновить

**Файл:** `.dockerignore`

```
.git
.venv
__pycache__
*.pyc
.env
.env.local
node_modules
frontend/node_modules
frontend/dist
doc/
.claude/
.mypy_cache
.ruff_cache
.pytest_cache
.firecrawl
frontend/.firecrawl
frontend/.claude
.gitignore
LICENSE
```

Изменения: убрать `README.md` из exclude, добавить `frontend/node_modules`, `frontend/dist` (собирается в Docker), `.firecrawl`.

### 11. README.md: обновить Quick Start

Обновить секции Quick Start и Make Commands для Docker full stack:

- Два режима: Docker (full stack) и Local dev (DB в Docker, app локально)
- `make docker-build && make docker-up` → приложение доступно на `http://localhost:8000`
- `make docker-up-db` → только PostgreSQL (для local dev)
- Инструкция: скопировать `.env.example` → `.env`, прописать API ключи

## Файлы для изменения

| Файл | Действие | Описание |
|------|----------|----------|
| `backend/app/main.py` | Modify | `/api` prefix, static serving, health check |
| `backend/alembic/env.py` | Modify | `include_object` фильтр для LangGraph-таблиц |
| `frontend/vite.config.ts` | Modify | Убрать proxy rewrite |
| `Dockerfile` | Rewrite | Multi-stage: frontend build + backend |
| `docker-compose.yml` | Modify | Добавить app service, health checks |
| `Makefile` | Modify | docker-up → full stack, добавить docker-up-db, docker-logs |
| `.dockerignore` | Modify | Добавить frontend/node_modules, frontend/dist, .firecrawl |
| `README.md` | Modify | Docker Quick Start |
| `backend/entrypoint.sh` | **Create** | Миграции + запуск uvicorn |

## Существующий код для переиспользования

- `Dockerfile` — текущий шаблон backend-сборки с uv (кеширование слоёв, wkhtmltopdf)
- `docker-compose.yml` — текущий db service
- `backend/app/main.py:122` — `GET /health` endpoint (расширяем проверкой DB)
- `frontend/src/shared/api/client.ts:14` — `VITE_API_URL` env var уже поддерживается
- `backend/app/config.py` — `cors_origins` уже парсит JSON из env var

## Верификация

### 1. Backend с `/api` prefix (local dev)
```bash
make dev       # backend на :8000
make dev-fe    # frontend на :5173
# Открыть http://localhost:5173 → всё работает через Vite proxy
# curl http://localhost:8000/api/projects → JSON response
# curl http://localhost:8000/health → {"status": "ok"}
# http://localhost:8000/docs → Swagger UI показывает /api/* роуты
```

### 2. Alembic autogenerate (проверка фильтра)
```bash
make migration msg="test"
# Убедиться, что сгенерированная миграция НЕ содержит drop_table для LangGraph-таблиц
# Удалить тестовую миграцию после проверки
```

### 3. Docker full stack
```bash
# Настроить .env с реальными API ключами
make docker-build && make docker-up
# Дождаться health check: docker compose ps → healthy
make docker-logs  # проверить логи: migrations OK, server started

# Открыть http://localhost:8000 → frontend загружается
# Создать проект → отправить сообщение → SSE стриминг работает
# Проверить SPA routing: F5 на /projects/{id} → страница загружается
# Проверить персистентность: docker compose down && docker compose up -d → данные на месте
```

### 4. Lint & type-check
```bash
make check      # ruff + mypy
make lint-fe    # eslint
```

### 5. Clean shutdown
```bash
make docker-down  # все контейнеры остановлены, volumes сохранены
```

## Финальный шаг

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.
