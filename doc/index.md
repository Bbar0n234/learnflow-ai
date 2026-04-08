# Навигация по документации

## Структура

```
doc/
├── idea.md          # Что и зачем
├── vision.md        # Техническое видение
├── index.md         # ← вы здесь
│
├── product/         # Продуктовая документация
├── tech/            # Техническая документация
│   ├── backend.md       # Бэкенд: слои, API, persistence
│   ├── frontend.md      # Фронтенд: экраны, компоненты, state
│   ├── auth.md          # Аутентификация (кросс-сервисная)
│   ├── streaming.md     # SSE-стриминг (кросс-сервисный)
│   ├── agent-runtime.md # Agent Runtime: граф, tools, skills, context
│   ├── knowledge-sphere.md # Knowledge Sphere: хранение, tools, UI
│   ├── user-memory.md   # User Memory: instructions, agent memory, персонализация
│   ├── prompt-management.md # Prompt Management: Langfuse, dev/prod, seed/sync
│   ├── observability.md # Observability: Langfuse, трейсинг, feedback
│   ├── security.md      # Security: input guard, hardening, canary token
│   ├── conventions.md   # Git, code quality, naming, logging
│   └── adr/             # Architecture Decision Records
├── research/        # Исследования: технологические ресёрчи, анализ подходов
├── security/        # Модель угроз, защита и атака
└── tasks/           # Задачи и итерации
```

## Ключевые документы

- [idea.md](idea.md) — проблема, ICP, JTBD, конкурентное преимущество, границы продукта
- [vision.md](vision.md) — принципы, системная архитектура, стек, MVP-критерии
- [backlog.md](backlog.md) — входящий поток задач из опытной эксплуатации

## Техническая документация

**Сервисы:**
- [tech/backend.md](tech/backend.md) — слоистая архитектура, API endpoints, schemas, persistence, configuration
- [tech/frontend.md](tech/frontend.md) — экраны, компоненты, state management, API-интеграция

**Кросс-сервисные концепты:**
- [tech/auth.md](tech/auth.md) — JWT + refresh token rotation, rate limiting, frontend interceptor
- [tech/streaming.md](tech/streaming.md) — SSE-протокол, event types, cancellation, frontend consumption
- [tech/agent-runtime.md](tech/agent-runtime.md) — LangGraph граф, context engineering, tools, skills, MCP
- [tech/knowledge-sphere.md](tech/knowledge-sphere.md) — проектная память, storage model, fuzzy patch, REST API
- [tech/user-memory.md](tech/user-memory.md) — custom instructions, agent memory, кросс-проектная персонализация
- [tech/prompt-management.md](tech/prompt-management.md) — Langfuse prompts, dev/prod separation, seed/sync, fallback
- [tech/observability.md](tech/observability.md) — Langfuse трейсинг, cost tracking, user feedback loop
- [tech/security.md](tech/security.md) — Prompt injection protection: input guard, hardening, canary token

**Соглашения и решения:**
- [tech/conventions.md](tech/conventions.md) — git flow, code quality, naming, logging, Docker
- [tech/adr/](tech/adr/) — архитектурные решения (формат: `ADR-NNN-название.md`)

## Другие разделы

- [product/](product/) — сценарии использования, scope по версиям
- [research/](research/) — технологические ресёрчи, deep-dives, анализ подходов (информируют будущие фичи)
- [security/](security/) — threat model, red/blue team research (архитектура реализации — [tech/security.md](tech/security.md))
- [tasks/](tasks/) — задачи и итерации
