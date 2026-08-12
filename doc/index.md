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
│   ├── siem-service.md  # SIEM-сервис: pipeline, корреляция, alerts API
│   ├── frontend.md      # Фронтенд: экраны, компоненты, state
│   ├── design-system.md # Дизайн-система: токены, темизация, бренд, иллюстрации
│   ├── auth.md          # Аутентификация (кросс-сервисная)
│   ├── streaming.md     # SSE-стриминг (кросс-сервисный)
│   ├── agent-runtime.md # Agent Runtime: граф, tools, skills, context
│   ├── knowledge-sphere.md # Knowledge Sphere: хранение, tools, UI
│   ├── user-memory.md   # User Memory: instructions, agent memory, skill context, персонализация
│   ├── prompt-management.md # Prompt Management: Langfuse, dev/prod, seed/sync
│   ├── observability.md # Observability: Langfuse, трейсинг, feedback
│   ├── conventions.md   # Git, code quality, naming, logging, documentation (ядро)
│   ├── conventions/     # Доменные конвенции: db, api, agent, frontend, testing, review
│   ├── skill-map.md     # Карта скиллов: принципы, роли, отклонённые, пробелы
│   ├── sofa-pipeline.md # SOFA: двунаправленная петля знаний, author gate, реестр
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
- [tech/siem-service.md](tech/siem-service.md) — SIEM-сервис: топология, event pipeline, correlation engine, alerts REST API
- [tech/frontend.md](tech/frontend.md) — экраны, компоненты, state management, API-интеграция
- [tech/design-system.md](tech/design-system.md) — визуальный язык «Чернила / Электрик»: токены, типографика, темизация, бренд-примитивы, иллюстрации, error UX

**Кросс-сервисные концепты:**
- [tech/auth.md](tech/auth.md) — JWT + refresh token rotation, rate limiting, frontend interceptor
- [tech/streaming.md](tech/streaming.md) — SSE-протокол, event types, cancellation, frontend consumption
- [tech/agent-runtime.md](tech/agent-runtime.md) — LangGraph граф, context engineering, tools, skills, MCP
- [tech/knowledge-sphere.md](tech/knowledge-sphere.md) — проектная память, storage model, fuzzy patch, REST API
- [tech/user-memory.md](tech/user-memory.md) — custom instructions, agent memory, skill context, персонализация агента
- [tech/prompt-management.md](tech/prompt-management.md) — Langfuse prompts, dev/prod separation, seed/sync, fallback
- [tech/observability.md](tech/observability.md) — Langfuse трейсинг, cost tracking, user feedback loop, SIEM pipeline
- [tech/security-events.md](tech/security-events.md) — Security Event Pipeline vocabulary: event_type каталог, identifiers, metadata per type
- [security/architecture.md](security/architecture.md) — Защита агента: восемь I/O checkpoints, детекторы, trust boundaries, block mechanics, SIEM observability

**Соглашения и решения:**
- [tech/conventions.md](tech/conventions.md) — ядро: git flow, code quality, naming, logging, error handling, Docker, documentation, типизация
- [tech/conventions/](tech/conventions/) — доменные конвенции: [db.md](tech/conventions/db.md) (схема, миграции, сессии), [api.md](tech/conventions/api.md) (FastAPI, REST), [agent.md](tech/conventions/agent.md) (runtime, reasoning, prompt naming), [frontend.md](tech/conventions/frontend.md) (FSD, состояние), [testing.md](tech/conventions/testing.md) (модель тестов, фейки, тестовая БД), [review.md](tech/conventions/review.md) (гейт PR, ретро-контур, классификация артефактов)
- [tech/arch-checker.md](tech/arch-checker.md) — реестр архитектурных инвариантов и детерминированные проверки (import-linter, AST-ассерты, eslint-boundaries)
- [tech/skill-map.md](tech/skill-map.md) — карта скиллов: принципы отбора, роли, отклонённые, пробелы, отложенные кандидаты
- [tech/sofa-pipeline.md](tech/sofa-pipeline.md) — SOFA-пайплайн: двунаправленная петля знаний (consume / produce / write-back), context bus, author gate, реестр публикаций
- [tech/adr/](tech/adr/) — архитектурные решения (формат: `ADR-NNN-название.md`)
  - [ADR-018: SIEM Service Topology](tech/adr/ADR-018-siem-service-topology.md) — отдельный backend-сервис, isolation, identity
  - [ADR-019: Security Event Transport](tech/adr/ADR-019-security-event-transport.md) — Redis Streams, at-least-once semantics, bounded queue
  - [ADR-020: Security Event Contract](tech/adr/ADR-020-security-event-contract.md) — Pydantic SecurityEvent, vocabulary, identifiers, forward compatibility
  - [ADR-021: SIEM Correlation Engine](tech/adr/ADR-021-siem-correlation-engine.md) — polling-based engine, three strategies, open-alert deduplication, 24h age limit
  - [ADR-025: Conventions per Domain](tech/adr/ADR-025-conventions-per-domain.md) — дробление conventions.md: ядро + доменные файлы, progressive disclosure
  - [ADR-029: Operational Kill-Switches](tech/adr/ADR-029-operational-kill-switches.md) — один env-тумблер на подсистему (`LLM_DEFENSE_ENABLED`, `SIEM_ENABLED`), гранулярность остаётся в существующих конфигах
  - [ADR-030: Per-Call Tool Result Guard](tech/adr/ADR-030-per-call-tool-result-guard.md) — проверка и отчёт о результате инструмента повызовно, внутри узла `tools`: правдивость ленты против стоимости классификатора
  - [ADR-031: OAuth Identity Model](tech/adr/ADR-031-oauth-identity-model.md) — отдельная таблица `oauth_accounts`, запрет авто-линковки по email, nullable `password_hash`

**Setup manuals:**
- [tech/setup/codex-cloud.md](tech/setup/codex-cloud.md) — настройка ChatGPT Codex Environment для cloud-сессий
- [tech/setup/production.md](tech/setup/production.md) — nginx-периметр прод-VM, инвариант доверия, режимы `CLIENT_IP_SOURCE`, ручной runbook перед деплоем

## Другие разделы

- [product/](product/) — roadmap (фазы и треки), сценарии использования
- [content/](content/) — черновики технического контента: статьи, доклады (work-in-progress, не проектная документация)
  - [content/sofa/](content/sofa/index.md) — реестр публикаций на Stack Overflow for Agents: опубликованные посты + статистика
- [research/](research/) — технологические ресёрчи, deep-dives, анализ подходов (информируют будущие фичи)
  - [research/aidd-meta-harness.md](research/aidd-meta-harness.md) — рамка будущего анализа и системного улучшения AIDD harness по артефактам, Claude Code history и реальным outcomes
- [reference/](reference/) — референс-материалы: паттерны и справочники по доменам
  - [reference/model-selection.md](reference/model-selection.md) — методика выбора LLM по классам (основной/лёгкий/guard), критерии отбора, карта ролей и одобренных альтернатив
- [security/](security/) — threat model и архитектура защиты ([architecture.md](security/architecture.md))
- [tasks/](tasks/) — задачи и итерации
