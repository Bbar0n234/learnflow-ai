# Tasklist: Post-MVP Stabilization

## Контекст

v1.1 (Production Readiness) завершён. Переход на итеративный режим: использование → обратная связь → backlog → триаж → реализация. Фокус — стабилизация основного функционала.

**Источник:** [backlog.md](../backlog.md)
**Зависимости:** Production Readiness (tasklist-production.md) ✅

## Легенда

- 📋 Planned
- 🚧 In Progress
- ✅ Done
- ⏸️ Paused
- ❌ Cancelled

## Overview

| Итерация | Статус | Scope | Закрывает |
|----------|--------|-------|-----------|
| fix-001 | ✅ Done | cross-cutting | Frontend bug fixes (4 элемента backlog) |
| feat-001 | 📋 Planned | cross-cutting | Chat UX: auto title + thinking indicator + delete chats |
| feat-002 | ✅ Done | agent/backend | Agent observability & tooling |
| feat-003 | ✅ Done | cross-cutting | Runtime agent configuration (3 tracks: Langfuse+Model, Memory, User MCP) |
| feat-004 | ✅ Done | agent/backend | Prompt injection protection |
| feat-005 | 📋 Planned | cross-cutting | Security Event Pipeline (SIEM Core): collection, correlation, alerting, monitoring UI |
| feat-006 | ✅ Done | agent | Security 2.0: Universal I/O Guard + Boundary Enforcement |
| feat-007 | 📋 Planned | cross-cutting | SIEM Extensions: dashboard, basic response actions, search, notifications, export |

## Параллелизация

```
feat-003 (Agent Config: 3 tracks) ── feat-004 (Security) ─┬─ feat-005 (SIEM Core) ── feat-007 (SIEM Extensions)
                                                          └─ feat-006 (Security 2.0) ─────────────────────────
feat-001 (Chat UX) ── когда будет время ─────────────────────────────────────────────────────────────────────
```

- **feat-003** — первый приоритет. Три трека проектируются параллельно (Track A: Langfuse+Model, Track B: Memory, Track C: User MCP), реализуются вместе
- **feat-004** — после feat-003 (security проектируется по финальной поверхности атаки)
- **feat-005** — после feat-004 (строится поверх security-событий Security 1.0; forward compatible с Security 2.0)
- **feat-006** — после feat-004, параллельно с feat-005, не блокирует и не блокируется (разные scope: SIEM = aggregation/correlation events, Security 2.0 = расширение защиты на новые I/O границы графа)
- **feat-007** — после feat-005; продуктовые улучшения поверх SIEM Core (dashboard, basic ban, search, notifications, export)
- **feat-001** — отложена, не блокирует реальное использование

## Итерации

### fix-001: Frontend Bug Fixes

**Цель:** исправить накопившиеся UX-баги фронтенда.

**Статус:** ✅ Done
**Scope:** cross-cutting (Frontend + Backend + Infra) — расширен из-за feedback persistence
**Параллельно с:** feat-002

#### Из backlog

- [x] **P1** Feedback иконки (like/dislike) пропадают при перезагрузке страницы — Redis + backend + frontend
- [x] **P1** Артефакт-карточки пропадают из истории чата — не воспроизводится (2026-03-30)
- [x] **P2** Дублирование сообщения пользователя при переключении вкладки во время стриминга
- [x] **P2** Hover states: курсор не меняется на кнопках, непонятно что кликабельно

#### Документация

- [design-brief.md](iterations/frontend/fix-001-frontend-bugs/design-brief.md) — Feedback persistence: архитектура решения
- [plan.md](iterations/frontend/fix-001-frontend-bugs/plan.md) — Implementation plan
- [summary.md](iterations/frontend/fix-001-frontend-bugs/summary.md) — Post-implementation summary, отклонения

---

### feat-001: Chat UX — Auto Title + Thinking Indicator + Delete Chats

**Цель:** переработка UX чата: поле ввода для первого сообщения (не title), автогенерация title моделью, индикатор рассуждения, удаление чатов.

**Статус:** 📋 Planned
**Scope:** cross-cutting (Frontend + Backend)

#### Из backlog

