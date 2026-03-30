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
| fix-001 | 📋 Planned | frontend | Frontend bug fixes (4 элемента backlog) |
| feat-001 | 📋 Planned | cross-cutting | Chat UX: auto title + thinking indicator |
| feat-002 | ✅ Done | agent/backend | Agent observability & tooling |
| feat-003 | 📋 Planned | cross-cutting | Runtime model switching |
| feat-004 | 📋 Planned | cross-cutting | Custom instructions |

## Параллелизация

```
              ┌── fix-001 (Frontend Bugs) ──┐
              │                              ├── feat-001 (Chat UX)── feat-003 (Model Switch)
Триаж ────────┤                              │                                │
              │                              │                                ↓
              └── feat-002 (Agent Obs.) ─────┘                       feat-004 (Custom Instr.)
```

- **Волна 1:** fix-001 || feat-002 (frontend vs agent/backend — нулевой конфликт)
- **Волна 2:** feat-001 (после fix-001, т.к. пересекается по chat-компонентам)
- **Волна 3-4:** feat-003 → feat-004 (cross-cutting, последовательно)

## Итерации

### fix-001: Frontend Bug Fixes

**Цель:** исправить накопившиеся UX-баги фронтенда.

**Статус:** 📋 Planned
**Scope:** frontend
**Параллельно с:** feat-002

#### Из backlog

- **P1** Feedback иконки (like/dislike) пропадают при перезагрузке страницы
- **P1** Артефакт-карточки пропадают из истории чата (есть в tab Artifacts, нет в сообщениях)
- **P2** Дублирование сообщения пользователя при переключении вкладки во время стриминга
- **P2** Hover states: курсор не меняется на кнопках, непонятно что кликабельно

---

### feat-001: Chat UX — Auto Title + Thinking Indicator

**Цель:** переработка UX чата: поле ввода для первого сообщения (не title), автогенерация title моделью, индикатор рассуждения.

**Статус:** 📋 Planned
**Scope:** cross-cutting (Frontend + Backend)
**Blocked by:** fix-001

#### Из backlog

- **P1** Chat input: поле ввода должно быть для первого сообщения, не для title. Title auto-generated моделью *(cross: Backend)*
- **P2** Индикатор "модель рассуждает" до начала стриминга текста *(cross: Backend)*

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

### feat-003: Runtime Model Switching

**Цель:** смена модели без перезапуска сервиса.

**Статус:** 📋 Planned
**Scope:** cross-cutting (Agent + Backend + Frontend)
**Blocked by:** feat-001

#### Из backlog

- **P1** Смена модели без перезапуска сервиса (runtime model switching) *(cross: Backend, Frontend)*

---

### feat-004: Custom Instructions

**Цель:** кастомные инструкции на уровне пользователя, проекта и чата.

**Статус:** 📋 Planned
**Scope:** cross-cutting (Agent + Backend + Frontend)
**Blocked by:** feat-003

#### Из backlog

- **P2** Кастомные инструкции — на уровне пользователя, проекта и чата (помимо Knowledge Sphere) *(cross: Backend, Frontend)*
