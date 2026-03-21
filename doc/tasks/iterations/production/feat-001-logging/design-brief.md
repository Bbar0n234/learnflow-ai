# feat-001: Logging — Design Brief

Контекст реализации для implementation plan. Архитектурные решения: [ADR-009](../../../tech/adr/ADR-009-logging-strategy.md).

## Backend

### structlog + stdlib

- Централизованная инициализация: одна точка входа при старте приложения
- Двойной рендеринг: `human-readable` (dev) / `json` (prod), переключается через `configs/logging.yaml`
- Существующие 4 логгера (`main.py`, `graph.py`, `chat.py`, `mcp.py`) и ~8 вызовов — заменить на structlog API

### YAML-конфиг

Структура `configs/logging.yaml`:
- Формат вывода: `human-readable` | `json`
- Per-library overrides для шумных библиотек:
  - `httpx`, `httpcore` → `warning`
  - `sqlalchemy.engine` → `warning`
  - `asyncio` → `warning`
  - `uvicorn.access` → `info`

`LOG_LEVEL` из env имеет приоритет над всем. Дефолтный уровень — `info` по конвенции, в YAML не дублируется (single source of truth). В YAML нет поля `default_level`.

### Request ID

- FastAPI middleware генерирует UUID → `contextvars`
- structlog подхватывает автоматически — каждый лог в контексте запроса содержит `request_id`
- Ценно для LangGraph agent stream: несколько лог-событий на один HTTP-запрос

## Семантика уровней

После реализации — перенести в `conventions.md`.

### Принцип

- **INFO** — "что система делает": запрос пришёл → агент вызван → LLM ответил → ответ отправлен. Полная история без деталей.
- **DEBUG** — "почему она это делает": payload, промежуточные состояния, входы/выходы. Включается для расследования.

### Уровни

- **DEBUG** — детали для расследования (в production выключены по умолчанию): тела запросов/ответов (HTTP, LLM, MCP), промежуточное состояние графа агента, содержимое загруженных конфигов.
- **INFO** — значимые бизнес/операционные события: старт/остановка приложения, агент вызван/завершил (факт + длительность), внешний вызов выполнен (LLM, MCP — факт + длительность, не содержимое), ключевые бизнес-операции (чат создан, проект создан).
- **WARNING** — система справилась, но что-то было не так: fallback сработал (MCP tools не загрузились), retry (LLM rate limit), деградация (суммаризация упала → trim-only).
- **ERROR** — операция провалилась, пользователь пострадал: необработанное исключение, внешний сервис недоступен после retry, ответ не может быть сформирован.

### Привязка к компонентам

| Компонент | DEBUG | INFO | WARNING |
|-----------|-------|------|---------|
| FastAPI endpoints | request body, headers | — (access log от uvicorn) | — |
| Agent runner | state между нодами, prompt | "agent invoked", "agent completed" | fallback на trim-only |
| LLM calls | prompt + response | "LLM call (model, duration, tokens)" | rate limit retry |
| MCP tools | tool input/output | "MCP tool called: {name}" | tool init failed |
| Services | входные параметры | "chat created", "project created" | — |
| DB/Repository | — (sqlalchemy логирует) | — | — |
| Startup | loaded config details | "App started", "N MCP tools loaded" | config fallback |

### Антипаттерны

- INFO на входе/выходе каждой функции — шум, INFO только для бизнес-событий
- WARNING для ожидаемого поведения ("пользователь не создал проект" — это нормальный flow, не warning)
- ERROR для клиентских ошибок (невалидный JSON → 422, не error в логах)

## Frontend

### Logger-обёртка

- `import.meta.env.DEV` → debug/info включены; prod → только warn/error
- Отдельная `VITE_LOG_LEVEL` не нужна: Vite env vars — compile-time (вшиваются в бандл при `npm run build`), `DEV`/`PROD` из Vite достаточно
- Заменить 3 существующих `console.error` на `logger.error` (`client.ts`, `useAgentStream.ts` ×2)

### Error Boundary

- Оборачивает корень приложения
- Показывает fallback UI вместо белого экрана при непойманной ошибке рендера
- Логирует ошибку через `logger.error`

## Docker

### Log rotation

- `json-file` driver, `max-size: 10m`, `max-file: 3` (30MB total на сервис)
- Обоснование размеров: при ~100 req/day (pet-проект) → ~30KB/day → 10MB ≈ 300 дней; при ~1000 req/day → ~300KB/day → ~30 дней. Запас достаточный.
- Настроить для обоих сервисов: `app` и `db`

### Персистенция логов

- Логи живут пока живёт контейнер (`docker compose restart` — сохраняются; `docker compose down` + `up` — удаляются с пересозданием контейнера)
- Volume mount для логов не делаем — Docker-only подход
- Долговременная персистенция (Loki, ELK) — не в scope v1.1

## Scope boundaries (не v1.1)

- JSON-формат по умолчанию (механизм заложен, не активирован)
- Remote error reporting (Sentry) на фронтенде
- Персистенция логов на хост / агрегатор логов
- Динамический log level на фронтенде в runtime
