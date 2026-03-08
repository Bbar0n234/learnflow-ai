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
| feat-001 | 📋 Planned | Backend internal wiring (stubs → real) |
| feat-002 | 📋 Planned | Frontend → Backend connection (mocks → real) |
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

**Статус:** 📋 Planned
**Blocked by:** backend-core/feat-005, agent/feat-002
**Закрывает:** интеграция Backend Core ↔ Agent Runtime
**Ветка:** `feat/001-backend-wiring`

#### Состав работ
- [ ] ChatService → реальный AgentRunner (LangGraph stream вместо stub)
- [ ] SphereService → реальная реализация на LangGraph Store (вместо stub)
- [ ] Wiring в deps.py: инъекция реальных реализаций, настройка lifecycle (checkpointer/store init в lifespan)
- [ ] Smoke test: POST message через curl/httpie → SSE stream с реальным LLM-ответом

#### Критерии приёмки
- [ ] POST /messages возвращает SSE-поток с реальными text_chunk от LLM
- [ ] GET /sphere возвращает Knowledge Sphere из LangGraph Store
- [ ] PUT /sphere записывает данные в Store, повторный GET отражает изменения
- [ ] Диалог сохраняется: повторный запрос в тот же чат видит историю
- [ ] `make lint && make type-check` проходят

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-002: Frontend → Backend Connection

**Цель:** заменить хардкод-моки в API-модулях фронтенда реальными HTTP-вызовами к бэкенду. После итерации — фронтенд работает с живым API (REST-часть).

**Статус:** 📋 Planned
**Blocked by:** integration/feat-001, frontend/feat-006
**Закрывает:** интеграция Frontend ↔ Backend API (REST)
**Ветка:** `feat/002-frontend-backend`

#### Состав работ
- [ ] Убрать моки из shared/api/ модулей (projects.ts, chats.ts, sphere.ts, artifacts.ts), включить реальные axios-вызовы
- [ ] Проверить CORS-конфигурацию: frontend dev server успешно делает запросы к бэкенду без CORS-ошибок
- [ ] Vite dev proxy или CORS для dev-режима (frontend dev server → backend)
- [ ] Конфигурация X-User-Name (дефолтный пользователь для MVP)
- [ ] Верификация REST-потоков: projects CRUD, chats list/create, sphere GET/PUT, artifacts list/view/download

#### Критерии приёмки
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
**Blocked by:** integration/feat-002, frontend/feat-005
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
