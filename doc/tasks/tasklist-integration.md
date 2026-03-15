# Tasklist: Integration & Polish

## Контекст

Связывание всех частей в рабочий продукт: замена стабов и моков реальными реализациями, e2e-проверка полных пользовательских сценариев, Docker-запуск полного стека, финальная доводка.

**Документы:** [use-cases.md](../product/use-cases.md) (сценарии), [backend.md](../tech/backend.md) (API, SSE protocol, Service Layer), [frontend.md](../tech/frontend.md) (API-интеграция, SSE lifecycle)

**Зависимости:** Backend Core, Agent Runtime, Frontend

## Легенда

- 📋 Planned
- 🚧 In Progress
- ✅ Done
- ⏸️ Paused
- ❌ Cancelled

## Overview

| Итерация | Статус | Закрывает |
|----------|--------|-----------|
| feat-001 | ✅ Done | Backend internal wiring (stubs → real) |
| fix-001 | 📋 Planned | Contract alignment (frontend ↔ backend mismatches) |
| feat-002 | 📋 Planned | Frontend → Backend connection (mocks → real) + MVP auth UI |
| feat-003 | 📋 Planned | SSE Streaming E2E |
| feat-004 | 📋 Planned | Docker full stack |
| feat-005 | 📋 Planned | E2E scenarios + polish |

## Быстро меняющиеся инструменты

| Инструмент | Источник |
|-----------|----------|
| Docker / docker-compose | firecrawl → docs.docker.com при необходимости |
| Vite (proxy config) | firecrawl → vite.dev/config/server-options |
| FastAPI (CORS, middleware) | firecrawl → fastapi.tiangolo.com |

## Итерации

### feat-001: Backend Internal Wiring

**Цель:** заменить стабы в Service Layer реальными реализациями из Agent Runtime. После итерации — через API можно отправить сообщение и получить реальный ответ LLM со стримингом.

**Статус:** ✅ Done
**Blocked by:** backend-core/feat-005, agent/feat-002
**Закрывает:** интеграция Backend Core ↔ Agent Runtime
**Ветка:** `feat/001-backend-wiring`

> **Примечание:** с высокой вероятностью уже реализовано в ходе backend-core и agent итераций.
> `deps.py` использует `LangGraphAgentRunner` (не `StubAgentRunner`) и `LangGraphSphereService`.
> `main.py` lifespan создаёт реальный граф, checkpointer, store и agent runner.
> Требуется верификация: smoke test через curl/httpie, проверка всех критериев приёмки.
> Если всё подтверждается — итерация закрывается без кодовых изменений (только удаление мёртвого кода `StubAgentRunner`).

#### Состав работ
- [x] Верификация wiring: убедиться, что deps.py инжектит реальные реализации (не стабы)
- [x] Smoke test: POST message через curl/httpie → SSE stream с реальным LLM-ответом
- [x] Smoke test: GET/PUT sphere → данные из LangGraph Store
- [x] Smoke test: диалог сохраняется (повторный запрос видит историю)
- [x] Удаление мёртвого кода (`StubAgentRunner` в `services/agent_runner.py`) если не используется

#### Критерии приёмки
- [x] POST /messages возвращает SSE-поток с реальными text_chunk от LLM
- [x] GET /sphere возвращает Knowledge Sphere из LangGraph Store
- [x] PUT /sphere записывает данные в Store, повторный GET отражает изменения
- [x] Диалог сохраняется: повторный запрос в тот же чат видит историю
- [x] `make lint && make type-check` проходят

#### Артефакты
- [plan.md](iterations/integration/feat-001-backend-wiring/plan.md)
- [summary.md](iterations/integration/feat-001-backend-wiring/summary.md)

---

### fix-001: Contract Alignment

**Цель:** устранить обнаруженные расхождения между контрактами backend и frontend, подготовить почву для безпроблемной интеграции в feat-002/feat-003.

**Статус:** 📋 Planned
**Blocked by:** integration/feat-001
**Закрывает:** контрактные несоответствия, обнаруженные при аудите
**Ветка:** `fix/001-contract-alignment`

> **Контекст:** проблемы обнаружены при pre-integration аудите. Все три задокументированы как known limitations в post-implementation summaries соответствующих итераций. Конкретные решения принимаются при планировании итерации — здесь зафиксированы проблемы и возможные направления.