- **P1** Chat input: поле ввода должно быть для первого сообщения, не для title. Title auto-generated моделью *(cross: Backend)*
- **P2** Индикатор "модель рассуждает" до начала стриминга текста *(cross: Backend)*
- **P2** Удаление чатов — нет кнопки, только проекты можно удалять *(cross: Frontend, Backend)*

---

### feat-002: Agent Observability & Tooling

**Цель:** улучшение observability агента (reasoning tokens, pricing) и конфигурации инструментов.

**Статус:** ✅ Done
**Scope:** agent/backend
**Параллельно с:** fix-001

#### Из backlog

- **P1** Reasoning tokens → Langfuse additional kwargs (прозрачность рассуждений)
- **P2** OpenRouter модели: программная инициализация pricing в Langfuse
- **P2** MCP Firecrawl: фильтрация инструментов (13+ → нужны 2-3)

#### Документация

- [design-brief.md](iterations/post-mvp/feat-002-agent-obs/design-brief.md)
- [plan.md](iterations/post-mvp/feat-002-agent-obs/plan.md)
- [summary.md](iterations/post-mvp/feat-002-agent-obs/summary.md)

---

### feat-003: Runtime Agent Configuration

**Цель:** runtime-конфигурация агента: смена модели без перезапуска, управление промптами через Langfuse, memory architecture (custom instructions, user memory), per-user MCP серверы.

**Статус:** ✅ Done
**Scope:** cross-cutting (Agent + Backend + Frontend)

#### Из backlog

- **P1** Смена модели без перезапуска сервиса (runtime model switching) *(cross: Backend, Frontend)*
- **P2** Версионирование промптов — управление версиями system prompt, откат к предыдущим *(cross: Agent, Backend)*
- **P2** Кастомные инструкции — на уровне пользователя, проекта и чата (помимо Knowledge Sphere) *(cross: Backend, Frontend)*

#### Tracks (проектируются независимо, реализуются вместе)

- **Track A** — Langfuse Prompt Management + Model Switching (prompt versioning, env separation, model cascade: global → per-user → per-project → per-chat)
- **Track B** — Memory Architecture (custom instructions, user memory, agent notes — расширение системы памяти за пределы KS)
- **Track C** — User MCP Servers (per-user внешние инструменты, dynamic tools)

#### Definition of Done

**Track A — Langfuse Prompt Management + Model Switching:**
- [ ] `PromptProvider` фетчит промпты (`system`, `summarization`) из Langfuse; при недоступности Langfuse — file fallback + warning в логах
- [ ] Startup seed: на пустом Langfuse промпты создаются из файлов с label `production`
- [ ] Model override каскад: thread → project → user → Langfuse prompt.config → agent.yaml. NULL на любом уровне = наследование от уровня выше
- [ ] `GET /api/models` возвращает whitelist из `agent.yaml`; PUT model на уровне user/project/thread сохраняется в соответствующую settings-таблицу
- [ ] Смена модели через UI → следующее сообщение обрабатывается выбранной моделью (проверяемо через Langfuse trace: model name в generation)
- [ ] GraphFactory: per-request build+compile; read-операции (`get_history`) через `checkpointer.aget_tuple()` напрямую, без графа
- [ ] agent_node: оркестратор + extracted functions (`_reduce_context`, `_build_system_message`, `_invoke_llm`)

**Track B — Memory Architecture:**
- [ ] `PUT /api/users/me/instructions` сохраняет текст → он появляется в system message в блоке `<custom_instructions>` (проверяемо через Langfuse trace: input system message)
- [ ] `GET /api/users/me/memories` возвращает записи, созданные агентом
- [ ] Агент автономно использует `save_user_memory` / `delete_user_memory` в контексте диалога (tool calls видны в Langfuse trace)
- [ ] Settings page (`/settings`): textarea для instructions + read-only список memories, навигация через иконку в sidebar
- [ ] `store_helpers.format_index()` — generic helper, используется и для KS, и для User Memory

**Track C — User MCP Servers:**
- [ ] CRUD для user/project/thread MCP серверов через REST API; `POST .../test` проверяет соединение и возвращает список tools
- [ ] Additive merge: tools со всех уровней (thread ∪ project ∪ user ∪ global) доступны агенту; при конфликте имён global tools приоритетнее
- [ ] SSRF: `POST /api/users/me/mcp-servers` с URL на private IP (127.0.0.1, 10.x.x.x) → 400
- [ ] stdio transport → 400; API key зашифрован (Fernet), API возвращает только `has_api_key: bool`
- [ ] Graceful degradation: сбой user MCP сервера → агент работает с global tools, warning в логах

