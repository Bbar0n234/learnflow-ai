# Фаза B: Детальная архитектура

## Цель

Проработать каждый компонент до уровня модулей, классов, интерфейсов, методов. Сформировать контекст, достаточный для начала реализации по AIDD.

**Фаза проекта:**

```
Фаза A: Documentation Transfer       ✅ done
     ↓
Фаза B: Detailed Architecture        ← СЕЙЧАС
  Модули, интерфейсы, классы, контракты
     ↓
Фаза C: Infrastructure Setup
  uv, ruff, mypy, pre-commit, Docker, Makefile
     ↓
Фаза D: Implementation (Итерации 1-4)
```

## Принципы

- **Сверху вниз:** сервис → модули → классы → интерфейсы
- **AIDD:** уровень интерфейсов и контрактов, не кода (см. [workflow.md](../workflow.md))
- **Монолитно, потом дробим:** начинаем с одного документа на сервис. Если секция разрастается — выносим в отдельный файл и ставим ссылку.
- **Outline-first:** для каждого документа outline → ревью архитектора → апрув → полный документ

## Документы и статус

| # | Документ | Что содержит | Статус |
|---|----------|-------------|--------|
| 1 | `doc/index.md` | Навигация по документации: структура, что где лежит, ссылки | ✅ done |
| 2 | `doc/workflow.md` | Процесс: AIDD, итерации, работа с агентом, жизненный цикл итерации | ✅ done |
| 3 | `doc/tech/conventions.md` | Технические соглашения: git (ветки, коммиты, flow), code quality (ruff, mypy), структура проекта (uv workspace), Docker, Makefile, тестирование, именование | ✅ done |
| 4 | `doc/tech/backend.md` | Весь бэкенд: API (endpoints, schemas, SSE), Agent (core, memory, skills, tools), Persistence (сущности, связи) | ✅ done |
| 5 | `doc/tech/frontend.md` | Фронтенд: React UI, chat-интерфейс, state management, API-интеграция, SSE | 📋 todo |

### Backend: секции к детализации

| # | Секция | Что раскрыть | Статус |
|---|--------|-------------|--------|
| 4.0 | Layered Architecture | Слои, правила вызовов, гибридная persistence | ✅ done |
| 4.1 | Module Structure | Карта Python-пакетов, ответственности | ✅ done |
| 4.2 | API Schemas | Pydantic request/response модели для каждого endpoint | ✅ done |
| 4.3 | SSE Streaming Protocol | Event types, data payload, lifecycle стрима | ✅ done |
| 4.4 | Agent Graph | LangGraph nodes, edges, State-модель, переходы | ✅ done |
| 4.5 | Error Handling | Стратегия ошибок: LLM сбой, таймаут, cancel, SSE disconnect | ✅ done |
| 4.6 | Configuration | Settings-класс, env vars, конфигурируемые параметры | ✅ done |

## Порядок работы

Последовательность: 1 → 5.

- **index.md, workflow.md, conventions.md** — независимы, можно делать параллельно или последовательно
- **backend.md** — ядро, от него зависит frontend
- **frontend.md** — зависит от backend (API-контракты)

Для каждого документа:
1. Outline → ревью архитектора → апрув
2. Написание полного документа
3. Отметка статуса в таблице выше

## Правило дробления

Если секция внутри документа разрастается (300+ строк), выносим в отдельный файл и ставим ссылку. Например, если Agent внутри backend.md станет слишком большим → `doc/tech/agent.md`.
