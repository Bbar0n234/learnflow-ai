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
| feat-003 | 📋 Planned | cross-cutting | Runtime agent configuration (3 tracks: Langfuse+Model, Memory, User MCP) |
| feat-004 | 📋 Planned | agent/backend | Prompt injection protection |

## Параллелизация

```
feat-003 (Agent Config: 3 tracks) ── feat-004 (Security) ──
feat-001 (Chat UX) ── когда будет время ────────────────────
```

- **feat-003** — первый приоритет. Три трека проектируются параллельно (Track A: Langfuse+Model, Track B: Memory, Track C: User MCP), реализуются вместе
- **feat-004** — после feat-003 (security проектируется по финальной поверхности атаки)
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

**Статус:** 📋 Planned (проектирование завершено)
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
- [ADR-013](../tech/adr/ADR-013-model-settings-storage.md) — Per-Scope Settings Storage: typed tables vs polymorphic vs JSONB
- [ADR-014](../tech/adr/ADR-014-dynamic-model-resolution.md) — Graph Factory: per-request graph build (model + tools)
- [ADR-015](../tech/adr/ADR-015-unified-memory-backend.md) — LangGraph Store как unified memory backend (Track B)
- [ADR-016](../tech/adr/ADR-016-per-scope-mcp-servers.md) — Per-Scope MCP Servers: storage, encryption, additive merge (Track C)

---

### feat-004: Prompt Injection Protection

**Цель:** базовая MVP-защита от prompt injection (direct + indirect).

**Статус:** 📋 Planned
**Scope:** agent/backend
**After:** feat-003

#### Из backlog

- **P1** Prompt injection protection — MVP-защита от direct/indirect PI. Threat model и blue-team strategy проработаны (`doc/security/`), реализации нет *(cross: Backend)*