**Cross-cutting:**
- [ ] `make check` + `make check-fe` проходят
- [ ] Миграции применяются на чистой БД (`docker-compose down -v → docker-up-db → migrate`)
- [ ] E2E: задать custom instructions → сменить модель → отправить сообщение → агент следует инструкциям, использует выбранную модель, tool calls и model видны в Langfuse

#### Документация

- [design-brief.md](iterations/post-mvp/feat-003-agent-config/design-brief.md) — Design brief: контекст, решения, open questions по всем трекам
- [plan.md](iterations/post-mvp/feat-003-agent-config/plan.md) — Implementation plan: 7 phases, API verification, logging conventions
- [test-cases.md](iterations/post-mvp/feat-003-agent-config/test-cases.md) — 101 test case (95 pass, 6 deferred), 14 findings
- [summary.md](iterations/post-mvp/feat-003-agent-config/summary.md) — Post-implementation summary: отклонения, дополнения, верификация
- [ADR-013](../tech/adr/ADR-013-model-settings-storage.md) — Per-Scope Settings Storage: typed tables vs polymorphic vs JSONB
- [ADR-014](../tech/adr/ADR-014-dynamic-model-resolution.md) — Graph Factory: per-request graph build (model + tools)
- [ADR-015](../tech/adr/ADR-015-unified-memory-backend.md) — LangGraph Store как unified memory backend (Track B)
- [ADR-016](../tech/adr/ADR-016-per-scope-mcp-servers.md) — Per-Scope MCP Servers: storage, encryption, additive merge (Track C)

---

### feat-004: Prompt Injection Protection

**Цель:** MVP-защита от prompt injection: input guard, system prompt hardening, canary token output check, Langfuse observability.

**Статус:** ✅ Done
**Scope:** agent/backend
**After:** feat-003

#### Из backlog

- **P1** Prompt injection protection — MVP-защита от direct/indirect PI. Threat model и blue-team strategy проработаны (`doc/security/`), реализации нет *(cross: Backend)*

#### Definition of Done

**SecurityGuard:**
- [x] `SecurityGuard.check()` — invisible Unicode chars → INJECTION; LLM classifier → CLEAN / SUSPICIOUS / INJECTION; canary в input → INJECTION
- [x] Retry: невалидный ответ classifier → retry до `max_retries`, все исчерпаны → CLEAN (graceful degradation)
- [x] Guard LLM недоступен → CLEAN + warning в логах
- [x] INJECTION → `security_block` SSE event, запрос блокируется до запуска графа
- [x] SUSPICIOUS → запрос проходит, усиленный лог

**System Prompt Hardening:**
- [x] Hardened template: instruction hierarchy, trust boundaries на `<custom_instructions>`, sandwich defense, canary token
- [x] `system.txt` не изменён — hardening только Jinja-обёртка

**Canary Token:**
- [x] Генерация: HMAC(CANARY_SECRET, thread_id), per-session
- [x] Canary в output (full_response) → abort stream + `security_block(reason="canary_leak")`

**Langfuse Observability:**
- [x] Score `security_verdict` (categorical) на trace
- [x] Guardrail observation (`as_type="guardrail"`, name `input-guard`)
- [x] Metadata (`blocked`, `detection_layer`, `block_reason`) при инцидентах
- [x] Degradation → WARNING level, `degraded: true`

**Cross-cutting:**
- [x] Classifier prompt в Langfuse (seed при старте)
- [x] `agent.yaml`: секция `security` (guard_model, max_retries)
- [x] `CANARY_SECRET` в `.env.example`
- [x] `make check` проходит

#### Сознательно deferred (backlog → Security 2.0)

KS Write Guard, LLM Output Classifier, SUSPICIOUS → ограничения, Tool Result Guard, Semantic Similarity, Async Guard, Multi-turn escalation — оставлены как attack vectors для Red Team и/или требуют отдельной проработки. Детали — в backlog (секция Security).

#### Документация

