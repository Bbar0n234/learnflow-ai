# Tasklist: Production Readiness (v1.1)

## Контекст

MVP (v1) завершён и развёрнут. Цель v1.1 — довести до production-ready: аутентификация, observability, CI/CD, автоматизация деплоя.

**Документы:** [roadmap.md](../product/roadmap.md), [vision.md](../vision.md), [security/](../security/)

**Зависимости:** Integration & Polish (tasklist-integration.md) ✅

## Легенда

- 📋 Planned
- 🚧 In Progress
- ✅ Done
- ⏸️ Paused
- ❌ Cancelled

## Overview

| Итерация | Статус | Закрывает |
|----------|--------|-----------|
| feat-001 | ✅ Done | Logging (backend + frontend + Docker) |
| feat-002 | 📋 Planned | Аутентификация (JWT/session, замена X-User-Name) |
| feat-003 | 📋 Planned | Langfuse (tracing, cost tracking, user feedback) |
| chore-001 | 📋 Planned | CI/CD + Deploy (GitHub Actions, auto-deploy on merge to main) |

## Быстро меняющиеся инструменты

| Инструмент | Источник |
|-----------|----------|
| Langfuse SDK v4 | скилл `langfuse` |
| structlog | firecrawl → structlog.org |
| GitHub Actions | firecrawl → docs.github.com |

## Итерации

### feat-001: Logging

**Цель:** управляемое логирование на backend и frontend. При ошибках — видеть что произошло, а не гадать. Фундамент для observability (feat-003).

**Статус:** ✅ Done
**Blocked by:** —
**Закрывает:** v1.1: logging
**Ветка:** `prod/feat-001-logging`

#### Состав работ

