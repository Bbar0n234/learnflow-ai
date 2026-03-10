# Implementation Plan: feat-001 — App Skeleton + Config + DB

## Контекст

Первая итерация из `tasklist-backend-core.md`. Создаём каркас FastAPI-приложения с подключением к PostgreSQL — фундамент для всех последующих итераций (модели, репозитории, сервисы, API).

Проект уже имеет:
- uv workspace с `backend/` member (`backend/pyproject.toml`)
- docker-compose с PostgreSQL 17
- `.env.example` / `.env.local.example` с `DATABASE_URL`
- Makefile, ruff, mypy, pre-commit — настроены
- Dockerfile (placeholder CMD)

## Референсы

| Документ | Путь | Что используем |
|----------|------|----------------|
| Workflow | `doc/workflow.md` | Жизненный цикл итерации |
| Conventions | `doc/tech/conventions.md` | Git, именование, code quality |
| Backend arch | `doc/tech/backend.md` | Layered architecture, module structure, config, persistence |
| Vision | `doc/vision.md` | Стек, принципы |
| Tasklist | `doc/tasks/tasklist-backend-core.md` | feat-001 |

## Решение по драйверу (согласовано с архитектором)

**psycopg** (psycopg3) — единый sync+async PostgreSQL драйвер.

- Тот же драйвер, что использует `langgraph-checkpoint-postgres` (AsyncPostgresSaver)
- Один dialect URL `postgresql+psycopg://` для sync (`create_engine`) и async (`create_async_engine`)
- Alembic миграции (feat-002) — тот же драйвер в sync-режиме, без второго пакета
- First-class поддержка в SQLAlchemy 2.0

## Версии инструментов (проверено через PyPI)

| Пакет | Версия |
|-------|--------|
| FastAPI | 0.135.1 |
| SQLAlchemy | 2.0.48 |
| psycopg\[binary\] | 3.3.3 |
| pydantic-settings | 2.13.1 |
| uvicorn | 0.41.0 |
| pydantic | 2.12.5 (уже установлен) |

## Файлы для изменения

| Файл | Действие |
|------|----------|
| `backend/pyproject.toml` | Добавить зависимости (через `uv add`) |
| `backend/app/**` | **Создать** — вся структура пакетов |
| `backend/app/config.py` | **Создать** — Settings class |
| `backend/app/infra/db.py` | **Создать** — async engine, session factory |
| `backend/app/main.py` | **Создать** — app factory, lifespan, health-check |
| `Makefile` | **Изменить** — команда `dev` |
| `Dockerfile` | **Изменить** — CMD |
| `.env.example` | **Изменить** — DATABASE_URL формат |
| `.env.local.example` | **Изменить** — DATABASE_URL формат |

## Шаги реализации

### 0. Git setup

```bash
git fetch origin && git checkout -b feat/001-app-skeleton origin/develop
```

### 1. Зависимости

```bash
uv add --package learnflow-backend fastapi "uvicorn[standard]" "sqlalchemy[asyncio]" "psycopg[binary]" pydantic-settings
```

- `fastapi` — web framework
- `uvicorn[standard]` — ASGI server (uvloop, httptools, watchfiles для --reload)
- `sqlalchemy[asyncio]` — ORM + async расширение
- `psycopg[binary]` — async PostgreSQL driver (C-ускорение через binary)
- `pydantic-settings` — Settings class с загрузкой из env/`.env`

### 2. Структура пакетов `backend/app/`

```
backend/app/
├── __init__.py
├── main.py
├── config.py
├── api/
│   ├── __init__.py
│   ├── deps.py              # пустой placeholder
│   ├── routes/
│   │   └── __init__.py
│   └── schemas/
│       └── __init__.py
├── services/
│   └── __init__.py
├── agent/
│   ├── __init__.py
│   ├── tools/
│   │   └── __init__.py
│   └── skills/
│       └── __init__.py
├── repositories/
│   └── __init__.py
├── models/
│   └── __init__.py
└── infra/
    ├── __init__.py
    └── db.py
```

Все `__init__.py` — пустые. Реализация только в `config.py`, `infra/db.py`, `main.py`.

### 3. `backend/app/config.py`

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    database_url: str = "postgresql+psycopg://learnflow:learnflow@localhost:5432/learnflow"
```

- Единственный параметр для feat-001. Остальные (LLM_API_KEY, CORS) — в будущих итерациях.
- Дефолт — localhost для local dev без `.env`.
- Без `env_prefix` — совпадает с `.env.example`.

### 4. `backend/app/infra/db.py`

```python
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(settings.database_url, echo=False)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

- `expire_on_commit=False` — стандарт для async (предотвращает lazy-load после commit)
- Фабричные функции — engine создаётся в lifespan с конкретными settings

### 5. `backend/app/main.py`

```python
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from sqlalchemy import text

from app.config import Settings
from app.infra.db import create_engine, create_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    engine = create_engine(settings)
    # Fail-fast: verify DB is reachable at startup
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)
    yield
    await engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="LearnFlowAI", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- **Lifespan** — async context manager (актуальный паттерн, `on_startup`/`on_shutdown` deprecated)
- **Fail-fast** — `SELECT 1` при старте: если БД недоступна, приложение не поднимется
- **`app.state`** — engine + session_factory для dependencies (feat-005)
- **Health-check** — `GET /health` → 200

### 6. Обновить `Makefile`

```makefile
dev:  ## Run backend dev server
	uv run --package learnflow-backend uvicorn app.main:app --reload --app-dir backend
```

### 7. Обновить `.env.example` и `.env.local.example`

`DATABASE_URL` → `postgresql+psycopg://...` (вместо `postgresql://...`).

### 8. Обновить `Dockerfile` CMD

```dockerfile
CMD ["uv", "run", "--package", "learnflow-backend", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "backend"]
```

## Верификация (критерии приёмки)

```bash
# 1. Запуск PostgreSQL
make docker-up

# 2. Запуск dev-сервера
make dev
# Ожидание: uvicorn стартует без ошибок, SELECT 1 проходит (fail-fast)

# 2b. Негативный тест: остановить БД, перезапустить сервер
make docker-down && make dev
# Ожидание: сервер НЕ стартует (connection refused)

# 3. Health-check
curl http://localhost:8000/health
# Ожидание: {"status":"ok"}

# 4. Code quality
make check
# Ожидание: ruff check + ruff format --check + mypy — всё проходит
```

## Финальный шаг

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.
