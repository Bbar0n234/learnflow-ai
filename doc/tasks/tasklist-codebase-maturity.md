# Tasklist: Codebase Maturity Pass

## Контекст

Плановая фаза «взросления» кодовой базы. Цель — единые паттерны, конвенции и тесты во всех слоях (backend / agent runtime / frontend) через slice-ревью каждого домена в паре с релевантным skill'ом.

Конвенции формируются *по ходу* на реальных примерах (continuous improvement), а не предписываются заранее. Каждый slice — отдельная сессия с отдельным агентом; tasklist служит навигатором, агент получает ссылку на свой пункт и работает в гибком интерактивном формате.

**Источник:** [backlog.md](../backlog.md) — зонтичный пункт «Codebase-wide patterns & conventions pass» (Tech Debt & Competency).
**Зависимости:** Post-MVP (`tasklist-post-mvp.md`) — фаза не блокируется незакрытыми элементами post-mvp, выполняется параллельно по решению архитектора.

## Легенда

- 📋 Planned
- 🚧 In Progress
- ✅ Done
- ⏸️ Paused
- ❌ Cancelled

## Принципы работы по фазе

- **Slice-формат.** Каждая итерация — отдельный домен (REST, DB, FastAPI, Agent runtime, Frontend). Отдельная сессия, отдельный агент, отдельная feature-ветка.
- **Skill first, code second.** Скиллы отобраны и разобраны с архитектором в feat-001 (см. [skill-map.md](../tech/skill-map.md)) — внутри slice'а skill не пересказывается как теория, а применяется: агент читает его сам и показывает, как принципы выливаются на конкретном коде репозитория. Отложенные кандидаты из skill-map ставятся при заходе в соответствующий slice.
- **Ревью шире скилла.** Аудит не ограничивается чек-листом скилла: общие паттерны чистого кода, читаемость, очевидные некорректности — тоже в скоупе slice'а.
- **Точки остановки на теорию.** На любом шаге slice'а можно (и нужно) остановиться, чтобы архитектор разобрался в теории. Это не отвлечение от задачи — это часть задачи. Мини-подпункты «здесь стоит разобраться в теории» явно отмечены в DoD каждой итерации.
- **Интерактивный формат + согласование на ключевых шагах.** Первичный аудит и изучение кода агент ведёт автономно; findings приносит архитектору на разбор. Перед написанием тест-кейсов и перед рефакторингом аутлайн согласуется с архитектором — правки только после апрува. Развилки решает архитектор.
- **Конвенции — continuous, без дублирования скиллов.** Каждый slice добавляет в `doc/tech/conventions.md` по факту найденного, но содержимое скиллов туда не копируется: фиксируются только проектные решения — выбранные развилки, отступления от skill-дефолтов, специфика репозитория. Финализирующий pass (feat-007) не первая запись, а сборка/уточнение накопленного.
- **Тесты — естественное завершение.** Понимаем код → понимаем, что и как тестировать. Системная тестовая философия и инфраструктура — feat-009.
- **Рефакторинг со страховкой.** Ручные тест-кейсы — норма slice'а: перед правками составляется список кейсов на затронутые участки, после правок — прогон (руками, curl'ом, через UI). Точечные автотесты до feat-009 допустимы, когда правка трогает критичный путь (auth, security guard, SIEM pipeline); позже они вливаются в общую рамку feat-009.

## Overview

| Итерация | Статус | Scope | Закрывает |
|----------|--------|-------|-----------|
| feat-001 | ✅ Done | foundation | Skill Discovery + Layers & Abstractions Diagram |
| feat-002 | ✅ Done | backend / REST | REST API slice: api-design-principles skill + поглощение REST API cleanup (8 пунктов аудита 2026-04-04) |
| feat-003 | ✅ Done | db | DB slice: postgresql skill, индексы, constraints, типы, паттерны миграций |
| feat-004 | ✅ Done | backend / fastapi | Backend/FastAPI slice: fastapi skill + поглощение точечных техдолгов (SIEM MetaEmitter, дубль SecurityEvent, CORS_ORIGINS, SIEM follow-ups) |
| feat-005 | ✅ Done | agent | Agent runtime slice: langgraph-patterns (авторский) + кандидаты langgraph-* от langchain-ai + поглощение Reasoning ChatOpenAI everywhere (langchain-architecture отклонён в feat-001) |
| feat-006 | ✅ Done | frontend | Frontend slice: `feature-sliced-design` skill + миграция на канон FSD (pages/features), фабрика query keys, ось состояния в conventions |
| feat-007 | ✅ Done | cross-cutting | Кросс-резрезные конвенции: error return types + error handling philosophy (graceful degradation vs fail-fast) |
| feat-008 | ✅ Done | enforcement | Arch-checker (детерминированные проверки) + 2 ревьюера A/B + harvest-механизм + дробление конвенций |
| feat-009 | 📋 Planned | testing | Test philosophy + test engineering + покрытие критичных участков |

## Параллелизация

```
feat-001 (foundation) ── обязательное предусловие для slice-аудитов
            │
            ├── feat-002 (REST) ─────┐
            ├── feat-003 (DB) ────────┤
            ├── feat-004 (FastAPI) ───┼── slice-аудиты независимы по коду,
            ├── feat-005 (Agent) ─────┤   но порождают зависимый поток
            └── feat-006 (Frontend) ──┘   обновлений conventions.md
                                            │
                                            ▼
                            feat-007 (cross-cutting conventions)
                                            │
                                            ▼
                            feat-008 (enforcement: arch-checker + reviewer)
                                            │
                                            ▼
                            feat-009 (тесты)
```

