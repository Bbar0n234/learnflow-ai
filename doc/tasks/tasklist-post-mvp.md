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
| feat-005 | ✅ Done | cross-cutting | Security Event Pipeline (SIEM Core): collection, correlation, alerting, monitoring UI |
| feat-006 | ✅ Done | agent | Security 2.0: Universal I/O Guard + Boundary Enforcement |
| feat-007 | 📋 Planned | cross-cutting | SIEM Extensions: dashboard, basic response actions, search, notifications, export |
| feat-008 | ✅ Done | security tooling | Promptfoo Red Team Scan: app-level LLM vulnerability scan через локальный Python provider |
| feat-009 | ✅ Done | agent | Многофайловые скиллы (load_skill file param) + перенос скилла tech-article-writing |
| feat-010 | ✅ Done | cross-cutting | Генерация изображений: OpenRouter Image API, artifact_blobs, media endpoint, живой ImageViewer |
| feat-011 | 🚧 In Progress | agent | Продуктовые субагенты v1: subagent-as-tool, реестр в agent.yaml, judge + web-research (+ADR) |
| feat-012 | 🚧 In Progress | cross-cutting | Skill-scoped user context: Store namespace, tools, REST, секция в /settings |

## Параллелизация

```
feat-003 (Agent Config: 3 tracks) ── feat-004 (Security) ─┬─ feat-005 (SIEM Core) ── feat-007 (SIEM Extensions)
                                                          └─ feat-006 (Security 2.0) ── feat-008 (Promptfoo Red Team)
feat-001 (Chat UX) ── когда будет время ─────────────────────────────────────────────────────────────────────
```

- **feat-003** — первый приоритет. Три трека проектируются параллельно (Track A: Langfuse+Model, Track B: Memory, Track C: User MCP), реализуются вместе
- **feat-004** — после feat-003 (security проектируется по финальной поверхности атаки)
- **feat-005** — после feat-004 (строится поверх security-событий Security 1.0; forward compatible с Security 2.0)
- **feat-006** — после feat-004, параллельно с feat-005, не блокирует и не блокируется (разные scope: SIEM = aggregation/correlation events, Security 2.0 = расширение защиты на новые I/O границы графа)
- **feat-007** — после feat-005; продуктовые улучшения поверх SIEM Core (dashboard, basic ban, search, notifications, export)
- **feat-008** — после feat-006; scanner/tooling итерация поверх уже реализованного security perimeter. Не меняет production API, проверяет существующий backend contour через Promptfoo + local Python provider
- **feat-009…feat-012** — трек «извлечение активов discovery-спайка» (Фаза 5a → продукт), итерации независимы друг от друга и идут в любом порядке; рекомендованный порядок по ценности для догфудинга: 009 (скилл доступен) → 010 (без картинок статья через продукт не начнётся) → 011 (judge-проходы скилла) → 012 (профиль голоса появится только после первой статьи)
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

**Статус:** ✅ Done
**Scope:** cross-cutting (Backend + Frontend)
**After:** feat-004

#### Из backlog

- **P2** Security Event Pipeline — unified subsystem for collecting, storing, and correlating security events from all sources (auth, rate limiter, security guard/Langfuse). structlog processor as integration point. Correlation engine (background asyncio task) with SQL rules by time window + grouping (IP, user_id). Result: `security_events` + `security_alerts` tables in PostgreSQL, REST API + React page for monitoring. *(cross: Backend, Frontend)*

#### Definition of Done

Декомпозиция на 4 трека для последовательной реализации в одной ветке. DoD проверяется агентом-тестировщиком через `test-cases.md`.

