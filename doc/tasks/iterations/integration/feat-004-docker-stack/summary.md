# Post-Implementation Summary: feat-004 — Docker Full Stack

## Результат

Полный стек в docker-compose: `make docker-build && make docker-up` поднимает рабочее приложение на `http://localhost:8000`. Single Container pattern — FastAPI отдаёт и API, и фронтенд-статику из одного контейнера. Alembic autogenerate защищён фильтром от конфликтов с LangGraph-таблицами.

## Отклонения от плана

### 1. SPA fallback guard — расширен на точный `/api` путь (ревью-фикс)

**План:** guard проверял `full_path.startswith("api/")`.

**Факт:** при ревью обнаружено, что `GET /api` (без trailing slash) проходил мимо guard и возвращал `index.html` вместо JSON 404. Расширен до `full_path == "api" or full_path.startswith("api/")`.

### 2. LANGGRAPH_TABLES — расширен набор таблиц

**План:** 6 таблиц (`checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`, `store`, `store_vectors`).

**Факт:** при верификации через исходный код `langgraph-checkpoint-postgres` и `langgraph.store.postgres` обнаружены ещё 2 таблицы: `store_migrations` и `vector_migrations`. Итого 8 таблиц в фильтре.

### 3. Форматирование — исправлен долг из предыдущих итераций

4 файла из develop не проходили `ruff format --check` (не связаны с feat-004): `graph.py`, `runner.py`, `artifact.py`, миграция `6b69e2cad2ae`. Отформатированы в рамках итерации.

## Архитектурные решения

Все решения были согласованы с архитектором на этапе планирования, реализованы без отклонений:

- **Single Container** — один image: FastAPI + frontend dist. Node.js только в build stage
- **`/api` prefix** — все API routes под `/api`, SPA fallback на catch-all, `/health` и `/docs` на root level
- **`include_object` фильтр** — Alembic autogenerate игнорирует LangGraph-managed таблицы

## Затронутые файлы

| Файл | Изменение |
|------|-----------|
| `backend/app/main.py` | `/api` prefix на роутеры, health check с DB проверкой, SPA static serving с path traversal protection |
| `backend/alembic/env.py` | `include_object` фильтр для 8 LangGraph-таблиц |
| `frontend/vite.config.ts` | Убран `rewrite` из proxy (backend теперь ожидает `/api`) |
| `Dockerfile` | Multi-stage: Node.js build + Python runtime, точечные COPY, entrypoint |
| `backend/entrypoint.sh` | **Новый** — Alembic migrate + uvicorn startup |
| `docker-compose.yml` | + app service с healthcheck, healthcheck для db, `depends_on: service_healthy` |
| `Makefile` | `docker-up` → full stack, + `docker-up-db`, `docker-logs` |
| `.dockerignore` | + `frontend/node_modules`, `frontend/dist`, `.firecrawl` |
| `README.md` | Quick Start: Docker full stack + Local dev |
| `doc/tech/backend.md` | Примечание о `/api` prefix, health check |
| `doc/tech/conventions.md` | Новые Makefile-команды |
| `doc/tasks/tasklist-integration.md` | feat-004 статус → Done |
| `doc/tasks/iterations/integration/feat-004-docker-stack/plan.md` | Implementation plan |
| `doc/tasks/iterations/integration/feat-004-docker-stack/summary.md` | Этот документ |