- **feat-001** — sequential, выполняется первым.
- **feat-002 — feat-006** — независимы по коду, могут идти параллельно (разные агенты в worktree) или последовательно. Default рекомендация: последовательно в порядке REST → DB → FastAPI → Agent → Frontend (REST первым, потому что у него самый ясный исходный материал — существующий аудит). Архитектор решает по ситуации.
- **feat-007** — после всех slice'ов: финализирует то, что накопилось.
- **feat-008** — после feat-007: enforcement пишется на уже сформированные конвенции, иначе arch-checker и reviewer-промпты будут проверять ещё не существующие правила.
- **feat-009** — завершающий шаг.

## Итерации

### feat-001: Foundation — Skill Discovery & Layers Diagram

**Цель:** подготовить каркас для slice-аудитов: подобрать релевантные skill'ы и зафиксировать карту слоёв.

**Статус:** ✅ Done — итоги в [summary.md](iterations/codebase-maturity/feat-001-foundation/summary.md)
**Scope:** foundation
**Зависимости:** —

#### Из backlog

- **P2** Layers & abstractions diagram (часть пункта из Documentation Quality & Architecture, переносится сюда как обслуживающий артефакт фазы — не самостоятельная цель документации, а навигационная карта).

#### Скоуп работы

- **Skill discovery.** Web search по доменам кодовой базы: REST API design, PostgreSQL, FastAPI, LangChain/LangGraph, frontend (React/TypeScript), тестирование. Для каждого домена — список найденных skill'ов, беглое ознакомление, отметка «берём / не берём / нужно изучить глубже».
- **Layers & abstractions diagram.** Mermaid-диаграмма слоёв и направлений зависимостей:
  - backend: handlers / services / repositories
  - agent runtime: graph nodes / tools / skills / context
  - frontend: features / shared / entities
  - cross-service границы (main app ↔ siem-service ↔ shared packages)
- Точное место в `doc/` — определить при реализации (вероятно отдельный документ в `doc/tech/`).

#### Точки остановки на теорию

- При неуверенности — разобрать каждую найденную skill'у вместе с автором, понять что она покрывает, где границы применимости.
- Архитектура слоёв: если для какого-то компонента слой неочевиден (например, граница между `services/` и `pipeline/` внутри сервиса) — остановиться, разобрать, зафиксировать решение.

#### Definition of Done

- [x] Skill discovery проведён: установленные скиллы + внешняя охота по каталогам, решения по каждому домену зафиксированы (артефакт итерации: `skill-discovery-draft.md`, заморожен).
- [x] `doc/tech/skill-map.md` создан — постоянная карта скиллов: принципы, роли, отклонённые, пробелы, отложенные кандидаты.
- [x] Таблица скиллов в `CLAUDE.md` дополнена принятыми скиллами + ссылка на skill-map.
- [x] Принятые скиллы лежат в `.claude/skills/` репозитория.
- [x] Layers & abstractions diagrams — по согласованному принципу «карта сервисов в `vision.md`, слои сервиса в документе сервиса»: `vision.md` (общесистемная, добавлен SIEM-контур), `backend.md` (детальная послойная + сквозной chat-поток + карта persistence), `frontend.md` (послойная + поток данных по осям состояния), `doc/tech/siem-service.md` (новый полный документ: топология, послойная с границей сервиса, event pipeline, lifecycle алерта; секция в backend.md сжата до ссылки). Стиль: Mermaid, слои — полупрозрачные цветные подложки (subgraph с alpha-заливкой и цветным stroke/заголовком), рендер каждой проверен на тёмной теме (запрет светлых сплошных заливок остаётся).
- [x] Диаграммы ссылаются на конкретные директории/модули кодовой базы (не абстрактные «слой A → слой B»).
- [x] В `doc/index.md` добавлены ссылки на `siem-service.md` и `skill-map.md`.

---

### feat-002: REST API Slice

**Цель:** привести REST API к best practices через `api-design-principles` skill, закрыть существующий аудит 2026-04-04.

**Статус:** ✅ Done — итоги в [summary.md](iterations/codebase-maturity/feat-002-rest-api/summary.md)
**Scope:** backend / REST
**Зависимости:** feat-001

#### Из backlog

- **P2** REST API cleanup — аудит от 2026-04-04: pagination на коллекциях (projects, chats, artifacts), POST create возвращает 200 вместо 201, DELETE feedback через POST с score=None, нет стандартного envelope для list responses ({items, total, limit, offset}). Полный список — 8 пунктов *(перенесено из Backend)*.
- **P2** REST API audit + refactor via api-design-principles skill *(перенесено из Tech Debt & Competency)*.

#### Скоуп работы

- Изучение skill `api-design-principles` — принципы, паттерны, антипаттерны.
- Проход по всем REST endpoints проекта (main app + siem-service): аудит против skill + материала из бэклога.
- Точечные правки кода: pagination, status codes, envelope для list, DELETE endpoints, error response format.
- Обновление `doc/tech/conventions.md` — раздел про REST-конвенции (паттерны pagination, status code policy, envelope shape, error response).

