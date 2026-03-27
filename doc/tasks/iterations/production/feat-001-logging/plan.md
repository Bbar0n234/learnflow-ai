# Implementation Plan: feat-001 Logging

## Context

MVP (v1) завершён. Текущее состояние логирования: 4 разрозненных `logging.getLogger(__name__)` без централизованной конфигурации (main.py, graph.py, chat.py, mcp.py), ~5 вызовов (2 info/warning в main.py, 1 warning в graph.py, 1 warning в chat.py, 1 warning в mcp.py). На фронтенде — 3 `console.error` без уровней и Error Boundary. Docker — без log rotation.

Цель: управляемое логирование на backend и frontend. Фундамент для observability (feat-003: Langfuse).

## Референсы

| Документ | Роль |
|----------|------|
| [ADR-009](doc/tech/adr/ADR-009-logging-strategy.md) | Архитектурные решения |
| [Design Brief](doc/tasks/iterations/production/feat-001-logging/design-brief.md) | Детальный контекст реализации |
| [tasklist-production.md](doc/tasks/tasklist-production.md) | Состав работ и критерии приёмки |
| [conventions.md](doc/tech/conventions.md) | Git flow, code quality, Docker, именование |
| [workflow.md](doc/workflow.md) | Итерация, жизненный цикл |
| [structlog 25.5.0 docs](https://www.structlog.org/en/stable/) | API (верифицировано через firecrawl) |

## Верификация API быстро меняющихся инструментов

**structlog 25.5.0** (stable, проверено через firecrawl → structlog.org):
- `structlog.configure(processors=[...], wrapper_class=..., logger_factory=..., cache_logger_on_first_use=True)`
- `structlog.stdlib.ProcessorFormatter` — unified formatting для structlog + stdlib loggers
- `structlog.stdlib.ProcessorFormatter.wrap_for_formatter` — последний процессор в structlog chain
- `structlog.stdlib.ProcessorFormatter.remove_processors_meta` — убирает `_record` и `_from_structlog`
- `structlog.contextvars.merge_contextvars` — первый процессор в chain (подтягивает contextvars)
- `structlog.contextvars.bind_contextvars()` / `clear_contextvars()` — для request_id
- `structlog.stdlib.BoundLogger` — wrapper_class для stdlib интеграции
- `structlog.stdlib.LoggerFactory()` — logger_factory
- `structlog.dev.ConsoleRenderer(colors=True/False)` — human-readable
- `structlog.processors.JSONRenderer()` — JSON формат
- `structlog.stdlib.add_log_level` / `structlog.stdlib.add_logger_name` — стандартные процессоры
- `structlog.get_logger()` — возвращает lazy proxy, конфигурация подхватывается при первом вызове

Langfuse SDK v4, GitHub Actions — не в scope feat-001.

## Архитектурный подход

**structlog поверх stdlib через ProcessorFormatter** (подход "Rendering using structlog-based formatters within logging" из документации structlog). Это даёт единый формат вывода для structlog loggers (наш код) и stdlib loggers (uvicorn, sqlalchemy, httpx).

Схема потока:
```
structlog.get_logger().info(...)  ──→ structlog processors ──→ ProcessorFormatter.wrap_for_formatter ──→ logging.Logger ──→ ProcessorFormatter.format() ──→ stdout
logging.getLogger().info(...)     ──→ logging.Logger ──→ ProcessorFormatter.format() (foreign_pre_chain) ──→ stdout
```

## Шаги реализации

### Шаг 1: Зависимость structlog

**Файл:** `backend/pyproject.toml`

Добавить `structlog>=25.0` в dependencies. Запустить `uv sync`.

### Шаг 2: YAML-конфиг логирования

**Файл (новый):** `configs/logging.yaml`

```yaml
# Output format: human-readable (dev) | json (prod)
format: human-readable

# Per-library log level overrides (noisy libraries)
overrides:
  httpx: warning
  httpcore: warning
  sqlalchemy.engine: warning
  asyncio: warning
  uvicorn.access: info
```

Примечание: `default_level` в YAML нет — дефолт `info` по конвенции, управляется через `LOG_LEVEL` env var (single source of truth, см. design brief).

Dockerfile уже копирует `configs/` (`COPY configs/ /app/configs/`).

### Шаг 3: LOG_LEVEL в Settings

**Файл:** `backend/app/config.py`

Добавить поле `log_level: str = "info"` в `Settings`. Значение приходит из env var `LOG_LEVEL`.

### Шаг 4: Модуль инициализации логирования

**Файл (новый):** `backend/app/infra/logging.py`

Единственная точка входа для настройки логирования. Функция `setup_logging(log_level: str, config_path: Path)`:

1. Загрузить `configs/logging.yaml` (формат, per-library overrides)
2. Определить renderer по полю `format`:
   - `human-readable` → `structlog.dev.ConsoleRenderer()`
   - `json` → `structlog.processors.JSONRenderer()`
3. Собрать shared_processors: `merge_contextvars` (первый — чтобы contextvars попали в event dict до остальных процессоров), `add_log_level`, `add_logger_name`, `TimeStamper(fmt="iso")`
4. `structlog.configure(processors=shared_processors + [wrap_for_formatter], wrapper_class=BoundLogger, logger_factory=LoggerFactory(), cache_logger_on_first_use=True)`
5. `logging.config.dictConfig(...)`:
   - root logger: level из `log_level` param, handler → stdout с `ProcessorFormatter`
   - `ProcessorFormatter`: `foreign_pre_chain=shared_processors`, `processors=[remove_processors_meta, renderer]`
   - per-library overrides из YAML → `loggers: { "httpx": {"level": "WARNING"}, ... }`

### Шаг 5: Request ID middleware

**Файл:** `backend/app/main.py` (модификация `create_app()`)

Новый async middleware:
```python
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    structlog.contextvars.clear_contextvars()
    request_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(request_id=request_id)
    response = await call_next(request)
    return response
```

Примечание по FastAPI + contextvars: structlog docs предупреждают о гибридных sync/async приложениях на Starlette. Наш случай безопасен — middleware, handlers, services, agent runner все async. Contextvars корректно propagate внутри одной asyncio task.

### Шаг 6: Вызов setup_logging в lifespan

**Файл:** `backend/app/main.py`

В начале `lifespan()` (до любых операций):
```python
setup_logging(
    log_level=settings.log_level,
    config_path=Path(__file__).resolve().parents[2] / "configs" / "logging.yaml",
)
```

### Шаг 7: Замена существующих logging-вызовов на structlog

Заменить `import logging` + `logger = logging.getLogger(__name__)` → `import structlog` + `logger = structlog.get_logger()` в 4 файлах:

| Файл | Текущие вызовы | Что меняется |
|------|---------------|--------------|
| `backend/app/main.py:29` | `logger = logging.getLogger(__name__)` | → `structlog.get_logger()` |
| `backend/app/agent/graph.py:20` | `logger = logging.getLogger(__name__)` | → `structlog.get_logger()` |
| `backend/app/services/chat.py:14` | `logger = logging.getLogger(__name__)` | → `structlog.get_logger()` |
| `backend/app/infra/mcp.py:15` | `logger = logging.getLogger(__name__)` | → `structlog.get_logger()` |

Все 5 существующих вызовов `logger.info(...)` / `logger.warning(...)` переписать на structlog keyword-args стиль:
- `logger.info("Loaded %d MCP tools from %d server(s)", len(mcp_tools), len(agent_config.mcp_servers))` → `logger.info("mcp tools loaded", tool_count=len(mcp_tools), server_count=len(agent_config.mcp_servers))`
- printf-style → keyword args (structlog convention)

### Шаг 8: Добавление новых log-вызовов по design brief

Добавить INFO/DEBUG/WARNING вызовы по таблице "Привязка к компонентам" из design brief. Строго по семантике уровней, без over-logging:

- **main.py (startup):** `logger.info("app started")`, `logger.info("mcp tools loaded", ...)` (уже есть), `logger.debug("loaded config", ...)` при загрузке конфигов
- **agent/runner.py:** `logger.info("agent invoked", thread_id=..., project_id=...)`, `logger.info("agent completed", thread_id=..., duration_ms=...)`, `logger.warning("agent stream error", ...)` на except
- **agent/graph.py:** уже есть warning на summarization fallback. Добавить `logger.info("llm call", model=..., duration_ms=..., tokens=...)` после LLM-вызова, `logger.debug("agent state", ...)` с промежуточным состоянием
- **services/chat.py:** `logger.info("chat created", ...)` при создании, warning уже есть
- **infra/mcp.py:** warning уже есть

Конкретные log-вызовы будут уточнены при реализации по design brief таблице.

### Шаг 9: .env.example / .env.local.example

**Файлы:** `.env.example`, `.env.local.example`

Добавить:
```
# Logging
LOG_LEVEL=info
```

### Шаг 10: Frontend logger-обёртка

**Файл (новый):** `frontend/src/shared/lib/logger.ts`

```typescript
type LogLevel = "debug" | "info" | "warn" | "error";

const LEVELS: Record<LogLevel, number> = { debug: 0, info: 1, warn: 2, error: 3 };
const MIN_LEVEL: LogLevel = import.meta.env.DEV ? "debug" : "warn";

export const logger = {
  debug: (...args: unknown[]) => shouldLog("debug") && console.debug(...args),
  info:  (...args: unknown[]) => shouldLog("info")  && console.info(...args),
  warn:  (...args: unknown[]) => shouldLog("warn")  && console.warn(...args),
  error: (...args: unknown[]) => shouldLog("error") && console.error(...args),
};

function shouldLog(level: LogLevel): boolean {
  return LEVELS[level] >= LEVELS[MIN_LEVEL];
}
```

`import.meta.env.DEV` — compile-time из Vite, отдельная `VITE_LOG_LEVEL` не нужна (ADR-009).

### Шаг 11: Error Boundary

**Файл (новый):** `frontend/src/app/components/ErrorBoundary.tsx`

React class component (Error Boundary требует class component):
- `componentDidCatch` → `logger.error("render error", error, errorInfo)`
- `render()` → fallback UI при ошибке (сообщение + кнопка "обновить страницу")
- Оборачивает корень приложения

**Файл (модификация):** `frontend/src/App.tsx`

```tsx
export function App() {
  return (
    <ErrorBoundary>
      <AuthGate>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
      </AuthGate>
    </ErrorBoundary>
  );
}
```

### Шаг 12: Замена console.error → logger.error на фронтенде

| Файл | Строка | Текущее | Новое |
|------|--------|---------|-------|
| `frontend/src/shared/api/client.ts:28` | `console.error("[API Error]", ...)` | → `logger.error("[API Error]", ...)` |
| `frontend/src/features/chat/hooks/useAgentStream.ts:134` | `console.error("[SSE stream error]", err)` | → `logger.error("[SSE stream error]", err)` |
| `frontend/src/features/chat/hooks/useAgentStream.ts:152` | `console.error("[cancel error]", err)` | → `logger.error("[cancel error]", err)` |

### Шаг 13: Docker log rotation

**Файл:** `docker-compose.yml`

Добавить logging config для обоих сервисов (`app` и `db`):

```yaml
logging:
  driver: json-file
  options:
    max-size: "10m"
    max-file: "3"
```

30MB total на сервис. Обоснование размеров — в design brief.

### Шаг 14: Актуализация документации

1. **`doc/tech/backend.md`** — добавить секцию Logging: structlog setup, YAML-конфиг, request ID middleware, семантика уровней (или ссылка на conventions.md)
2. **`doc/tech/frontend.md`** — добавить секцию Logging: logger-обёртка, Error Boundary
3. **`doc/tech/conventions.md`** — добавить секцию Logging Conventions: семантика уровней (из design brief, раздел "Семантика уровней"), антипаттерны. Design brief говорит: "После реализации — перенести в conventions.md"
4. **`CLAUDE.md`** — секция Logging Conventions: семантика уровней, антипаттерны (по составу работ)

### Шаг 15: Проверки качества

```bash
make check      # ruff + mypy
make lint-fe    # ESLint
```

### Шаг 16: Верификация по критериям приёмки

| Критерий | Как проверить |
|----------|--------------|
| `make dev`: логи human-readable с цветами | Запустить `make dev`, отправить запрос, смотреть вывод |
| `LOG_LEVEL=debug`: видны debug-сообщения | `LOG_LEVEL=debug make dev` |
| `LOG_LEVEL=warning`: info подавлен | `LOG_LEVEL=warning make dev`, убедиться что info не выводится |
| Шумные библиотеки не мусорят | Убедиться что httpx/sqlalchemy/asyncio не выводят info |
| request_id во всех логах HTTP-запроса | Отправить запрос, проверить что все лог-строки содержат request_id |
| Frontend dev: debug/info видны | `make dev-fe`, открыть консоль браузера |
| Frontend prod: только warn/error | `npm run build && npm run preview`, проверить консоль |
| Error Boundary: fallback UI | Намеренно сломать рендер компонента, проверить fallback |
| Docker log rotation | `docker compose up -d`, проверить `docker inspect` на logging config |

### Шаг 17: Post-implementation summary + ревью

1. Написать `summary.md` в `doc/tasks/iterations/production/feat-001-logging/`
2. Обновить статус итерации в `tasklist-production.md`
3. **Дождаться ревью и обратной связи от архитектора перед коммитом и пушем**

## Файлы для модификации

| Файл | Действие |
|------|----------|
| `backend/pyproject.toml` | Добавить structlog |
| `backend/app/config.py` | Добавить log_level |
| `backend/app/main.py` | setup_logging, request_id middleware, replace logger |
| `backend/app/agent/graph.py` | Replace logger, добавить log-вызовы |
| `backend/app/agent/runner.py` | Добавить log-вызовы |
| `backend/app/services/chat.py` | Replace logger |
| `backend/app/infra/mcp.py` | Replace logger |
| `docker-compose.yml` | Log rotation |
| `.env.example` | LOG_LEVEL |
| `.env.local.example` | LOG_LEVEL |
| `frontend/src/App.tsx` | ErrorBoundary wrapper |
| `frontend/src/shared/api/client.ts` | console.error → logger.error |
| `frontend/src/features/chat/hooks/useAgentStream.ts` | console.error → logger.error |
| `doc/tech/backend.md` | Секция Logging |
| `doc/tech/frontend.md` | Секция Logging |
| `doc/tech/conventions.md` | Секция Logging Conventions |
| `CLAUDE.md` | Секция Logging Conventions |

## Новые файлы

| Файл | Назначение |
|------|-----------|
| `configs/logging.yaml` | Конфиг логирования |
| `backend/app/infra/logging.py` | Инициализация structlog + stdlib |
| `frontend/src/shared/lib/logger.ts` | Logger-обёртка |
| `frontend/src/app/components/ErrorBoundary.tsx` | Error Boundary |