- [design-brief.md](iterations/post-mvp/feat-004-security/design-brief.md) — Architecture, компоненты, интерфейсы, промпты, 20 decisions
- [langfuse-observability-decisions.md](iterations/post-mvp/feat-004-security/langfuse-observability-decisions.md) — Решения по Langfuse: score + guardrail + metadata
- [plan.md](iterations/post-mvp/feat-004-security/plan.md) — Implementation plan: 11 phases, API verification
- [test-cases.md](iterations/post-mvp/feat-004-security/test-cases.md) — 71 test case (59 pass, 12 deferred), 5 findings
- [summary.md](iterations/post-mvp/feat-004-security/summary.md) — Post-implementation summary: отклонения, решения, tech debt
- [architecture.md](../security/architecture.md) — Архитектурный документ: три слоя защиты, SecurityGuard, canary, hardening, observability
- [ADR-017](../tech/adr/ADR-017-prompt-injection-defense.md) — Prompt Injection Defense: sync guard, full history, fail-open, hardening wrapper

---

### feat-005: Security Event Pipeline (SIEM Core)

**Цель:** SIEM-подсистема: сбор, нормализация, хранение и корреляция security-событий из всех источников (SecurityGuard, auth, rate limiter). Alerting, REST API, React monitoring page. Закрывает academic SIEM requirements (R1–R10) + backlog P2.

**Статус:** 📋 Planned
**Scope:** cross-cutting (Backend + Frontend)
**After:** feat-004

#### Из backlog

- **P2** Security Event Pipeline — unified subsystem for collecting, storing, and correlating security events from all sources (auth, rate limiter, security guard/Langfuse). structlog processor as integration point. Correlation engine (background asyncio task) with SQL rules by time window + grouping (IP, user_id). Result: `security_events` + `security_alerts` tables in PostgreSQL, REST API + React page for monitoring. *(cross: Backend, Frontend)*

#### Definition of Done

Декомпозиция на 4 трека для последовательной реализации в одной ветке. DoD проверяется агентом-тестировщиком через `test-cases.md`.

**T1 — Vocabulary + Contracts + Producer:**
- [ ] `doc/tech/security-events.md` создан: полный vocabulary `event_type`, форма `metadata` per type, обязательность `identifiers`
- [ ] `packages/siem-contracts/` собран как uv-workspace member: `SecurityEvent` (Pydantic), `Literal[...]` event_type, `SecurityEventIdentifiers`
- [ ] structlog processor строит `SecurityEvent` из `logger.*(security_event=True, ...)` + `contextvars`; identifiers подмешиваются автоматически (HTTP middleware: `ip` / `request_id` / `user_agent_hash`; auth dep: `user_id` / `session_id`; chat route: `thread_id` / `project_id`)
- [ ] Producer'ы (`SecurityGuard`, auth-handlers, rate limiter) пишут события через canonical `event_type`; existing log-вызовы рефакторятся
- [ ] Publisher loop публикует события в Redis Stream `security.events`; видно через `redis-cli XREAD`

**T2 — SIEM service skeleton + ingestion:**
- [ ] siem-service в `docker-compose.yml` с собственной PostgreSQL БД и миграциями (`siem_events` с `UNIQUE event_id`, индексы по timestamp / event_type)
- [ ] Subscriber: XREADGROUP → Pydantic-валидация → INSERT с дедупом → XACK; pending list переживает рестарт
- [ ] Минимальный REST `GET /security/events`: pagination + фильтры (event_type, severity, time range)
- [ ] Producer-сайд → Redis → consumer → БД → API: end-to-end доставка одного события воспроизводима

**T3 — Correlation + Alerts + RBAC + полный API + Meta-log:**
- [ ] Миграции `siem_alerts`, `correlation_rules`; идемпотентный seed правил при старте (≥4 baseline: brute_force_auth, injection_spike, targeted_user_attack, mass_suspicious)
- [ ] Correlation engine: asyncio polling 10s; стратегии Threshold / Sequence / Aggregate; срабатывание создаёт алерт
- [ ] Alert deduper: open-alert policy с возрастным лимитом 24h
- [ ] Полный REST API: `GET /security/alerts`, `PATCH /security/alerts/:id` (acknowledge / resolve), CRUD `correlation_rules`
- [ ] Identity: JWT HS256 общий с main app, claim `is_admin`; admin-only зависимость на всех security-endpoints
- [ ] Bootstrap админа: миграция `users.is_admin` + env `INITIAL_ADMIN_USERNAME` в main app; идемпотентный seed
- [ ] Meta-log: PATCH alerts эмитит `siem.alert.acknowledged` / `siem.alert.resolved` через тот же producer-pipeline