**T1 — Vocabulary + Contracts + Producer:**
- [x] `doc/tech/security-events.md` создан: полный vocabulary `event_type`, форма `metadata` per type, обязательность `identifiers`
- [x] `packages/siem-contracts/` собран как uv-workspace member: `SecurityEvent` (Pydantic), `Literal[...]` event_type, `SecurityEventIdentifiers`
- [x] structlog processor строит `SecurityEvent` из `logger.*(security_event=True, ...)` + `contextvars`; identifiers подмешиваются автоматически (HTTP middleware: `ip` / `request_id` / `user_agent_hash`; auth dep: `user_id` / `session_id`; chat route: `thread_id` / `project_id`)
- [x] Producer'ы (`SecurityGuard`, auth-handlers, rate limiter) пишут события через canonical `event_type`; existing log-вызовы рефакторятся
- [x] Publisher loop публикует события в Redis Stream `security.events`; видно через `redis-cli XREAD`

**T2 — SIEM service skeleton + ingestion:**
- [x] siem-service в `docker-compose.yml` с собственной PostgreSQL БД и миграциями (`siem_events` с `UNIQUE event_id`, индексы по timestamp / event_type)
- [x] Subscriber: XREADGROUP → Pydantic-валидация → INSERT с дедупом → XACK; pending list переживает рестарт
- [x] Минимальный REST `GET /security/events`: pagination + фильтры (event_type, severity, time range)
- [x] Producer-сайд → Redis → consumer → БД → API: end-to-end доставка одного события воспроизводима

**T3 — Correlation + Alerts + RBAC + полный API + Meta-log:**
- [x] Миграции `siem_alerts`, `correlation_rules`; идемпотентный seed правил при старте (≥4 baseline: brute_force_auth, injection_spike, targeted_user_attack, mass_suspicious)
- [x] Correlation engine: asyncio polling 10s; стратегии Threshold / Sequence / Aggregate; срабатывание создаёт алерт
- [x] Alert deduper: open-alert policy с возрастным лимитом 24h
- [x] Полный REST API: `GET /security/alerts`, `PATCH /security/alerts/:id` (acknowledge / resolve), CRUD `correlation_rules`
- [x] Identity: JWT HS256 общий с main app, claim `is_admin`; admin-only зависимость на всех security-endpoints
- [x] Промоут админа: миграция `users.is_admin` в main app + helper-скрипт `make grant-admin USER=<name>` (целевое действие оператора, без автоматического seed на старте)
- [x] Meta-log: PATCH alerts эмитит `siem.alert.acknowledged` / `siem.alert.resolved` через тот же producer-pipeline

**T4 — Frontend + Integration + ADRs:**
- [x] React страница `/security` (lazy chunk + RBAC guard): три view (events / alerts / rules) с фильтрами и пагинацией
- [x] Все UI labels на русском
- ⚠️ E2E через UI: админ логинится, видит события и алерты, может acknowledge / resolve, видит срабатывания correlation rules — *deferred: docker-compose port conflict при live XADD → siem-service; ручная проверка архитектором*
- [x] ADR-018..021 проверены и актуализированы под фактическую реализацию

**Cross-cutting:**
- [x] `make check` + `make check-fe` проходят
- [x] Миграции применяются на чистой БД (`docker-compose down -v` → `make docker-up-db` → `make migrate`) для main app и siem-service независимо
- [x] `siem-contracts` импортируется и main app, и siem-service из локального workspace источника
- [x] Forward compatibility: добавление нового `event_type` требует только расширения Literal-vocabulary в shared-пакете, без миграций SIEM
- [x] `architecture.md`, `observability.md`, `backend.md`, `conventions.md` актуализированы

#### Сознательно deferred

Dashboard & Metrics, basic response actions (ban IP/user), расширенный Search, Notifications, Export — вынесены в feat-007. Threat Intelligence, UEBA, SOAR automation, Log Forwarding, Compliance Frameworks — out of scope (not planned).

#### Документация

