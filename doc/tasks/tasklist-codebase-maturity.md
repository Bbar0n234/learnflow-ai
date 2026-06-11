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
- **Skill first, code second.** Внутри slice'а: сначала прокачиваем теорию через skill, потом смотрим код. Не наоборот.
- **Skill discovery — обязательный первый шаг.** Релевантные skill'ы подбираем заранее через web search по доменам кодовой базы. Если skill нашёлся — почти наверняка нужен; беглое ознакомление → решаем, берём или нет.
- **Точки остановки на теорию.** На любом шаге slice'а можно (и нужно) остановиться, чтобы архитектор разобрался в теории. Это не отвлечение от задачи — это часть задачи. Мини-подпункты «здесь стоит разобраться в теории» явно отмечены в DoD каждой итерации.
- **Интерактивный формат.** Агент изучает кусочек кодовой базы автономно; архитектор спрашивает, уточняет, обучается, направляет.
- **Конвенции — continuous.** Каждый slice добавляет в `doc/tech/conventions.md` по факту найденного. Финализирующий pass (feat-007) не первая запись, а сборка/уточнение накопленного.
- **Тесты — естественное завершение.** Понимаем код → понимаем, что и как тестировать.

## Overview

| Итерация | Статус | Scope | Закрывает |
|----------|--------|-------|-----------|
| feat-001 | ✅ Done | foundation | Skill Discovery + Layers & Abstractions Diagram |
| feat-002 | 📋 Planned | backend / REST | REST API slice: api-design-principles skill + поглощение REST API cleanup (8 пунктов аудита 2026-04-04) |
| feat-003 | 📋 Planned | db | DB slice: postgresql skill, индексы, constraints, типы, паттерны миграций |
| feat-004 | 📋 Planned | backend / fastapi | Backend/FastAPI slice: fastapi skill + поглощение точечных техдолгов (SIEM MetaEmitter, дубль SecurityEvent, CORS_ORIGINS, SIEM follow-ups) |
| feat-005 | 📋 Planned | agent | Agent runtime slice: langgraph-patterns (авторский) + кандидаты langgraph-* от langchain-ai + поглощение Reasoning ChatOpenAI everywhere (langchain-architecture отклонён в feat-001) |
| feat-006 | 📋 Planned | frontend | Frontend slice: skill discovery for frontend, ручной slice если skill отсутствует |
| feat-007 | 📋 Planned | cross-cutting | Кросс-резрезные конвенции: error return types + error handling philosophy (graceful degradation vs fail-fast) |
| feat-008 | 📋 Planned | enforcement | Arch-checker (детерминированные проверки) + Reviewer-промпты (logging, error returns, doc-first) |
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

**Статус:** 📋 Planned
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

- [ ] Skill `api-design-principles` изучен, ключевые принципы зафиксированы.
- [ ] Все 8 пунктов аудита 2026-04-04 либо закрыты, либо явно отложены с обоснованием.
- [ ] Status codes везде корректны (201 на POST create, 204 на DELETE без body, и т.д.).
- [ ] List responses везде имеют единый envelope с pagination metadata.
- [ ] REST-конвенции добавлены в `doc/tech/conventions.md`.
- [ ] Точки остановки на теорию пройдены и (если решено архитектурно) зафиксированы.

---

### feat-003: DB Slice

**Цель:** аудит схемы БД и query-паттернов через `postgresql` skill, формирование DB-конвенций.

**Статус:** 📋 Planned
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

- [ ] Skill `postgresql` изучен.
- [ ] Аудит схемы и query-паттернов проведён, findings зафиксированы.
- [ ] Критичные индексы добавлены (если выявлены пропуски).
- [ ] DB-конвенции добавлены в `doc/tech/conventions.md`.
- [ ] Точки остановки на теорию пройдены.

---

### feat-004: Backend / FastAPI Slice + SIEM Hygiene