#### Проблема 1: Transient ArtifactCard

Артефакт-карточки в чате видны только во время SSE-стрима. После `endStream()` stream store сбрасывается, карточка исчезает. Финальное сообщение (из query invalidation) — `{id, role, content, created_at}` без привязки к артефактам.

**Источник:** `frontend/feat-005-sse-streaming/summary.md` — обсуждены варианты A–D, выбран D (known limitation).

**Возможные направления:**
- A: Добавить `artifacts[]` в Message response (backend изменение, связка message ↔ artifact)
- B: Добавить `message_id` в Artifact модель (backend изменение + миграция)
- C: Не сбрасывать `streamingArtifacts` в `endStream()`, хранить артефакты по chat_id
- D: Оставить как есть (артефакты доступны в tab Artifacts, в чате — только во время стрима)

#### Проблема 2: Nullable mismatches в типах

**`Message.created_at`**: backend `MessageOut.created_at: datetime | None` (LangGraph checkpointer не хранит timestamps), frontend `Message.created_at: string` (required).

**`ArtifactDetail.thread_id`**: backend `ArtifactDetailResponse.thread_id: uuid.UUID | None` (nullable by design — `SET NULL` on thread delete), frontend `ArtifactDetail.thread_id: string` (required).

**Источники:** `backend-core/feat-002/plan.md`, `frontend/feat-002/plan.md`.

**Возможные направления:**
- Привести frontend-типы в соответствие с backend (добавить `| null`)
- Или обеспечить значения на backend-стороне (fallback для created_at и т.д.)

#### Проблема 3: Лишние create-response типы

Frontend определяет `ProjectCreateResponse` и `ChatCreateResponse` (без `updated_at`), но backend возвращает полный `ProjectResponse`/`ChatResponse` (с `updated_at`). Технически не ломает (TS игнорирует лишние поля), но создаёт лишние типы и расхождение с контрактом.

#### Состав работ
- [ ] Принять решение по каждой из трёх проблем (при планировании итерации)
- [ ] Реализовать выбранные решения
- [ ] `make lint && make lint-fe && make type-check` проходят

#### Критерии приёмки
- [ ] Frontend типы соответствуют backend schemas (nullable поля согласованы)
- [ ] Определено и реализовано решение по ArtifactCard visibility
- [ ] Нет лишних/дублирующих типов в frontend
- [ ] Если были backend-изменения — миграция + smoke test

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-002: Frontend → Backend Connection

**Цель:** заменить хардкод-моки в API-модулях фронтенда реальными HTTP-вызовами к бэкенду. Добавить MVP-авторизацию (ввод username). После итерации — фронтенд работает с живым API (REST-часть).

**Статус:** 📋 Planned
**Blocked by:** integration/fix-001, frontend/feat-006
**Закрывает:** интеграция Frontend ↔ Backend API (REST), MVP auth UI
**Ветка:** `feat/002-frontend-backend`

#### Состав работ
- [ ] Убрать моки из shared/api/ модулей (projects.ts, chats.ts, sphere.ts, artifacts.ts), включить реальные axios-вызовы
- [ ] Проверить CORS-конфигурацию: frontend dev server успешно делает запросы к бэкенду без CORS-ошибок
- [ ] Vite dev proxy или CORS для dev-режима (frontend dev server → backend)
- [ ] MVP auth UI: простой ввод username (модалка/prompt при первом визите, сохранение в localStorage, передача в `X-User-Name` header). Backend уже поддерживает: `get_current_user()` в deps.py извлекает header, `get_or_create` user
- [ ] Верификация REST-потоков: projects CRUD, chats list/create, sphere GET/PUT, artifacts list/view/download

#### Критерии приёмки
- [ ] Пользователь может ввести имя при первом визите, имя сохраняется между сессиями
- [ ] Фронтенд создаёт проект → проект появляется в sidebar (данные из реального API)
- [ ] Список чатов, sphere, artifacts загружаются с бэкенда
- [ ] CRUD-операции с проектами работают через UI
- [ ] Sphere: просмотр и редактирование через UI → данные персистятся на бэкенде
- [ ] Нет hardcoded mock-данных в API-модулях
- [ ] `make lint-fe` и TypeScript проходят без ошибок

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-003: SSE Streaming E2E