- [design-brief.md](iterations/post-mvp/feat-005-security-event-pipeline/design-brief.md) — Context, scope, функциональная карта, контракт событий, scope boundaries, 23 decisions (D1–D23), 14 contracts (C1–C14)
- [plan.md](iterations/post-mvp/feat-005-security-event-pipeline/plan.md) — Implementation plan: 4 фазы (T1-T4), decomposition по коммитам, verification gates
- [test-cases.md](iterations/post-mvp/feat-005-security-event-pipeline/test-cases.md) — 60 тестовых кейсов: Layer 0 (Automated) / Layer 1 (Component, по трекам T1-T4) / Layer 2 (Integration) / Layer 3 (E2E)
- [summary.md](iterations/post-mvp/feat-005-security-event-pipeline/summary.md) — Post-implementation summary: T1-T4 completion status, key decisions, tech debt, deviations
- [ADR-018](../tech/adr/ADR-018-siem-service-topology.md) — SIEM Service Topology: отдельный сервис, isolation, identity
- [ADR-019](../tech/adr/ADR-019-security-event-transport.md) — Security Event Transport: Redis Streams, at-least-once semantics
- [ADR-020](../tech/adr/ADR-020-security-event-contract.md) — Security Event Contract: Pydantic model, vocabulary, identifiers
- [ADR-021](../tech/adr/ADR-021-siem-correlation-engine.md) — SIEM Correlation Engine: polling, strategies, deduplication
- [security-events.md](../tech/security-events.md) — Vocabulary: полный каталог event_type по доменам, identifiers, metadata форма per type

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

---

### feat-008: Promptfoo Red Team Scan

**Цель:** добавить воспроизводимый app-level LLM vulnerability scan для LearnFlowAI через Promptfoo и локальный Python provider, без добавления scanner-only endpoints в production API.

**Статус:** ✅ Done
**Scope:** security tooling
**After:** feat-006

#### Triggered by

- Academic requirement: запустить LLM-specific vulnerability scanner для проекта и предоставить результаты.
- Scanner research: Garak подходит как baseline-концепт, но для LearnFlowAI требует отдельной обвязки из-за auth/project/chat/SSE lifecycle.
- Promptfoo выбран как более простой app-level scanner: Python provider, redteam plugins/strategies, OWASP mappings, HTML/JSON reports.

#### Scope

**MVP — Chat Runtime Scan:**
- `tools/security-scan/` с `promptfooconfig.yaml`, `learnflow_provider.py`, `.env.example`, `README.md`, `reports/`
- Python provider реализует lifecycle: login/register eval-user → create project → create chat per test → send message → read SSE → normalize output
- Promptfoo target указывает на `file://./learnflow_provider.py`
- Baseline plugins: `prompt-injection`, `indirect-prompt-injection`, `ascii-smuggling`, `hijacking`, `data-exfil`
- Baseline strategies: `basic`, один jailbreak strategy, один encoding strategy; тяжелые multi-turn strategies не входят в baseline
- Reports сохраняются в `tools/security-scan/reports/<run-id>/`: `report.html`, `results.json`, `provider-events.jsonl`, `summary.md`

**Optional — Add-Time Endpoints:**
- `custom_instructions_write`, `ks_write_rest`, `mcp_metadata` покрываются в первой итерации только если это реализуется без сложной orchestration и без изменений production API
- Если требуется fake malicious MCP server или сложный fixture state — выносится в future work

#### Definition of Done

- [x] `npx promptfoo@latest validate config` проходит в `tools/security-scan`
- [x] Provider standalone smoke отправляет benign prompt через существующий backend API и получает normal output
- [x] Provider standalone attack smoke получает или корректно фиксирует `security_block`
- [x] Small Promptfoo redteam run завершается без infrastructure errors (22 cases, 0 successful attacks, 16/22 passed, 6/22 errored по timeout/grader edge case)
- [x] `provider-events.jsonl` содержит `run_id`, Promptfoo metadata, `project_id`, `chat_id`, `blocked`, `block_reason`, latency
- [x] `report.html` (как `results.html`) и `results.json` сохранены в `reports/<run-id>/`
- [x] `summary.md` написан вручную: commit hash, Promptfoo version, plugins/strategies, totals, blocked/errors, findings, limitations
- [x] Raw reports проходят ручной review на секреты и коммитятся как audit evidence, если получены на dedicated eval-user и не содержат real user data
- [x] Production backend API не содержит `/scan` или других scanner-only endpoints

