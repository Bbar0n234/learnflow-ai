# Tasklist: Infrastructure Setup

## Контекст

Фундамент проекта: monorepo, tooling, контейнеризация, база данных, dev-команды. Без рабочей инфраструктуры невозможно начинать код в других скоупах.

**Документы:** [vision.md](../vision.md) (стек), [conventions.md](../tech/conventions.md) (соглашения)

**Зависимости:** нет (первый скоуп)

## Легенда

- 📋 Planned
- 🚧 In Progress
- ✅ Done
- ⏸️ Paused
- ❌ Cancelled

## Overview

| Итерация | Статус | Закрывает |
|----------|--------|-----------|
| chore-001 | ✅ Done | Monorepo + Docker + env |
| chore-002 | ✅ Done | Code quality tooling |
| chore-003 | ✅ Done | Makefile + dev workflow |

## Быстро меняющиеся инструменты

| Инструмент | Источник |
|-----------|----------|
| uv | скилл uv-package-manager |
| ESLint | MCP `@eslint/mcp` |
| ruff, mypy, Prettier | firecrawl / web search при необходимости |
| PostgreSQL, Docker | firecrawl / web search при необходимости |

## Итерации

### chore-001: Monorepo + Docker + Environment

**Цель:** поднять uv workspace (monorepo, member: backend; frontend — отдельный Node.js проект, управляется npm), docker-compose с PostgreSQL, структуру environment-файлов для двух режимов запуска (Docker и local dev).

**Статус:** ✅ Done
**Blocked by:** —
**Закрывает:** Phase C: project skeleton, containerization, database
**Ветка:** `chore/001-monorepo-docker`

#### Состав работ
- [x] Корневой `pyproject.toml` (uv workspace, объявление members)
- [x] Минимальный `backend/pyproject.toml` (имя пакета, Python version)
- [x] Минимальный `frontend/package.json` (каркас)
- [x] `docker-compose.yml` (PostgreSQL + volume)
- [x] `Dockerfile` (backend — базовый, собирает Python-окружение)
- [x] `.env.example` + `.env.local.example` (два уровня: Docker и local dev)
- [x] `.dockerignore`

#### Критерии приёмки
- [x] `uv sync` проходит без ошибок
- [x] `docker-compose up db` поднимает PostgreSQL, подключение через `psql` работает
- [x] `.env.example` содержит `DATABASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- [x] `.env.local.example` содержит те же переменные с localhost-адресами

#### Артефакты
- [Plan](iterations/infra/chore-001-monorepo-docker/plan.md)
- [Summary](iterations/infra/chore-001-monorepo-docker/summary.md)

---

### chore-002: Code Quality Tooling

**Цель:** настроить трёхуровневую защиту качества кода (ruff format → ruff check → mypy) для backend и ESLint + Prettier для frontend. MVP-каркас: базовые правила, дорабатываем по мере столкновений.

**Статус:** ✅ Done
**Blocked by:** infra/chore-001
**Закрывает:** Phase C: code quality, pre-commit hooks
**Ветка:** `chore/002-code-quality`

#### Состав работ
- [x] `ruff.toml` (правила: E, W, F, B, I, SIM; ignore E501; per-file exceptions)
- [x] mypy-конфигурация в `backend/pyproject.toml` (disallow_untyped_defs, pydantic plugin)
- [x] `.pre-commit-config.yaml` (ruff check + ruff format + mypy)
- [x] Frontend: ESLint (`@typescript-eslint/recommended` + prettier) + Prettier (базовый конфиг)
- [x] MCP `@eslint/mcp` — подключить в `.mcp.json` проекта

#### Критерии приёмки
- [x] `ruff check .` и `ruff format --check .` проходят на пустом проекте
- [x] `mypy .` проходит без ошибок (pre-commit скипает на пустом backend, см. summary)
- [x] `git commit` триггерит pre-commit хуки
- [x] Frontend: `eslint` и `prettier --check` проходят

#### Артефакты
- [Plan](iterations/infra/chore-002-code-quality/plan.md)
- [Summary](iterations/infra/chore-002-code-quality/summary.md)

---

### chore-003: Makefile + Dev Workflow

**Цель:** единая точка входа для dev-команд (Makefile), заготовка для тестов (pytest config + директория), README с инструкцией запуска.

**Статус:** ✅ Done
**Blocked by:** infra/chore-002
**Закрывает:** Phase C: dev commands, testing infra, README
**Ветка:** `chore/003-dev-workflow`

#### Состав работ
- [x] `Makefile` (docker-up/down/build, lint, format, type-check, check, lint-fe, format-fe, dev, dev-fe, test)
- [x] pytest-конфигурация в `backend/pyproject.toml` (`[tool.pytest.ini_options]`)
- [x] Директория `tests/` с `__init__.py`
- [x] README с инструкцией запуска (Docker и local dev)

#### Критерии приёмки
- [x] `make check` запускает lint + format-check + type-check
- [x] `make docker-up` поднимает PostgreSQL
- [x] `make test` запускает pytest (пустой прогон, 0 тестов)
- [x] README: новый разработчик может запустить проект по инструкции

#### Артефакты
- [Plan](iterations/infra/chore-003-dev-workflow/plan.md)
- [Summary](iterations/infra/chore-003-dev-workflow/summary.md)
