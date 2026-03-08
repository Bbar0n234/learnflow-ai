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
| chore-001 | 📋 Planned | Monorepo + Docker + env |
| chore-002 | 📋 Planned | Code quality tooling |
| chore-003 | 📋 Planned | Makefile + dev workflow |

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

**Статус:** 📋 Planned
**Blocked by:** —
**Закрывает:** Phase C: project skeleton, containerization, database
**Ветка:** `chore/001-monorepo-docker`

#### Состав работ
- [ ] Корневой `pyproject.toml` (uv workspace, объявление members)
- [ ] Минимальный `backend/pyproject.toml` (имя пакета, Python version)
- [ ] Минимальный `frontend/package.json` (каркас)
- [ ] `docker-compose.yml` (PostgreSQL + volume)
- [ ] `Dockerfile` (backend — базовый, собирает Python-окружение)
- [ ] `.env.example` + `.env.local.example` (два уровня: Docker и local dev)
- [ ] `.dockerignore`

#### Критерии приёмки
- [ ] `uv sync` проходит без ошибок
- [ ] `docker-compose up db` поднимает PostgreSQL, подключение через `psql` работает
- [ ] `.env.example` содержит `DATABASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- [ ] `.env.local.example` содержит те же переменные с localhost-адресами

#### Артефакты
<!-- Заполняется по мере работы -->

---

### chore-002: Code Quality Tooling

**Цель:** настроить трёхуровневую защиту качества кода (ruff format → ruff check → mypy) для backend и ESLint + Prettier для frontend. MVP-каркас: базовые правила, дорабатываем по мере столкновений.

**Статус:** 📋 Planned
**Blocked by:** infra/chore-001
**Закрывает:** Phase C: code quality, pre-commit hooks
**Ветка:** `chore/002-code-quality`

#### Состав работ
- [ ] `ruff.toml` (правила: E, W, F, B, I, SIM; ignore E501; per-file exceptions)
- [ ] mypy-конфигурация в `backend/pyproject.toml` (disallow_untyped_defs, pydantic plugin)
- [ ] `.pre-commit-config.yaml` (ruff check + ruff format + mypy)
- [ ] Frontend: ESLint (`@typescript-eslint/recommended` + prettier) + Prettier (базовый конфиг)
- [ ] MCP `@eslint/mcp` — подключить в `.mcp.json` проекта

#### Критерии приёмки
- [ ] `ruff check .` и `ruff format --check .` проходят на пустом проекте
- [ ] `mypy .` проходит без ошибок
- [ ] `git commit` триггерит pre-commit хуки
- [ ] Frontend: `eslint` и `prettier --check` проходят

#### Артефакты
<!-- Заполняется по мере работы -->

---

### chore-003: Makefile + Dev Workflow

**Цель:** единая точка входа для dev-команд (Makefile), заготовка для тестов (pytest config + директория), README с инструкцией запуска.

**Статус:** 📋 Planned
**Blocked by:** infra/chore-002
**Закрывает:** Phase C: dev commands, testing infra, README
**Ветка:** `chore/003-dev-workflow`

#### Состав работ
- [ ] `Makefile` (docker-up/down/build, lint, format, type-check, check, lint-fe, format-fe, dev, dev-fe, test)
- [ ] pytest-конфигурация в `backend/pyproject.toml` (`[tool.pytest.ini_options]`)
- [ ] Директория `tests/` с `__init__.py`
- [ ] README с инструкцией запуска (Docker и local dev)

#### Критерии приёмки
- [ ] `make check` запускает lint + format-check + type-check
- [ ] `make docker-up` поднимает PostgreSQL
- [ ] `make test` запускает pytest (пустой прогон, 0 тестов)
- [ ] README: новый разработчик может запустить проект по инструкции

#### Артефакты
<!-- Заполняется по мере работы -->