**T4 — Frontend + Integration + ADRs:**
- [ ] React страница `/security` (lazy chunk + RBAC guard): три view (events / alerts / rules) с фильтрами и пагинацией
- [ ] Все UI labels на русском
- [ ] E2E через UI: админ логинится, видит события и алерты, может acknowledge / resolve, видит срабатывания correlation rules
- [ ] ADR-018..021 проверены и актуализированы под фактическую реализацию

**Cross-cutting:**
- [ ] `make check` + `make check-fe` проходят
- [ ] Миграции применяются на чистой БД (`docker-compose down -v` → `make docker-up-db` → `make migrate`) для main app и siem-service независимо
- [ ] `siem-contracts` импортируется и main app, и siem-service из локального workspace источника
- [ ] Forward compatibility: добавление нового `event_type` требует только расширения Literal-vocabulary в shared-пакете, без миграций SIEM
- [ ] `architecture.md`, `observability.md`, `backend.md` актуализированы

#### Сознательно deferred

Dashboard & Metrics, basic response actions (ban IP/user), расширенный Search, Notifications, Export — вынесены в feat-007. Threat Intelligence, UEBA, SOAR automation, Log Forwarding, Compliance Frameworks — out of scope (not planned).

#### Документация

- [design-brief.md](iterations/post-mvp/feat-005-security-event-pipeline/design-brief.md) — Context, scope, функциональная карта, контракт событий, scope boundaries
- [test-cases.md](iterations/post-mvp/feat-005-security-event-pipeline/test-cases.md) — 60 тестовых кейсов: Layer 0 (Automated) / Layer 1 (Component, по трекам T1-T4) / Layer 2 (Integration) / Layer 3 (E2E)

---

### feat-006: Security 2.0 — Universal I/O Guard + Boundary Enforcement

**Цель:** расширить защиту от prompt injection на все I/O границы графа (tool input/output, KS write, semantic output) + ввести бинарную enforceable границу confidentiality (PUBLIC capabilities / PRIVATE identifiers).

**Статус:** ✅ Done
**Scope:** agent (+ minor frontend для UX inline-error на add-time формах)
**After:** feat-004
**Параллельно с:** feat-005

#### Triggered by

- Red Team incidents: tools/schemas leak через social engineering, MCP injection vector confirmed
- Investigation: [tool-confidentiality-investigation.md](iterations/post-mvp/feat-006-security-2.0/tool-confidentiality-investigation.md)

#### Из backlog (переходят в этот scope)

- **P1** KS Write Guard
- **P1** LLM Output Classifier
- **P2** Tool Result Guard
- **P2** Semantic Similarity output check (становится частью Output Classifier composite)
- **P2** Guard LLM observability — закрыт в Engineering follow-up (EF-5c/EF-5d): `normalize_usage_for_langfuse` + pricing re-seed для `output_reasoning`
- **P2** Guard LLM reasoning — закрыт в Engineering follow-up (EF-5b): guard model переключена на `google/gemini-3-flash-preview` (text reasoning); `create_guard_llm` уже выбирает `ReasoningChatOpenAI` при `include_reasoning: true`

#### Новые элементы (вне existing backlog)

- Tool Call Guard (новый attack vector — MCP injection через arguments)
- Boundary formalization (encapsulation principle: PUBLIC/PRIVATE)
- Composite deterministic detector (tool-name greppable + threshold)
- Eval infrastructure (trace harvest → curated dataset → regression runner)

#### Research items (pending, sub-agents)

- **R1** — Industry MCP defense overview
- **R2** — Output vs system prompt similarity metric
- **R3** — Confidentiality boundary precise definition

#### Сознательно вне scope (остаётся в backlog или другие итерации)

