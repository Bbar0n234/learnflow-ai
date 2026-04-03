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
| feat-003 | 📋 Planned | cross-cutting | Runtime agent configuration: model switching + prompt versioning |
| feat-004 | 📋 Planned | cross-cutting | Custom instructions |
| feat-005 | 📋 Planned | agent/backend | Prompt injection protection |

## Параллелизация

```
feat-005 (Security) ──────────────────────────────────
feat-003 (Agent Config) ── feat-004 (Custom Instr.) ──
feat-001 (Chat UX) ── когда будет время ──────────────
```

- **feat-005 || feat-003** — разный scope (security vs config), параллелизуемы
- **feat-004** — после feat-003 (расширяет config, пересекается по UI)
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

**Цель:** runtime-конфигурация агента: смена модели без перезапуска сервиса + управление промптами и их версионирование.

**Статус:** 📋 Planned
**Scope:** cross-cutting (Agent + Backend + Frontend)

#### Из backlog

- **P1** Смена модели без перезапуска сервиса (runtime model switching) *(cross: Backend, Frontend)*
- **P2** Версионирование промптов — управление версиями system prompt, откат к предыдущим *(cross: Agent, Backend)*

---

### feat-004: Custom Instructions

**Цель:** кастомные инструкции на уровне пользователя, проекта и чата.

**Статус:** 📋 Planned
**Scope:** cross-cutting (Agent + Backend + Frontend)
**After:** feat-003

#### Из backlog

- **P2** Кастомные инструкции — на уровне пользователя, проекта и чата (помимо Knowledge Sphere) *(cross: Backend, Frontend)*

---

### feat-005: Prompt Injection Protection

**Цель:** базовая MVP-защита от prompt injection (direct + indirect).

**Статус:** 📋 Planned
**Scope:** agent/backend
**Параллельно с:** feat-003

#### Из backlog

- **P1** Prompt injection protection — MVP-защита от direct/indirect PI. Threat model и blue-team strategy проработаны (`doc/security/`), реализации нет *(cross: Backend)*