#### Сознательно deferred

- Garak integration через REST adapter / custom generator
- Reactivation archived `tools/eval-sec` как regression harness
- CI/nightly security scan
- Hydra / GOAT / Crescendo multi-turn strategies
- Dedicated malicious MCP fixture для robust `mcp_metadata` / `tool_result` indirect injection tests

#### Документация

- [design-brief.md](iterations/post-mvp/feat-008-promptfoo-redteam/design-brief.md) — Context, goals/non-goals, Promptfoo + Python provider decision, repository layout, provider contract, reporting policy, add-time endpoint boundary
- [plan.md](iterations/post-mvp/feat-008-promptfoo-redteam/plan.md) — Implementation plan: phasing, file map, hard-rules checklist, Makefile targets, verification
- [summary.md](iterations/post-mvp/feat-008-promptfoo-redteam/summary.md) — Post-implementation summary: deviations (D1-D6), tech debt, baseline run results, verification commands
- [reports/2026-05-10-baseline/summary.md](../../tools/security-scan/reports/2026-05-10-baseline/summary.md) — Baseline scan run report: 22 cases, 0 successful attacks, two-layer defense verification

### feat-009: Многофайловые скиллы + перенос tech-article-writing

**Цель:** продуктовый агент умеет пошагово подгружать модули многофайловых скиллов (progressive disclosure), первый такой скилл — `tech-article-writing` — перенесён из discovery-инициативы в `skills/`.

**Статус:** ✅ Done
**Scope:** agent

#### Triggered by

Discovery-спайк SOFA_Habr_Article (Фаза 5a): скилл обкатан на реальной опубликованной статье, Transfer Brief инициативы подтверждён автором. Текущий `load_skill` читает только `SKILL.md` — многофайловый скилл в продукте неработоспособен.

#### Критерии приёмки

- [ ] `load_skill(skill_name, file=None)`: без `file` — SKILL.md + автосписок файлов, с `file` — модуль; path traversal невозможен (тесты)
- [ ] `skills/tech-article-writing/` перенесён (без author-voice-данных), внутренние ссылки живые, нет ссылок на `~/.claude/`
- [ ] Скилл виден в Skills Index и полностью проходим агентом в режиме B

#### Документация

- [design-brief.md](iterations/post-mvp/feat-009-multifile-skills/design-brief.md) — контракт параметра `file`, правила переноса, отклонённые альтернативы
- [tracks/T1/plan.md](iterations/post-mvp/feat-009-multifile-skills/tracks/T1/plan.md) / [summary.md](iterations/post-mvp/feat-009-multifile-skills/tracks/T1/summary.md) / [test-cases.md](iterations/post-mvp/feat-009-multifile-skills/tracks/T1/test-cases.md) — расширение `load_skill` (параметр `file`, автосписок), решения и обоснования, тестовые кейсы
- [tracks/T2/plan.md](iterations/post-mvp/feat-009-multifile-skills/tracks/T2/plan.md) / [summary.md](iterations/post-mvp/feat-009-multifile-skills/tracks/T2/summary.md) / [test-cases.md](iterations/post-mvp/feat-009-multifile-skills/tracks/T2/test-cases.md) — перенос скилла `tech-article-writing`, сверка конвенции description, тестовые кейсы
- [review-a.md](iterations/post-mvp/feat-009-multifile-skills/review-a.md) — ревью качества кода (режим A)
- [review-b.md](iterations/post-mvp/feat-009-multifile-skills/review-b.md) — ревью соответствия конвенциям и doc-first (режим B)
- [harvest-proposals.md](iterations/post-mvp/feat-009-multifile-skills/harvest-proposals.md) — кандидаты в backlog/конвенции из итерации

### feat-010: Генерация изображений агентом

**Цель:** агент генерирует изображения по запросу пользователя: tool `generate_image` → OpenRouter Image API → артефакт `image` c бинарём в `artifact_blobs` → media endpoint → живой `ImageViewer`.