#### Точки остановки на теорию

- REST principles (resources vs actions, HATEOAS уровень, idempotency).
- Pagination patterns: offset/limit vs cursor — что подходит нашим коллекциям.
- Error response shape: RFC 7807 (Problem Details) vs custom envelope.
- API versioning policy (нужна сейчас или нет).

#### Definition of Done

- [x] Skill `api-design-principles` применён к коду проекта: аудит endpoints против его принципов, findings на конкретных примерах (включая 4 ownership/authz-дыры сверх бэклога).
- [x] Все 8 пунктов аудита 2026-04-04 либо закрыты, либо явно отложены с обоснованием (полный список из 8 не был сохранён; 4 зафиксированных закрыты, остальное перекрыто повторным аудитом — см. summary).
- [x] Status codes везде корректны (201 на POST create, 204 на DELETE без body, 409 на конфликт лимита; auth-endpoints — RPC-исключение по решению архитектора).
- [x] List responses везде имеют единый envelope с pagination metadata (`Page[T]`: items/total/limit/offset, оба сервиса).
- [x] REST-конвенции добавлены в `doc/tech/conventions.md` (§ REST API).
- [x] Тест-кейсы на затронутые endpoints составлены до правок и прогнаны после — 57 pass / 1 fail (environmental, PDF) / 2 deferred 👤 ([test-cases.md](iterations/codebase-maturity/feat-002-rest-api/test-cases.md)).
- [x] Точки остановки на теорию пройдены: pagination offset/limit vs cursor, RFC 9457 vs custom envelope, versioning policy — решения зафиксированы в conventions.md.

---

### feat-003: DB Slice

**Цель:** аудит схемы БД и query-паттернов через `postgresql` skill, формирование DB-конвенций.

**Статус:** ✅ Done — итоги в [summary.md](iterations/codebase-maturity/feat-003-db/summary.md)
**Scope:** db
**Зависимости:** feat-001

#### Из backlog

- **P2** DB architecture audit via postgresql skill *(перенесено из Tech Debt & Competency)*.

#### Скоуп работы

- Изучение skill `postgresql` — best practices по схеме, индексам, constraints, типам.
- Аудит схемы main app + siem-service: типы колонок, индексы (есть ли по тем колонкам, по которым реально фильтруем; есть ли лишние), constraints (FK, CHECK, UNIQUE), nullable где не надо.
- Аудит query-паттернов: N+1, отсутствующие `joinedload`/`selectinload`, ручные SQL, миграции.
- Точечные миграции при необходимости (через autogenerate, не руками).
- Обновление `doc/tech/conventions.md` — DB-конвенции (типы, индексы, constraints, миграции).

#### Точки остановки на теорию

- Индексы: B-tree vs GIN vs partial vs expression — когда что.
- Query plans (`EXPLAIN ANALYZE`) — как читать, когда смотреть.
- SQLAlchemy 2.x паттерны: async session, eager loading, relationship configuration.
- Migration safety: что autogenerate не покрывает, как делать data migrations.

#### Definition of Done

- [x] Skill `postgresql` применён к коду проекта: аудит схемы и запросов против его принципов, findings на конкретных примерах.
- [x] Аудит схемы и query-паттернов проведён, findings зафиксированы.
- [x] Критичные индексы добавлены (если выявлены пропуски).
- [x] DB-конвенции добавлены в `doc/tech/conventions.md`.
- [x] Тест-кейсы на затронутые участки составлены и прогнаны (миграции применяются и откатываются, затронутые запросы возвращают прежние результаты).
- [x] Точки остановки на теорию пройдены.

---

### feat-004: Backend / FastAPI Slice + SIEM Hygiene

**Цель:** аудит backend-инфраструктуры через `fastapi` skill, закрытие точечных техдолгов в SIEM и конфиге.

**Статус:** ✅ Done — итоги в [summary.md](iterations/codebase-maturity/feat-004-fastapi/summary.md)
**Scope:** backend / fastapi
**Зависимости:** feat-001

#### Из backlog

- **P2** SIEM `MetaEmitter` — устранить module-level singleton (`services/siem-service/siem_service/pipeline/meta_emitter.py:86,89`) *(перенесено из Tech Debt & Competency)*.
- **P2** SIEM meta-emitter — выпилить дубль `SecurityEvent` (`meta_emitter.py:25-33`) *(перенесено из Tech Debt & Competency)*.
- **P3** SIEM follow-ups из feat-005 hygiene pass: UP042 StrEnum-миграция для `backend/app/agent/security/types.py`; bump pin uv в Dockerfile'ах с 0.10.2 до текущего; `line-length` 88 → 100 в `ruff.toml`; пересоздание hand-written DDL миграций (`add_is_admin_to_users.py`, `001_initial_siem_events.py`, `002_alerts_and_rules.py`) через autogenerate *(перенесено из Tech Debt & Competency)*.
- **P2** `CORS_ORIGINS` парсится из env как JSON, ломается в shell-source (`backend/app/config.py:46-61`) *(перенесено из Tech Debt & Competency)*.

#### Скоуп работы