**Цель:** аудит backend-инфраструктуры через `fastapi` skill, закрытие точечных техдолгов в SIEM и конфиге.

**Статус:** 📋 Planned
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

- [ ] Skill `fastapi` изучен.
- [ ] SIEM `MetaEmitter` singleton устранён (state в app.state, инициализация в lifespan, route'ы через Depends).
- [ ] Дубль `SecurityEvent` в siem-service удалён, импорт из `siem_contracts.events`.
- [ ] `CORS_ORIGINS` парсится надёжно (CSV или `NoDecode`).
- [ ] SIEM follow-ups закрыты (UP042 + uv pin + line-length 100 + DDL миграции через autogenerate).
- [ ] FastAPI-конвенции добавлены в `doc/tech/conventions.md`.
- [ ] Точки остановки на теорию пройдены.

---

### feat-005: Agent Runtime Slice

**Цель:** аудит agent runtime через `langgraph-patterns` skill (+ официальные кандидаты `langgraph-*` от langchain-ai — подтверждение при заходе), миграция на единые паттерны. `langchain-architecture` отклонён в feat-001 (LangChain-обёртки при raw LangGraph), см. `doc/tech/skill-map.md`.

**Статус:** 📋 Planned
**Scope:** agent
**Зависимости:** feat-001

#### Из backlog

- **P2** LangGraph / LangChain audit via agent-скиллы (изначально langchain-architecture — отклонён в feat-001, заменён на `langgraph-patterns` + кандидаты от langchain-ai) *(перенесено из Tech Debt & Competency)*.
- **P2** Reasoning ChatOpenAI everywhere — convention + migration. Все модели проекта используют `ReasoningChatOpenAI`, не plain `ChatOpenAI`. Добить summarizer, guard на `ReasoningChatOpenAI`; зафиксировать convention в `conventions.md` *(перенесено из Agent)*.

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

- [ ] Skill'ы `langchain-architecture` и `langgraph-patterns` изучены.
- [ ] Summarizer и guard переведены на `ReasoningChatOpenAI`.
- [ ] Reasoning convention зафиксирован в `conventions.md` (раздел Reasoning LLMs уже есть, обновить формулировкой «все модели проекта используют ReasoningChatOpenAI by default»).
- [ ] LangGraph-конвенции добавлены в `conventions.md`.
- [ ] Точки остановки на теорию пройдены.

---

### feat-006: Frontend Slice

**Цель:** аудит фронтенд-кода, формирование frontend-конвенций.

**Статус:** 📋 Planned
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

- [ ] Frontend-skill найден (или зафиксировано, что подходящего нет — slice идёт ручным).
- [ ] Аудит структуры проведён, findings зафиксированы.
- [ ] Точечные правки применены.
- [ ] Frontend-конвенции добавлены в `conventions.md`.
- [ ] Точки остановки на теорию пройдены.

---

### feat-007: Cross-Cutting Conventions (Error Handling)

**Цель:** формализовать кросс-резрезные конвенции, которые не привязаны к одному slice'у.

**Статус:** 📋 Planned
**Scope:** cross-cutting
**Зависимости:** feat-002, feat-003, feat-004, feat-005, feat-006 (нужны накопленные примеры)

#### Из backlog

- **P2** Error return types conventions — exceptions / Result-Either / Optional + None, границы применимости *(перенесено из Agent Harness & Workflow)*.

#### Скоуп работы

- **Error return types.** На реальных примерах из кодовой базы (накопленных в slice-итерациях) сформулировать границы:
  - exceptions — для неожидаемых ошибок и границ системы;
  - Result/Either — для ожидаемых бизнес-ошибок (если решим так);
  - Optional — для отсутствия значения без ошибки.
- **Error handling philosophy.** Где graceful degradation, где fail-fast: какие сервисы и слои деградируют (LLM провайдер недоступен → fallback), какие падают (БД недоступна → 503). На каком уровне принимается решение (handler / service / infra).
- Что ещё всплыло по ходу slice'ов и достойно кросс-резрезной фиксации — записать.
- Обновление `doc/tech/conventions.md` — раздел про error handling.

#### Точки остановки на теорию

- Result/Either в Python: returns library, проектные обёртки, плюсы/минусы vs exceptions.
- Graceful degradation vs circuit breaker — границы понятий.
- Где в FastAPI ловить и куда отдавать ошибки: middleware vs exception handler vs Depends.

#### Definition of Done

- [ ] Error return types conventions зафиксированы в `conventions.md`.
- [ ] Error handling philosophy зафиксирована в `conventions.md`.
- [ ] Конвенции иллюстрированы примерами из реального кода проекта (не абстрактные снippets).
- [ ] Точки остановки на теорию пройдены.

---

### feat-008: Enforcement — Arch-Checker + Reviewer Prompts

**Цель:** автоматизировать проверку конвенций, сформированных в slice-аудитах и feat-007.

**Статус:** 📋 Planned
**Scope:** enforcement (workflow / CI)
**Зависимости:** feat-007 (нужны зафиксированные конвенции для enforcement'а)

#### Из backlog

- **P2** Arch-checker (deterministic layer rules) — детерминированные проверки архитектурных инвариантов: направление зависимостей, отсутствие module-level singletons, запрет cross-slice imports, запрет прямого DB-доступа из handlers. Tentative инструменты: `import-linter`, AST-чекеры, комбинация *(перенесено из Agent Harness & Workflow)*.
- **P2** Logging conventions enforcement in code reviewer — проверка соответствия logging conventions из `conventions.md` встраивается в промпт code reviewer как отдельный чек-лист *(перенесено из Agent Harness & Workflow)*.

#### Скоуп работы

- **Arch-checker:**
  - Выбор инструмента (`import-linter` vs свои AST-чекеры vs комбинация).
  - Конфигурация правил на основе Layers & abstractions diagram (feat-001).
  - Правила, заведомо нужные: направление зависимостей по слоям, запрет module-level singleton, запрет import'ов вне допустимых направлений.
  - Интеграция в pre-commit hook или CI (`make check`).
- **Reviewer-промпты:**
  - Чек-лист по logging conventions (structlog keyword-args, level semantics, security events).
  - Чек-лист по error return types (из feat-007).
  - Чек-лист по error handling philosophy (из feat-007).
  - Точная точка встраивания — на этапе реализации (отдельный reviewer-агент, инструкция в `.claude/skills/`, секция в `CLAUDE.md` — варианты).

#### Точки остановки на теорию

- `import-linter` vs AST-чекеры: что покрывает, что нет, цена поддержки.
- pre-commit hook architecture: что в hook, что в CI.
- Reviewer-prompt design: как формулировать чек-листы, чтобы reviewer-агент стабильно их применял.

#### Definition of Done

- [ ] Arch-checker настроен, минимум 3-5 правил активны (направления зависимостей + module-level state + cross-slice imports).
- [ ] Arch-checker запускается в pre-commit или CI, нарушения блокируют merge.
- [ ] Reviewer-промпты содержат чек-листы по logging / error returns / error handling.
- [ ] Документация: как добавлять новые правила в arch-checker, как обновлять reviewer-чек-листы.
- [ ] Точки остановки на теорию пройдены.

---

### feat-009: Testing — Philosophy + Coverage

**Цель:** сформировать тестовую культуру проекта и покрыть критичные участки.

**Статус:** 📋 Planned
**Scope:** testing
**Зависимости:** feat-002 — feat-007 (понимаем код → понимаем что тестировать)

#### Из backlog

- *(нет точечных пунктов из бэклога — итерация заведена как логическое завершение фазы)*

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
- **Покрытие критичных участков.** На основе findings из slice-аудитов — точечно дописать тесты:
  - критичные пути auth, security guard, SIEM pipeline;
  - business invariants, выявленные в slice-аудитах.
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