**Цель:** сквозной стриминг от пользовательского ввода до инкрементального рендеринга в UI. Самая критичная точка интеграции — все 6 event types, cancel, error handling.

**Статус:** 📋 Planned
**Blocked by:** integration/feat-002
**Закрывает:** SSE end-to-end (frontend SSE client ↔ backend SSE endpoint ↔ LangGraph stream)
**Ветка:** `feat/003-sse-e2e`

#### Состав работ
- [ ] useAgentStream подключён к реальному SSE endpoint бэкенда
- [ ] Верификация всех event types: text_chunk (инкрементальный рендеринг), tool_start/tool_end (индикаторы), artifact_created (карточка + инвалидация), done (инвалидация chat query + recents), error (UI feedback)
- [ ] Cancel E2E: кнопка Cancel → POST /cancel → сервер отправляет error event → стрим закрывается → UI в idle
- [ ] TanStack Query инвалидация после done и artifact_created (полное сообщение с сервера)
- [ ] Error handling: ошибки LLM, сетевые разрывы, таймауты — graceful degradation в UI

#### Критерии приёмки
- [ ] Отправка сообщения → текст появляется инкрементально (чанк за чанком)
- [ ] При вызове tool агентом — индикатор появляется и исчезает корректно
- [ ] При создании артефакта — карточка в чате, список артефактов обновляется
- [ ] Cancel прерывает генерацию, UI возвращается в idle без ошибок
- [ ] После done — chat query инвалидируется, полное сообщение загружается с сервера
- [ ] Сетевой разрыв во время стриминга — пользователь видит сообщение об ошибке, UI не зависает

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-004: Docker Full Stack

**Цель:** полный стек в docker-compose. `make docker-up` → рабочее приложение в браузере.

**Статус:** 📋 Planned
**Blocked by:** integration/feat-003
**Закрывает:** контейнеризация всех сервисов, production-ready запуск
**Ветка:** `feat/004-docker-stack`

#### Состав работ
- [ ] Backend Dockerfile (production: uvicorn, multi-stage build)
- [ ] Frontend: build + static serving (конкретный подход — при реализации, без nginx)
- [ ] docker-compose.yml: backend + frontend + PostgreSQL (volumes, networks, depends_on)
- [ ] Environment configuration для Docker-режима (.env)
- [ ] Health checks (backend readiness: DB connection)
- [ ] Makefile: `docker-up`, `docker-down`, `docker-build` — полный стек

#### Критерии приёмки
- [ ] `make docker-build && make docker-up` → все сервисы поднимаются без ошибок
- [ ] Приложение доступно в браузере, можно создать проект и отправить сообщение
- [ ] Данные персистятся между перезапусками (PostgreSQL volume)
- [ ] `make docker-down` корректно останавливает всё
- [ ] Новый разработчик может запустить проект по README (clone → env → docker-up)

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-005: E2E Scenarios + Polish

**Цель:** прогон реальных пользовательских сценариев из use-cases.md, обнаружение и фикс интеграционных проблем. После итерации — MVP "не стыдно показать".

**Статус:** 📋 Planned
**Blocked by:** integration/feat-004
**Закрывает:** MVP readiness, use-cases UC-1/UC-2/UC-3
**Ветка:** `feat/005-e2e-polish`

#### Состав работ
- [ ] UC-1: структурирование доклада — полный флоу (создать проект → описать тему → агент использует skill "structure" → итеративная доработка → артефакт)
- [ ] UC-2: research по теме — полный флоу (запрос на исследование → агент использует MCP tools для web search → структурированный результат со ссылками)
- [ ] UC-3: Knowledge Sphere — персистентность контекста (работа в проекте → закрыть → вернуться → агент помнит контекст)
- [ ] Фикс обнаруженных интеграционных проблем
- [ ] Polish: loading states, error states, empty states, edge cases (длинные ответы, конкурентные запросы)

#### Критерии приёмки
- [ ] Все три use-case проходят от начала до конца без критичных ошибок
- [ ] Knowledge Sphere обновляется агентом по ходу работы и сохраняется между сессиями
- [ ] Артефакты создаются и доступны для просмотра/скачивания
- [ ] UI не зависает, ошибки отображаются понятно для пользователя
- [ ] Приложение соответствует критерию MVP из vision.md: "не стыдно показать"

#### Артефакты
<!-- Заполняется по мере работы -->