- Изучение skill `fastapi` — современные паттерны (lifespan, dependency providers, app.state, BaseSettings, async, тестирование).
- Аудит backend infra: lifespan-инициализация, app.state, DI, конфиг (Settings + .env), middleware, error handlers.
- Закрытие точечных техдолгов из списка выше.
- Обновление `doc/tech/conventions.md` — FastAPI-специфичные конвенции (что лежит в lifespan, что в Depends, что в app.state).

#### Точки остановки на теорию

- FastAPI lifespan vs middleware vs Depends — когда что использовать.
- Pydantic Settings: `Annotated[..., NoDecode]`, поведение complex types из env, способы парсинга CSV-списков.
- Async paradigms: что блокирует event loop, где `run_in_executor` обязателен.
- Pydantic v2 migration: что изменилось, что мы используем, где можно подтянуть.

#### Definition of Done

- [x] Skill `fastapi` применён к коду проекта: аудит infra-слоя против его принципов, findings на конкретных примерах.
- [x] SIEM `MetaEmitter` singleton устранён (state в app.state, инициализация в lifespan, route'ы через Depends).
- [x] Дубль `SecurityEvent` в siem-service удалён, импорт из `siem_contracts.events`.
- [x] `CORS_ORIGINS` парсится надёжно (CSV или `NoDecode`).
- [x] SIEM follow-ups закрыты частично по решению архитектора: UP042 ✅ (аудит `str()`-семантики чистый), uv pin ✅ (0.10.2 → 0.11.21); line-length 100 — отклонено, остаёмся на 88 (пункт в backlog: bump = project-wide reformat, конфликты с параллельными slice'ами); пересоздание DDL-миграций — отклонено («пусть как есть», переписывание истории миграций не оправдано).
- [x] FastAPI-конвенции добавлены в `doc/tech/conventions.md`.
- [x] Тест-кейсы на затронутые участки составлены и прогнаны (33 кейса, независимый агент-тестировщик на docker-стенде; 30 PASS / 3 SKIP без LLM-ключей; + пост-merge прогон 14/14). Точечные автотесты (17 шт.) написаны и отработали (поймали circular import), но по решению архитектора перенесены из `backend/tests/` в архив итерации — живую тестовую инфраструктуру проектирует feat-009.
- [x] Точки остановки на теорию пройдены (app.state vs module-level singletons, CSV vs NoDecode, anyio.to_thread vs def-handlers vs asyncer, StrEnum `str()`-семантика).

---

### feat-005: Agent Runtime Slice

**Цель:** аудит agent runtime через `langgraph-patterns` skill (+ официальные кандидаты `langgraph-*` от langchain-ai — подтверждение при заходе), миграция на единые паттерны. `langchain-architecture` отклонён в feat-001 (LangChain-обёртки при raw LangGraph), см. `doc/tech/skill-map.md`.

**Статус:** ✅ Done — итоги в [summary.md](iterations/codebase-maturity/feat-005-agent-runtime/summary.md)
**Scope:** agent
**Зависимости:** feat-001

#### Из backlog

- **P2** LangGraph / LangChain audit via agent-скиллы (изначально langchain-architecture — отклонён в feat-001, заменён на `langgraph-patterns` + кандидаты от langchain-ai) *(перенесено из Tech Debt & Competency)*.
- **P2** Reasoning ChatOpenAI everywhere — convention + migration. Все модели проекта используют `ReasoningChatOpenAI`, не plain `ChatOpenAI`. Добить summarizer, guard на `ReasoningChatOpenAI`; зафиксировать convention в `conventions.md` *(перенесено из Agent)*.
- **P3** `langfuse_enabled` module-level флаг (`backend/app/infra/langfuse.py`) — поднимается через `global` в `init_langfuse()`, читается lazy-импортами в `agent/runner.py` и `agent/security/observer.py` (вне request scope). Единственное намеренное отступление от правила «никаких module-level синглтонов» (conventions.md § FastAPI). Владение флагом перевести в агентную инструментацию (closure/DI) *(перенесено из Tech Debt & Competency)*.

#### Скоуп работы

- Скилл `langgraph-patterns` (raw LangGraph: StateGraph, Command, HITL, streaming, checkpointing) + подтверждение кандидатов `langgraph-*` (langchain-ai/langchain-skills) — сверить на дубль с авторским.
- Аудит agent runtime: ноды графа, tools, skills layer, context engineering, checkpointer, streaming protocol.
- Миграция summarizer и guard на `ReasoningChatOpenAI`.
- Обновление `doc/tech/conventions.md` — LangGraph-конвенции + reasoning convention.

#### Точки остановки на теорию

- LangGraph state patterns: что хранить в state, что в context, что в Store.
- Command API vs обычный return из ноды.
- Streaming events: какие типы, как обрабатывать, как тестировать.
- LangGraph Store: unified memory backend, namespace strategies (стыкуется с отдельным P2 «LangGraph Store deep-dive», который остаётся в бэклоге как самостоятельное research-погружение).
- Reasoning LLMs: что попадает в `additional_kwargs.reasoning`, как видится в Langfuse, цена reasoning токенов.

#### Definition of Done

- [x] Skill `langgraph-patterns` применён к коду проекта: аудит runtime против его паттернов, findings на конкретных примерах (подтверждения: pre-defined edges для ReAct, shared checkpointer/store через `async with`, multi-mode streaming).
- [x] Summarizer и guard на `ReasoningChatOpenAI` — все модели создаются как `ReasoningChatOpenAI` безусловно (единый билдер `_build_chat_model`).
- [x] Reasoning convention зафиксирован в `conventions.md § Reasoning LLMs` («все модели проекта создаются как ReasoningChatOpenAI — безусловно»).
- [x] LangGraph-конвенции добавлены в `conventions.md § Agent Runtime` (топология графа, runner-оркестратор + коллаборáторы).
- [x] Тест-кейсы составлены; точечные автотесты прогнаны (46 PASS, критичный путь guard покрыт, независимо отревьюены, заархивированы). Ручной smoke агентного потока отложен — стенд занят параллельным slice'ом feat-006 + нет LLM-ключей (см. summary).
- [x] Точки остановки на теорию пройдены (langfuse `tracing_enabled`/no-op vs наш auth-флаг; Command API vs pre-defined edges; reasoning-надкласс).
- [x] Доп. findings закрыты: `langfuse_enabled` module-global → DI; runner расщеплён (separation of concerns); `ModelConfigResolver.default()`; user_memory `RuntimeError`; удалён мёртвый код; пойман и пофикшен циклический импорт llm↔agent.

---

### feat-006: Frontend Slice

**Цель:** аудит фронтенд-кода, формирование frontend-конвенций.

**Статус:** ✅ Done — итоги в [summary.md](iterations/codebase-maturity/feat-006-frontend/summary.md)
**Scope:** frontend
**Зависимости:** feat-001

#### Из backlog

- *(нет точечных пунктов из бэклога — slice заведён как часть phase scope)*

#### Скоуп работы

- **Sub-skill discovery для frontend.** В feat-001 уже должен быть результат. Если skill для React/TypeScript архитектуры найден — используем. Если нет — ручной slice по принципам, известным архитектору.
- Аудит структуры: features / shared / entities, состояние (Redux/Zustand/local), типизация, API integration (TanStack Query, RTK), стили (Tailwind/CSS modules), компонентная композиция.
- Конвенции по логированию через `@/shared/lib/logger` (уже есть в проекте, проверить применение).
- Обновление `doc/tech/conventions.md` или отдельного раздела — frontend-конвенции.

#### Точки остановки на теорию

- React patterns: composition vs inheritance, suspense, error boundaries.
- TypeScript: strict mode coverage, generic patterns, discriminated unions.
- State management: где локальное, где глобальное, где server state.
- ESLint + Prettier rule strategy.

#### Definition of Done

- [x] Frontend-skill — `feature-sliced-design` (принят в feat-001), применён к коду; ось состояния закрыта конвенцией (ядро отклонённого `react-state-management`).
- [x] Аудит структуры проведён, findings зафиксированы и разобраны с архитектором (FSD-отступления, ось состояния, чистый код, дрейф доки).
- [x] Точечные правки применены: миграция на канон FSD (`pages/`/`features/`), консолидация `shared/api` (дробление типов, data-хуки, фабрика query keys), публичные API слайсов, B3-селекторы, C4 MarkdownRenderer→`shared/ui`, C1 удалён мёртвый `__init__.ts`.
- [x] Frontend-конвенции добавлены в `conventions.md` (§ Frontend); дрейф `frontend.md` исправлен (Module Structure + таблица query keys).
- [x] Тест-кейсы составлены до правок, прошли ревью полноты, прогнаны независимым тестировщиком на стенде в два захода (без LLM + на реальном ключе) — поведение-сохраняющий, регрессий нет ([test-cases.md](iterations/codebase-maturity/feat-006-frontend/test-cases.md)).
- [x] Точки остановки на теорию пройдены (pages vs features-as-sections, публичные API, ось состояния Zustand/TanStack Query, optimistic vs пессимистик).

---

### feat-007: Cross-Cutting Conventions (Error Handling)

**Цель:** формализовать кросс-резрезные конвенции, которые не привязаны к одному slice'у.

**Статус:** ✅ Done — итоги в [summary.md](iterations/codebase-maturity/feat-007-cross-cutting/summary.md)
**Scope:** cross-cutting
**Зависимости:** feat-002, feat-003, feat-004, feat-005, feat-006 (нужны накопленные примеры)

#### Из backlog

- **P2** Error return types conventions — exceptions / Result-Either / Optional + None, границы применимости *(перенесено из Agent Harness & Workflow)*.
- **P3** 5xx-ответы не в RFC 9457 — необработанные исключения проходят мимо problem-handlers через Starlette `ServerErrorMiddleware` и отдаются как `text/plain "Internal Server Error"` (4xx уже problem+json). Распространить единый формат на 500: generic `Exception`-handler → минимальный problem+json без internal details (`{type: about:blank, title, status: 500}`) + обязательное логирование `exc_info`. Форма ответа решается здесь вместе с философией обработки (где ловить, graceful degradation vs fail-fast) *(перенесено из Backend, finding feat-002)*.

#### Скоуп работы

- **Error return types.** На реальных примерах из кодовой базы (накопленных в slice-итерациях) сформулировать границы:
  - exceptions — для неожидаемых ошибок и границ системы;
  - Result/Either — для ожидаемых бизнес-ошибок (если решим так);
  - Optional — для отсутствия значения без ошибки.
- **Error handling philosophy.** Где graceful degradation, где fail-fast: какие сервисы и слои деградируют (LLM провайдер недоступен → fallback), какие падают (БД недоступна → 503). На каком уровне принимается решение (handler / service / infra).
  - *Конкретный пример из feat-005 (решить здесь):* агентные tools при отсутствии инфраструктуры (`runtime.store is None`) — fail-fast или graceful? Сейчас и KS, и user_memory **бросают `RuntimeError`** (выровнено в feat-005); из-за дефолтного `_default_handle_tool_errors` в `ToolNode` (глотает только `ToolInvocationError`) такое исключение пробрасывается из графа → SSE `error`, ход рвётся. Альтернатива — обе тулзы возвращают error-строку (status=success, агент продолжает). Это защитный путь (`store` в проде всегда есть), но направление políticy нужно зафиксировать.
- Что ещё всплыло по ходу slice'ов и достойно кросс-резрезной фиксации — записать.
- Обновление `doc/tech/conventions.md` — раздел про error handling (пишется в лаконичном стиле, обоснование «почему» сжато; систематический анти-раздувочный проход по всему документу — feat-008).

#### Точки остановки на теорию

- Result/Either в Python: returns library, проектные обёртки, плюсы/минусы vs exceptions.
- Graceful degradation vs circuit breaker — границы понятий.
- Где в FastAPI ловить и куда отдавать ошибки: middleware vs exception handler vs Depends.

#### Definition of Done

- [x] Error return types conventions зафиксированы в `conventions.md` (§ «Сигнал: исключения + Optional», § «Модель ошибок»).
- [x] Error handling philosophy зафиксирована в `conventions.md` (§ «Восстановление: fail-fast / graceful / fail-safe», § «Барьерный стек», § «Агентные tools», § «SIEM event pipeline», § «Frontend»).
- [x] Конвенции иллюстрированы примерами из реального кода проекта (ссылки на реальные файлы, карта «источник → статус», callable-обработчик `ToolNode`).
- [x] Точки остановки на теорию пройдены (Result/Either анализ — D-ERR-4; graceful degradation vs circuit breaker — D-ERR-6; fail-safe vs fail-secure для guard — D-ERR-6; барьер vs middleware vs exception handler — D-ERR-2).

Артефакты итерации: [decisions.md](iterations/codebase-maturity/feat-007-cross-cutting/decisions.md) · [summary.md](iterations/codebase-maturity/feat-007-cross-cutting/summary.md) · [test-cases.md](iterations/codebase-maturity/feat-007-cross-cutting/test-cases.md)

---

### feat-008: Enforcement — Arch-Checker + Reviewer Prompts

**Цель:** автоматизировать многоуровневое ревью изменений — детерминированные арх-проверки + LLM-reviewer по чек-листам (проектные конвенции + фундаментальное качество кода + соответствие документации) — и привести сам `conventions.md` в поддерживаемую форму (анти-раздувание). Предварительный шаг — deep research по состоянию инструментов code review.

**Статус:** ✅ Done — итоги в [summary.md](iterations/codebase-maturity/feat-008-enforcement/summary.md); проработка в [design-brief.md](iterations/codebase-maturity/feat-008-enforcement/design-brief.md)
**Scope:** enforcement (workflow / CI)
**Зависимости:** feat-007 (нужны зафиксированные конвенции для enforcement'а)

> **Скоуп расширился по ходу проработки с архитектором** (зафиксировано в design-brief): итерация выросла из «enforcement кода» в «надёжность петель обратной связи». Добавлены: harvest-механизм (систематический сбор хвостов → backlog/конвенции), норма ре-верификации, формат тест-кейсов (run-log) + шаблон, два ревьюера (A/B по когнитивным режимам, не один). Граница: tester-review и полная активация детерминированной ре-верификации → feat-009; обобщённая вставка ревью-шага, рычаг-3 (удаление норм из текста) → backlog.

#### Из backlog

- **P2** Arch-checker (deterministic layer rules) — детерминированные проверки архитектурных инвариантов: направление зависимостей, отсутствие module-level singletons, запрет cross-slice imports, запрет прямого DB-доступа из handlers. Tentative инструменты: `import-linter`, AST-чекеры, комбинация *(перенесено из Agent Harness & Workflow)*.
- **P2** Logging conventions enforcement in code reviewer — проверка соответствия logging conventions из `conventions.md` встраивается в промпт code reviewer как отдельный чек-лист *(перенесено из Agent Harness & Workflow)*.
- **P2** Анти-раздувание конвенций — формат записи `conventions.md`. Документ копится с каждым slice'ом (backend, agent, frontend) → риск разрастись до объёма, который реализатор-агенту тяжело удержать и соблюсти, и сам инструмент обесценится. Три направления: **(1) лаконичнее** — сжать/вынести развёрнутое «почему» из тела норм; **(2) опускать «трудноломаемые» нормы** — структурно выстроенное агент не сломает, держим норму там, где отклонение легко допустить и трудно заметить; **(3) Progressive disclosure / per-service** — не монолит, а подгрузка конвенций по домену/сервису в момент работы (по аналогии со скиллами). Направление 2 — естественный побочный продукт arch-checker'а (норма ушла в детерминированную проверку → удаляется из текста); направление 3 — мета-решение по формату, принимается здесь *(перенесено из Documentation Quality & Architecture)*.
- **P1** Doc-first execution discipline (review-time часть) — документация в `doc/` как единый источник правды; reviewer-чек-лист проверяет, что изменение согласовано с документацией, а дрейф помечен. Generation-time часть (правила doc-first в промптах ролей planner/implementer, `aidd-orchestrator`) остаётся в backlog — другая плоскость *(перенесено частично из Agent Harness & Workflow)*.

#### Скоуп работы

- **Deep research состояния code review (предварительный шаг).** Разбор наработок вендоров (Cursor, OpenAI, Anthropic / Claude Code, известные code-review скиллы и промпты): какие фундаментальные принципы ревью кода они проверяют *безотносительно* проектных конвенций — читаемость, сложность, мёртвый код, нейминг, корректность, безопасность. Цель — собрать базу для reviewer-промптов, чтобы ревьюилось всё: код по общим принципам + соответствие конвенциям + соответствие документации. Аналог skill discovery (feat-001), но по оси review-инструментов. Findings фиксируются как артефакт итерации.
- **Arch-checker:**
  - Выбор инструмента (`import-linter` vs свои AST-чекеры vs комбинация).
  - Конфигурация правил на основе Layers & abstractions diagram (feat-001).
  - Правила, заведомо нужные: направление зависимостей по слоям, запрет module-level singleton, запрет import'ов вне допустимых направлений.
  - Кандидаты из feat-007: (а) generic-`Exception` handler должен быть **внутри** `CORSMiddleware` (иначе 500 без CORS-заголовков — системный баг feat-007, ловится только эмпирически); (б) консистентность зеркал `problem.py` + иерархии `AppError` между main app и siem-service (зеркала разъезжались).
  - Область правил — production-пакеты; тест-дерево вне контрактов (тесты легально лезут во внутренности ради фикстур).
  - Интеграция в pre-commit hook или CI (`make check`).
- **Reviewer-промпты (многоуровневое ревью):**
  - Чек-лист по logging conventions (structlog keyword-args, level semantics, security events).
  - Чек-лист по error return types (из feat-007).
  - Чек-лист по error handling philosophy (из feat-007).
  - Чек-лист по фундаментальному качеству кода (из deep research выше): читаемость, сложность, мёртвый код, нейминг, корректность — общие принципы, не привязанные к проектным конвенциям.
  - Чек-лист по соответствию документации (doc-first): изменение согласовано с `doc/`, дрейф документации помечен.
  - Точная точка встраивания — на этапе реализации (отдельный reviewer-агент, инструкция в `.claude/skills/`, секция в `CLAUDE.md` — варианты).
- **Конвенции — формат и анти-раздувание (направления 1–3):**
  - Сжать развёрнутые «почему» в `conventions.md`, где они избыточны (направление 1).
  - Нормы, ушедшие в arch-checker (направления зависимостей, module-level state, cross-slice imports), удалить из текста — их теперь держит детерминированная проверка, дублировать прозой незачем (направление 2).
  - Принять решение по формату ведения конвенций: монолит против progressive disclosure / per-service (направление 3). При выборе per-service — определить раскладку (конвенции по домену/сервису, подгрузка в момент работы, по аналогии со скиллами) и мигрировать. Кандидат на ADR, т.к. меняет, *куда* пишут результат feat-007 и сами slice'ы.

#### Точки остановки на теорию

- Code review state-of-art: какие принципы проверяют вендорские скиллы/промпты, где граница «общий принцип» vs «проектная конвенция», что отдать детерминированному чекеру, а что LLM-reviewer'у.
- `import-linter` vs AST-чекеры: что покрывает, что нет, цена поддержки.
- pre-commit hook architecture: что в hook, что в CI.
- Reviewer-prompt design: как формулировать чек-листы, чтобы reviewer-агент стабильно их применял.
- Формат ведения конвенций: монолит vs per-service/progressive disclosure — где граница «трудноломаемой» нормы (что в arch-checker, что в тексте, что опускаем).

#### Definition of Done

- [x] Deep research по code review проведён, findings зафиксированы ([research-code-review.md](iterations/codebase-maturity/feat-008-enforcement/research-code-review.md): 13 источников, классы режима A, граница детерминированное/LLM, severity-модель).
- [x] Arch-checker настроен: 9 контрактов import-linter (слои backend/siem, транспорт-в-домене, изоляция packages), 3 AST-ассерта (порядок middleware, зеркала `problem.py`, module-singletons), eslint-boundaries (FSD). Системный реестр инвариантов — [arch-checker.md](../tech/arch-checker.md).
- [x] Arch-checker в gate: `make check` / `make check-fe` + pre-commit + CI; нарушения блокируют (проверено sanity-инъекцией: запрещённый импорт → BROKEN, откат → 0 broken).
- [x] R1-нарушения (3 роута API→Repository) — все нетривиальны, в allowlist + карточки в backlog (harvest-proposals).
- [x] Два LLM-ревьюера A/B (режим A качество / режим B контракт) в `.claude/skills/aidd-orchestrator/prompts/`; чек-листы по logging / error returns / error handling / фундаментальному качеству / doc-first; разрешение конфликтов A↔B; FSM-встройка в CODE_REVIEW.
- [x] Harvest-механизм: роль `harvester`, рубрика (backlog/конвенции/known-trivial), проверка «не закрыто ли уже», канон секции `## Follow-ups`, гейт архитектора; в workflow.md + FSM.
- [x] Норма ре-верификации + формат тест-кейсов (run-log) + шаблон с инлайн-конвенциями.
- [x] Документация: реестр arch-checker.md + README `tools/arch-checker/`; harvest и ре-верификация в workflow.md.
- [x] Конвенции: § Enforcement добавлен; рычаг-1 (плотность) — лёгкий проход при дроблении; рычаг-2 (per-domain дробление) применён, решение — ADR-025; рычаг-3 (удаление норм, ушедших в checker) — **отложен явно** (страховка на период обкатки).
- [x] Точки остановки на теорию пройдены (граница детерминированное/LLM, import-linter vs AST, severity-модели, формат конвенций).
- [x] Pre-commit gate архитектора пройден; PR #73 смержен в develop → 🚧→✅.

---

### feat-009: Testing — Philosophy + Coverage

**Цель:** сформировать тестовую культуру проекта и покрыть критичные участки.

**Статус:** 📋 Planned
**Scope:** testing
**Зависимости:** feat-002 — feat-007 (понимаем код → понимаем что тестировать)

#### Из backlog

- *(нет точечных пунктов из бэклога — итерация заведена как логическое завершение фазы)*

#### Контекст из slice-аудитов

- **Тестируемость LLM-guard и agent-flow путей (находка feat-006).** Прогон feat-006 на стенде
  показал: целый класс путей нельзя проверить без реального LLM-ключа — add-time security blocks
  (custom instructions / sphere editor / MCP form, HTTP 422), runtime `security_block` в чате,
  запись в Knowledge Sphere через checkpoint `ks_write_rest` (без ключа guard деградирует в CLEAN
  и контент не персистится), весь агентный SSE-стрим. Инфраструктура **не адаптирована под мок/
  фейк LLM**. Это прямой вход для «Test engineering → моки LLM в тестах агента»: нужен способ
  гонять guard- и agent-пути без живого провайдера (мок LLM/LangGraph, возможно replay-from-trace),
  иначе security-критичные пути остаются вне автотестов.

#### Скоуп работы

- **Test philosophy.** Сформулировать, что обязательно покрывается, что нет:
  - какие слои тестируем (handlers vs services vs repositories vs утилиты);
  - граница автоматических/ручных проверок (где UI тестим вручную, где e2e, где интеграционные);
  - что значит «фича готова» с точки зрения тестов (есть unit на бизнес-логику + integration на критичный путь? smoke?);
  - конвенция «каждый новый функционал обязан иметь тесты» — где исключения.
- **Test engineering.** Как писать и структурировать:
  - pytest fixtures и factories;
  - тестовая БД (моки vs реальный PG в Docker);
  - моки LLM в тестах агента;
  - тесты SSE-стриминга и async-кода;
  - frontend testing (Vitest / Testing Library / e2e — что используем).
  - **smoke-boot в gate** — инстанцирование `create_app()` обоих сервисов как минимальная проверка старта: статика (`make check` = ruff+mypy) не ловит startup-ломающие изменения. Пример из feat-007: регрессия аннотации `/health` (union-return под FastAPI ≥0.135) прошла мимо `make check`, приложение не поднялось бы — поймана только на реальном `create_app()`. Дёшево, ловит целый класс «не стартует».
- **Покрытие критичных участков.** На основе findings из slice-аудитов — точечно дописать тесты:
  - критичные пути auth, security guard, SIEM pipeline;
  - business invariants, выявленные в slice-аудитах;
  - точечные автотесты, написанные в slice-итерациях, привести к общей рамке (структура, фикстуры, naming).
- Обновление `doc/tech/conventions.md` — раздел про тесты.

#### Точки остановки на теорию

- Test pyramid vs trophy — какая модель нам ближе.
- Property-based testing (Hypothesis) — есть ли смысл подключать.
- pytest patterns: parametrize, fixtures with scope, factories, async тесты.
- LLM testing strategies: mock LLM, replay-from-trace, eval-наборы.

#### Definition of Done

- [ ] Test philosophy зафиксирована в `conventions.md`.
- [ ] Test engineering conventions зафиксированы (фикстуры, моки, структура тестов).
- [ ] Критичные участки покрыты тестами (точный список — на этапе реализации).
- [ ] `make test` запускается локально и в CI, проходит без падений.
- [ ] Точки остановки на теорию пройдены.

## Что НЕ входит в фазу

Явно выводим за рамки, чтобы не размывать scope:

- **Meta Agent Harness** — самоулучшающийся слой workflow (background-агент анализирует артефакты итераций и истории сообщений, предлагает улучшения skill'ов / инструкций / чек-листов). Отдельный домен, отдельная фаза. См. соответствующий пункт в `backlog.md` (Meta секция).
- **Documentation Quality & Architecture как самостоятельная фаза** — Doc feedback loop, Tech/ full documentation audit, REST API contracts summary, DB architecture summary. Не цели текущей фазы. Layers & abstractions diagram в feat-001 — обслуживающий артефакт, не часть doc-audit фазы.
- **Frontend stack deep-read / Linter/formatter stack deep-read** (P3 из Tech Debt & Competency) — задачи на компетенцию архитектора, не на код. Не часть фазы.
- **Async / cloud agent workflow** — отдельная инфраструктурная задача, не часть текущей фазы (хотя slice-итерации могут параллелиться через cloud-агентов по факту, инфраструктура async-workflow строится отдельно).