**Статус:** ✅ Done
**Scope:** cross-cutting (agent, backend, frontend)

#### Triggered by

Backlog P2 «Генерация изображений агентом»; подтверждено discovery-спайком — без генерации изображений подготовка статей через продукт не начнётся (блокер догфудинга 5b).

#### Критерии приёмки

- [x] `generate_image(prompt, title, aspect_ratio?, resolution?)`: артефакт + блоб пишутся одной транзакцией, SSE `artifact_created` приходит (маппер расширен на `generate_image`), generation-observation с `cost_details` из `usage.cost` уходит в Langfuse
- [x] `GET /projects/{pid}/artifacts/{id}/media` отдаёт бинарь с корректным mime под JWT-auth и `Cache-Control: private, immutable`
- [x] `ImageViewer` показывает реальную картинку (fetch с JWT → objectURL), состояния загрузки/404, caption = prompt, скачивание .png; ветка `image` выведена из-под `SHOW_GROUP_B_STUBS`
- [x] Карточка image-артефакта в ленте с превью (то же изображение с media-endpoint); плейсхолдер на время генерации по `tool_start`/`tool_end` (только фронт, протокол не меняется)
- [x] Миграция `artifact_blobs` через autogenerate; доступ за `BlobStorage`-протоколом (PG-реализация конструируется вокруг session)
- [x] Секция `image` в `agent.yaml` (`model` + `params`), дефолт — `google/gemini-3.1-flash-image`

#### Документация

- [design-brief.md](iterations/post-mvp/feat-010-image-generation/design-brief.md) — архитектура end-to-end, модель и параметры генерации, учёт стоимости, отклонённые альтернативы хранения/отдачи, границы scope
- [mockups/image-artifacts.html](iterations/post-mvp/feat-010-image-generation/mockups/image-artifacts.html) — интерактивный UI-референс: карточка с превью, плейсхолдер генерации, состояния вьюера (открывать локально)
- [tracks/T1/plan.md](iterations/post-mvp/feat-010-image-generation/tracks/T1/plan.md) / [summary.md](iterations/post-mvp/feat-010-image-generation/tracks/T1/summary.md) / [test-cases.md](iterations/post-mvp/feat-010-image-generation/tracks/T1/test-cases.md) — backend + agent: `artifact_blobs`, `BlobStorage`/`PgBlobStorage`, media endpoint, tool `generate_image`, расширение SSE-маппера, Langfuse cost-учёт; решения и обоснования, тестовые кейсы
- [tracks/T2/plan.md](iterations/post-mvp/feat-010-image-generation/tracks/T2/plan.md) / [summary.md](iterations/post-mvp/feat-010-image-generation/tracks/T2/summary.md) / [test-cases.md](iterations/post-mvp/feat-010-image-generation/tracks/T2/test-cases.md) — frontend: media-fetch, живой `ImageViewer`, превью в `ArtifactCard`, плейсхолдер генерации; решения и обоснования, тестовые кейсы
- [review-a.md](iterations/post-mvp/feat-010-image-generation/review-a.md) — ревью качества кода (режим A)
- [review-b.md](iterations/post-mvp/feat-010-image-generation/review-b.md) — ревью соответствия конвенциям и doc-first (режим B)
- [harvest-proposals.md](iterations/post-mvp/feat-010-image-generation/harvest-proposals.md) — кандидаты в backlog/конвенции из итерации
- [ADR-027: Хранение и отдача бинарных данных артефактов](../tech/adr/ADR-027-artifact-blob-storage.md) — `artifact_blobs` в PostgreSQL за `BlobStorage`-протоколом vs S3/файловая система/base64; authenticated media endpoint с immutable-кэшем

### feat-011: Продуктовые субагенты v1

**Цель:** механика субагентов по паттерну subagent-as-tool: реестр спек в `agent.yaml`, SubagentRunner, tool `run_subagent(agent_type, task, input_artifact_ids?)`, типы `judge` (чистый контекст), `web-research` (firecrawl-toolset), `general-purpose`. Архитектурное решение фиксируется ADR внутри итерации.