- [x] Backend: structlog — инициализация, конфигурация, YAML-конфиг с per-library overrides
- [x] Backend: LOG_LEVEL в Settings + .env / .env.example
- [x] Backend: request ID middleware (correlation)
- [x] Backend: замена существующих logging-вызовов на structlog
- [x] Frontend: logger-обёртка с уровнями
- [x] Frontend: Error Boundary
- [x] Frontend: замена console.error → logger.error
- [x] Docker: log rotation для app и db
- [x] Актуализация документации (backend.md, frontend.md, conventions.md)
- [x] Актуализация CLAUDE.md — секция Logging Conventions (do/don't + ссылка на conventions.md)

#### Критерии приёмки

- `make dev`: логи в human-readable формате с цветами, видны уровни и имена логгеров
- `LOG_LEVEL=debug`: видны debug-сообщения; `LOG_LEVEL=warning`: info подавлен
- Шумные библиотеки (httpx, sqlalchemy) не мусорят в INFO-режиме
- Каждый HTTP-запрос содержит request_id во всех логах
- Frontend: в dev-режиме debug/info видны в консоли браузера, в prod-сборке — только warn/error
- Frontend: ошибка рендера показывает fallback UI, а не белый экран
- `docker compose logs -f app`: логи ротируются, не растут бесконечно

#### Артефакты

- [ADR-009: Logging Strategy](../tech/adr/ADR-009-logging-strategy.md)
- [Design Brief](iterations/production/feat-001-logging/design-brief.md)
- [Implementation Plan](iterations/production/feat-001-logging/plan.md)
- [Summary](iterations/production/feat-001-logging/summary.md)

---

### feat-002: Аутентификация

**Цель:** полноценная аутентификация, замена MVP-заглушки (X-User-Name header). Безопасный доступ для нескольких пользователей.

**Статус:** 📋 Planned
**Blocked by:** prod/feat-001
**Закрывает:** v1.1: аутентификация
**Ветка:** `prod/feat-002-auth`

**Контекст:** frontend — модалка ввода username при первом визите, сохраняется в localStorage, передаётся как X-User-Name header. Backend — `get_current_user()` в deps.py извлекает header, `get_or_create` user по имени. Никакой защиты — любой может представиться кем угодно.

**Проработанные вопросы:** JWT + Refresh Token (гибрид), Argon2id (argon2-cffi), PyJWT + HS256, access в localStorage / refresh в httpOnly cookie, одноразовые refresh tokens (rotation). Детали: [ADR-011](../tech/adr/ADR-011-auth-architecture.md), [Design Brief](iterations/production/feat-002-auth/design-brief.md).

#### Состав работ

- [ ] Backend: модель User — добавить `password_hash`, миграция (drop + recreate)
- [ ] Backend: таблица `refresh_tokens`, репозиторий
- [ ] Backend: auth service (register, login, refresh, logout)
- [ ] Backend: auth router (`/api/auth/`)
- [ ] Backend: JWT encode/decode (PyJWT), переключить `get_current_user()` на JWT
- [ ] Backend: rate limiting middleware (in-memory)
- [ ] Backend: config (`JWT_SECRET`, token lifetimes)
- [ ] Frontend: Login/Register form (замена AuthGate модалки)
- [ ] Frontend: token management (axios interceptor → Bearer, refresh logic, 401 handling)
- [ ] Frontend: удаление legacy (`X-User-Name`, `learnflow-username` в localStorage)
- [ ] E2E: register → login → API-запросы → token refresh → logout

#### Критерии приёмки

- Регистрация и логин по username + password
- API-запросы аутентифицируются через JWT (`Authorization: Bearer`), `X-User-Name` убран
- Refresh token rotation работает (access обновляется прозрачно для пользователя)
- Logout инвалидирует refresh token на сервере
- Rate limiting на auth-эндпоинтах (429 при превышении)
- Все существующие роуты (projects, chats) работают без изменений через `CurrentUser`
- `make check` + `make lint-fe` проходят

#### Артефакты

- [ADR-011: Auth Architecture](../tech/adr/ADR-011-auth-architecture.md)
- [Design Brief](iterations/production/feat-002-auth/design-brief.md)

---

### feat-003: Langfuse Integration

**Цель:** observability агента (трейсы, стоимость, латенси) + structured feedback (thumbs up/down на ответы). Основной инструмент сбора обратной связи от использования.

**Статус:** 📋 Planned
**Blocked by:** prod/feat-001
**Закрывает:** v1.1: Langfuse
**Ветка:** `prod/feat-003-langfuse`

**Контекст:** Langfuse Cloud (EU), Python SDK v4. Точка интеграции: agent runner (LangGraph stream) — context manager + CallbackHandler. Подробнее: [ADR-010](../tech/adr/ADR-010-langfuse-observability.md).

#### Состав работ

- [ ] Backend: langfuse SDK v4 — зависимость, инициализация клиента, Score Config auto-init
- [ ] Backend: инструментация agent runner (root span + CallbackHandler + streaming output)
- [ ] Backend: propagate_attributes (user_id, session_id, trace_name, environment, release)
- [ ] Backend: trace_id в SSE event `done`
- [ ] Backend: feedback endpoint (`POST /api/feedback`) — create/update/delete score
- [ ] Backend: env variables (LANGFUSE_*) + .env.example + docker-compose
- [ ] Frontend: feedback UI (thumbs up/down с toggle model)
- [ ] Frontend: trace_id в state сообщения, optimistic UI, silent failure
- [ ] Верификация: token/cost tracking, корректность отображения в Langfuse UI

#### Критерии приёмки

- Каждый вызов агента порождает трейс в Langfuse с читаемым input/output
- В трейсе видны: LLM generations, tool calls, token usage, стоимость
- Трейсы сгруппированы по session_id (чаты) и user_id
- Thumbs up/down в UI чата → score привязан к трейсу в Langfuse
- Toggle: повторное нажатие удаляет оценку, смена — заменяет
- Environment (dev/production) корректно разделяет трейсы
- При недоступности Langfuse приложение работает без ошибок

#### Артефакты

- [ADR-010: Langfuse Observability Strategy](../tech/adr/ADR-010-langfuse-observability.md)
- [Design Brief](iterations/production/feat-003-langfuse/design-brief.md)
- [Reference: Feedback System](iterations/production/feat-003-langfuse/reference-feedback-system.md)

---

### chore-001: CI/CD + Deploy

**Цель:** автоматические проверки на PR (CI) + автоматический деплой при merge в main (CD). Замена ручного деплоя и локальных pre-commit hooks как единственного quality gate.

**Статус:** 📋 Planned
**Blocked by:** —
**Закрывает:** v1.1: CI/CD, автоматизация деплоя
**Ветка:** `prod/chore-001-ci-cd`

**Контекст:** нет CI/CD. Качество обеспечивается только pre-commit hooks локально. Деплой ручной — SSH на VM, git pull, docker compose build, docker compose up -d. Сервер с Nginx reverse proxy + basic auth (временная мера до feat-002).

**Проработанные вопросы:** GitHub Actions (CI + CD), SSH Action для деплоя (vs self-hosted runner, vs GHCR), сборка на сервере, main = production (auto-deploy), простой restart без zero-downtime. Детали: [ADR-012](../tech/adr/ADR-012-ci-cd-deploy.md), [Design Brief](iterations/production/chore-001-ci-cd/design-brief.md).

#### Состав работ

- [ ] CI workflow (`ci.yml`): setup Python/uv + Node/npm, make check, make lint-fe, frontend build, Docker build verification, make test
- [ ] CD workflow (`deploy.yml`): SSH Action → git pull, docker compose build, up -d, health check
- [ ] GitHub Secrets: SSH_PRIVATE_KEY, SSH_HOST, SSH_USER
- [ ] Deploy keypair на сервере
- [ ] Branch protection rules для develop и main

#### Критерии приёмки

- PR в develop/main → CI запускается, проверки проходят, результат виден в PR
- Merge в main → CD автоматически деплоит на сервер, приложение работает
- Провал CI блокирует merge (branch protection)
- Провал CD виден как ошибка в GitHub Actions
- `make check` + `make lint-fe` проходят локально и в CI идентично

#### Артефакты

- [ADR-012: CI/CD & Deploy Strategy](../tech/adr/ADR-012-ci-cd-deploy.md)
- [Design Brief](iterations/production/chore-001-ci-cd/design-brief.md)
