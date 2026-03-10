# Tasklist: Backend Core

## Контекст

Persistence + Service + API слои бэкенда — всё кроме агента. Скелет приложения: модели, репозитории, сервисы, REST-эндпоинты, SSE-каркас.

**Документы:** [backend.md](../tech/backend.md) (архитектура, API, schemas, persistence)

**Зависимости:** Infrastructure Setup

## Легенда

- 📋 Planned
- 🚧 In Progress
- ✅ Done
- ⏸️ Paused
- ❌ Cancelled

## Overview

| Итерация | Статус | Закрывает |
|----------|--------|-----------|
| feat-001 | ✅ Done | App skeleton, config, DB connection |
| feat-002 | ✅ Done | ORM models, Alembic migrations |
| feat-003 | ✅ Done | Repository Layer (CRUD) |
| feat-004 | 📋 Planned | Service Layer + Agent/Sphere interfaces |
| feat-005 | 📋 Planned | API Layer (REST + SSE каркас) |

## Быстро меняющиеся инструменты

| Инструмент | Источник |
|-----------|----------|
| FastAPI | firecrawl → fastapi.tiangolo.com при необходимости |
| SQLAlchemy 2.x (async) | `inspect` пакета, firecrawl → docs.sqlalchemy.org |
| Alembic | firecrawl → alembic.sqlalchemy.org |
| pydantic / pydantic-settings | `inspect` пакета, firecrawl → docs.pydantic.dev |
| uv | скилл uv-package-manager |

## Итерации

### feat-001: App Skeleton + Config + DB

**Цель:** каркас FastAPI-приложения с подключением к PostgreSQL — фундамент для всех последующих итераций.

**Статус:** ✅ Done
**Blocked by:** infra/chore-001
**Закрывает:** v1: project skeleton (backend), DB connection
**Ветка:** `feat/001-app-skeleton`

#### Состав работ
- [x] Структура пакетов `app/` (api/, services/, repositories/, models/, agent/, infra/)
- [x] `main.py` — app factory, lifespan (init/shutdown DB)
- [x] `config.py` — Settings (pydantic-settings), загрузка из `.env`
- [x] `infra/db.py` — async engine, async session factory
- [x] Зависимости в `backend/pyproject.toml` (fastapi, uvicorn, sqlalchemy, psycopg, pydantic-settings)

#### Критерии приёмки
- [x] `uv run uvicorn app.main:app` стартует без ошибок
- [x] Health-check endpoint (`GET /health`) отвечает 200
- [x] Приложение подключается к PostgreSQL из docker-compose
- [x] `ruff check` и `mypy` проходят

#### Артефакты
- [plan.md](iterations/backend-core/feat-001-app-skeleton/plan.md)
- [summary.md](iterations/backend-core/feat-001-app-skeleton/summary.md)

---

### feat-002: SQLAlchemy Models + Alembic Migrations

**Цель:** ORM-модели для app-managed таблиц и инфраструктура миграций.

**Статус:** ✅ Done
**Blocked by:** backend-core/feat-001
**Закрывает:** v1: persistence layer (app-managed tables)
**Ветка:** `feat/002-models-migrations`

#### Состав работ
- [x] ORM-модели: User, Project, ThreadView, Artifact (relationships, constraints)
- [x] Alembic setup (alembic.ini, env.py с async engine, versions/)
- [x] Initial migration (автогенерация из моделей)

#### Критерии приёмки
- [x] `alembic upgrade head` создаёт все таблицы в PostgreSQL
- [x] `alembic downgrade base` откатывает
- [x] Relationships корректны (FK constraints)
- [x] `ruff check` и `mypy` проходят

#### Артефакты
- [plan.md](iterations/backend-core/feat-002-models-migrations/plan.md)
- [summary.md](iterations/backend-core/feat-002-models-migrations/summary.md)

---

### feat-003: Repository Layer

**Цель:** async CRUD-репозитории для каждой app-managed сущности.

**Статус:** ✅ Done
**Blocked by:** backend-core/feat-002
**Закрывает:** v1: data access layer
**Ветка:** `feat/003-repository-layer`

#### Состав работ
- [x] UserRepository (get_or_create by name, get by id)
- [x] ProjectRepository (CRUD + list by user)
- [x] ThreadViewRepository (CRUD + list by project + recent across projects)
- [x] ArtifactRepository (CRUD + list by project)
- [x] Паттерн dependency injection (session через конструктор)

#### Критерии приёмки
- [x] Все CRUD-операции для каждой сущности реализованы
- [x] Async session корректно пробрасывается
- [x] `ruff check` и `mypy` проходят

#### Артефакты
- [plan.md](iterations/backend-core/feat-003-repository-layer/plan.md)
- [summary.md](iterations/backend-core/feat-003-repository-layer/summary.md)

---

### feat-004: Service Layer

**Цель:** сервисный слой — оркестрация между API и Repository/Agent, определение интерфейсов для Agent Runtime.

**Статус:** 📋 Planned
**Blocked by:** backend-core/feat-003
**Закрывает:** v1: business logic layer, agent/sphere interface contracts
**Ветка:** `feat/004-service-layer`

#### Состав работ
- [ ] ProjectService (CRUD-оркестрация, бизнес-правила)
- [ ] ArtifactService (CRUD-оркестрация)
- [ ] ChatService — thin layer: маппинг chat → thread, управление ThreadView, делегирование в AgentRunner
- [ ] AgentRunner — Protocol (stream, get_history, cancel) + stub-реализация
- [ ] SphereService — Protocol (get, update) + stub-реализация
- [ ] Wiring: паттерн для инъекции зависимостей в сервисы

#### Критерии приёмки
- [ ] Сервисы вызывают репозитории через инъекцию
- [ ] AgentRunner и SphereService определены как Protocol
- [ ] Stub-реализации позволяют вызывать API без реального агента
- [ ] `ruff check` и `mypy` проходят

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-005: API Layer (REST + SSE каркас)

**Цель:** полный HTTP-интерфейс приложения — все REST endpoints (включая PDF-экспорт артефактов через pandoc/weasyprint), SSE-каркас для стриминга, auth dependency.

**Статус:** 📋 Planned
**Blocked by:** backend-core/feat-004
**Закрывает:** v1: REST API, SSE streaming protocol, auth dependency (MVP), PDF-экспорт артефактов
**Ветка:** `feat/005-api-layer`

#### Состав работ
- [ ] `deps.py` — dependencies: DB session, user extraction (X-User-Name), инъекция сервисов
- [ ] Pydantic schemas (request/response модели для всех ресурсов)
- [ ] Роутеры: projects, chats, messages, artifacts, sphere
- [ ] SSE endpoint (`POST /messages`) — формат событий по протоколу, работает через AgentRunner stub
- [ ] PDF-экспорт артефактов: конвертация Markdown → PDF (pandoc / weasyprint), зависимость в pyproject.toml и Dockerfile
- [ ] CORS middleware

#### Критерии приёмки
- [ ] Все endpoints из backend.md реализованы и отвечают корректными статусами
- [ ] Pydantic-валидация работает (422 на невалидные данные)
- [ ] SSE endpoint отдаёт поток событий в задокументированном формате (через stub)
- [ ] `X-User-Name` корректно извлекается, запросы без заголовка — 401/422
- [ ] `ruff check` и `mypy` проходят

#### Артефакты
<!-- Заполняется по мере работы -->