**Статус:** 🚧 In Progress
**Scope:** agent

#### Triggered by

Backlog P2 «Продуктовые субагенты» + discovery-спайк: judge-проходы скилла `tech-article-writing` (анти-слоп, cold-reader) требуют независимого агента со «свежими глазами» и не требуют инструментов; для web-research инструменты уже есть (built-in firecrawl MCP) — прежняя блокировка «после web search / sandbox» снята полностью.

#### Критерии приёмки

- [ ] ADR: паттерн, отклонённые альтернативы (supervisor/swarm/deepagents, generic-tool, tool-per-role), sync v1 vs async v2, формат реестра, вход по референсу, security-политика (переиспользование checkpoint'ов внутри цикла)
- [ ] `run_subagent("judge", task, input_artifact_ids)` возвращает вердикт; вход собирается только из task + артефактов (каждый в обёртке с id/title), история сессии не утекает (тест); любой чужой/несуществующий id → ошибка tool целиком (без частичного входа), граф не падает
- [ ] Реестр в `agent.yaml`; description инструмента собирается из реестра на старте; невалидный тип → ошибка со списком; неизвестное имя tool в спеке → ошибка старта
- [ ] `web-research`: firecrawl-toolset, внутри цикла работают проверки TOOL_RESULT/TOOL_CALL_ARG (redact-семантика), `recursion_limit`; user-installed MCP в субагентов не попадают
- [ ] Промпты субагентов — в Langfuse-контуре (`prompts.yaml` + seed + file fallback); модель — дефолт `subagents.llm` + per-spec override
- [ ] `persistence: none|inherit` в спеке (v1 — none); запуски видны в Langfuse вложенными span'ами
- [ ] Токены субагента не рисуются в чат и не попадают в `full_response` (фильтр по тегу)
- [ ] Judge-проходы `SKILL.md` обновлены: черновик → `create_artifact` → id судье

#### Документация

- [design-brief.md](iterations/post-mvp/feat-011-subagents-v1/design-brief.md) — паттерн, слоистость Runner/Spec/tool, вход по артефакт-референсу, tools-механика с переиспользованием guard, промпт-контур через PromptProvider, изоляция токенов в стриме, обоснование sync v1, persistence-режимы

### feat-012: Skill-scoped user context

**Цель:** per-user контекст, привязанный к скиллу: namespace `("user", uid, "skill_context", <skill>)`, доменные tools, индекс при `load_skill`, REST CRUD с security-checkpoint, секция «Контекст скиллов» на `/settings`. Первый потребитель — профиль авторского голоса `tech-article-writing`.

**Статус:** 🚧 In Progress
**Scope:** cross-cutting (agent, backend, frontend)

#### Triggered by

Transfer Brief инициативы (задание T2): README скилла требует per-user хранилище профиля вне кода скилла. Обобщено архитектором до механизма для любого скилла.

#### Критерии приёмки

- [ ] Tools `get/save/delete_skill_context`; изоляция по user_id и skill_name (тесты)
- [ ] `load_skill` дописывает индекс контекста пользователя для загружаемого скилла (только key + description)
- [ ] REST CRUD `/users/me/skill-contexts/...`; PUT — через новый checkpoint SecurityGuard (инъекция → 422)
- [ ] Секция на `/settings` по мокапу: группировка по скиллу, Markdown-превью, правка raw, удаление, бейдж «скилла нет в библиотеке», пустое состояние
- [ ] Данные переживают удаление скилла из библиотеки; доставка в модель при этом прекращается

#### Документация

- [design-brief.md](iterations/post-mvp/feat-012-skill-context/design-brief.md) — модель хранения, доставка через load_skill, REST, безопасность, отклонённые альтернативы
- [mockups/settings-skill-context.html](iterations/post-mvp/feat-012-skill-context/mockups/settings-skill-context.html) — интерактивный UI-референс (открывать локально)