- Multi-turn escalation detection — symptom Класса 2, не отдельная проблема (текущий guard видит history)
- Async Guard — latency-оптимизация, после functional baseline
- SecurityObserver extraction — SIEM-related, отдельно
- Base prompt + security wrapper merge — tech debt, отдельно
- Reasoning ChatOpenAI everywhere — отдельный convention/backlog item
- Model whitelist expansion — отдельный backlog item
- **SUSPICIOUS actions (graduated response)** — переезжают в feat-007 (SIEM Extensions) как расширение существующего ban mechanism. В Sec 2.0 verdict только логируется как сейчас
- **KS Write через direct REST endpoint** — open question при детальном проектировании Phase 3. Делаем, если обёртывается без капитального рефакторинга абстракций; откидываем, если требует перелопачивания половины проекта

#### Документация

- [design-brief.md](iterations/post-mvp/feat-006-security-2.0/design-brief.md) — Skeleton: context, threat model, principles, coverage map, eval strategy, phasing. Финализация после research
- [tool-confidentiality-investigation.md](iterations/post-mvp/feat-006-security-2.0/tool-confidentiality-investigation.md) — Investigation notes (Iteration 1, провал, Key Insight)
- [plan.md](iterations/post-mvp/feat-006-security-2.0/plan.md) — Implementation plan Phases 1–3 (Track A, guard-код)
- [plan-phase-4.md](iterations/post-mvp/feat-006-security-2.0/plan-phase-4.md) — Implementation plan Phase 4 (Track B, eval infra)
- [summary.md](iterations/post-mvp/feat-006-security-2.0/summary.md) — Post-implementation summary (Track A — код + ручная верификация ⏳ за архитектором; Track B — single-run сделан вручную через Langfuse UI, регулярный pipeline не доводился, пакет переведён в **archived (parked)** 2026-04-26) + раздел `Engineering follow-up (2026-04-25)` (EF-1..EF-6 после первого rerun-цикла; EF-6 — изоляция guard LLM от parent callback chain + known limitation по иерархии guard observations в Langfuse UI)
- [ADR-022](../tech/adr/ADR-022-protected-disclosable-boundary.md) — PROTECTED / DISCLOSABLE Confidentiality Boundary: бинарная граница, MCP trust hierarchy, enforcement semantics
- [ADR-023](../tech/adr/ADR-023-two-level-detection.md) — Two-Level Detection: deterministic detectors + LLM classifier, composite prompt, classifier isolation
- [ADR-024](../tech/adr/ADR-024-streaming-security-guard.md) — Streaming Security Guard: live stream с post-classifier validation, block mechanics, replace-by-id

---

### feat-007: SIEM Extensions

**Цель:** продуктовые расширения поверх SIEM Core (feat-005): dashboard с метриками, базовые manual response actions (ban IP/user из UI), расширенный поиск/фильтры, in-app notifications, export событий и алертов.

**Статус:** 📋 Planned
**Scope:** cross-cutting (Backend + Frontend)
**After:** feat-005

#### Scope

- **Dashboard & Metrics** — агрегатные REST-эндпоинты поверх `security_events` / `security_alerts`; графики events/hour, severity distribution, top event_types, trends
- **Basic response actions** — manual-trigger блокировка (ban IP / ban user) из алерта или events list. Отдельная таблица `security_blocks`; auth middleware читает её и отклоняет заблокированные IP/user. SIEM остаётся точкой наблюдения, executor — auth middleware
- **Graduated Response extension** — correlation rule на SUSPICIOUS verdicts от SecurityGuard (Sec 1.0/2.0): `N suspicious в M сообщениях → automated ban через существующий security_blocks mechanism`. Связывает graduated response (CLEAN / SUSPICIOUS / INJECTION) с actionable enforcement. Сейчас SUSPICIOUS только логируется; здесь добавляется actionable слой поверх threshold-правил. Приходит из feat-006 (Sec 2.0) как сознательно deferred функционал
- **Extended Search** — полнотекстовый поиск по metadata, timeline-view, drill-down от алерта к событиям. GIN index на JSONB
- **Notifications** — in-app badge / toast при новых алертах (триггер на `status=new`)
- **Export** — CSV/PDF экспорт событий и алертов за период

#### Архитектурный инвариант

Response actions расширяют ответственность SIEM с чистого observer'а на observer+manual-responder. Сепарация сохраняется через отдельную таблицу блокировок: SIEM записывает intent, auth middleware исполняет. Автоматические response actions (auto-ban на threshold) в scope не входят — это SOAR, остаётся not planned.

#### Документация

На этапе tasklist содержательный design-brief не пишется; создаётся при старте итерации.
