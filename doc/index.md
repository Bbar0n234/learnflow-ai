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
│   ├── conventions.md   # Git, code quality, naming, logging, documentation
│   ├── skill-map.md     # Карта скиллов: принципы, роли, отклонённые, пробелы
│   ├── setup/            # Инструкции настройки dev/cloud окружений
│   └── adr/             # Architecture Decision Records
├── content/         # Черновики технического контента: статьи, доклады
├── research/        # Исследования: технологические ресёрчи, анализ подходов
├── reference/       # Референс-материалы: паттерны, справочники по доменам
├── security/        # Модель угроз и архитектура защиты
└── tasks/           # Задачи и итерации
```

## Ключевые документы

- [idea.md](idea.md) — проблема, ICP, JTBD, конкурентное преимущество, границы продукта
- [vision.md](vision.md) — принципы, системная архитектура, стек, MVP-критерии
- [product/roadmap.md](product/roadmap.md) — фазы и треки развития проекта, что сделано и что впереди
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
- [tech/observability.md](tech/observability.md) — Langfuse трейсинг, cost tracking, user feedback loop, SIEM pipeline
- [tech/security-events.md](tech/security-events.md) — Security Event Pipeline vocabulary: event_type каталог, identifiers, metadata per type
- [security/architecture.md](security/architecture.md) — Защита агента: семь I/O checkpoints, детекторы, trust boundaries, block mechanics, SIEM observability

**Соглашения и решения:**
- [tech/conventions.md](tech/conventions.md) — git flow, code quality, naming, logging, Docker
- [tech/skill-map.md](tech/skill-map.md) — карта скиллов: принципы отбора, роли, отклонённые, пробелы, отложенные кандидаты
- [tech/adr/](tech/adr/) — архитектурные решения (формат: `ADR-NNN-название.md`)
  - [ADR-018: SIEM Service Topology](tech/adr/ADR-018-siem-service-topology.md) — отдельный backend-сервис, isolation, identity
  - [ADR-019: Security Event Transport](tech/adr/ADR-019-security-event-transport.md) — Redis Streams, at-least-once semantics, bounded queue
  - [ADR-020: Security Event Contract](tech/adr/ADR-020-security-event-contract.md) — Pydantic SecurityEvent, vocabulary, identifiers, forward compatibility
  - [ADR-021: SIEM Correlation Engine](tech/adr/ADR-021-siem-correlation-engine.md) — polling-based engine, three strategies, open-alert deduplication, 24h age limit

**Setup manuals:**
- [tech/setup/codex-cloud.md](tech/setup/codex-cloud.md) — настройка ChatGPT Codex Environment для cloud-сессий

## Другие разделы

- [product/](product/) — roadmap (фазы и треки), сценарии использования
- [content/](content/) — черновики технического контента: статьи, доклады (work-in-progress, не проектная документация)
- [research/](research/) — технологические ресёрчи, deep-dives, анализ подходов (информируют будущие фичи)
- [reference/](reference/) — референс-материалы: паттерны и справочники по доменам
- [security/](security/) — threat model и архитектура защиты ([architecture.md](security/architecture.md))
- [tasks/](tasks/) — задачи и итерации
