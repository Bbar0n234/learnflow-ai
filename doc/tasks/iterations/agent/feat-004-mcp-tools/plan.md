# Implementation Plan: agent/feat-004 — MCP External Tools

## Context

Агенту нужны внешние инструменты (web search, URL reading, crawling). По ADR-007 external tools подключаются через MCP Client — конкретный MCP-сервер конфигурируется, не кодируется. Default MVP: Firecrawl MCP (search + scrape + crawl в одном сервере). Адаптер: `langchain-mcp-adapters` — конвертирует MCP tools в стандартные `BaseTool`, которые живут в одном `ToolNode` вместе с internal tools.

### Референсы

- Таск-лист: `doc/tasks/tasklist-agent.md` (feat-004)
- Архитектура: `doc/tech/backend.md` (Tools → External MCP, Module Structure → infra, Configuration)
- ADR: `doc/tech/adr/ADR-007-mcp-external-tools.md`
- Conventions: `doc/tech/conventions.md`
- Workflow: `doc/workflow.md`
- LangGraph reference: `doc/tech/langgraph-reference.md`

### Решения архитектора

- **MCP config** → `configs/agent.yaml` (секция `mcp_servers`, генерик итерация, API-ключи через env vars)
- **Startup failure** → graceful degradation (warning в лог, старт без MCP tools)

### Проверенный API (inspect + docs, март 2026)

- **langchain-mcp-adapters v0.2.1**: `MultiServerMCPClient(connections: dict)`, `await client.get_tools() -> list[BaseTool]`
- Transport `"http"` — алиас `streamable_http` (проверено в исходниках `create_session`)
- Connection types: `StdioConnection`, `SSEConnection`, `StreamableHttpConnection`, `WebsocketConnection`
- Client **stateless by default** — каждый tool call создаёт свежую сессию, не требует lifecycle management
- **Firecrawl MCP remote**: URL `https://mcp.firecrawl.dev/v2/mcp`, auth через header `Authorization: Bearer {API_KEY}`

---

## Шаг 0 — Ветка

```bash
git fetch origin && git checkout -b feat/004-mcp-tools origin/develop
```

Ветка согласно conventions.md: `feat/004-mcp-tools` (из tasklist).

---

## Шаг 1 — Зависимость `langchain-mcp-adapters`

**Файл:** `backend/pyproject.toml`

Добавить в `dependencies`:
```
"langchain-mcp-adapters>=0.2",
```

Затем `cd backend && uv sync`.

---

## Шаг 2 — MCP конфигурация в `configs/agent.yaml`

**Файл:** `configs/agent.yaml`

Добавить секцию `mcp_servers`:
```yaml
mcp_servers:
  firecrawl:
    transport: http
    url: https://mcp.firecrawl.dev/v2/mcp
    api_key_env: FIRECRAWL_API_KEY
```

Формат: каждый сервер — ключ с параметрами:
- `transport` — тип подключения (`http`, `sse`, `stdio`)
- `url` — endpoint MCP-сервера (для http/sse)
- `api_key_env` — имя env var с API-ключом (инжектируется в `Authorization: Bearer` header)
- Опционально: `command`, `args` (для stdio)

---

## Шаг 3 — Расширение AgentConfig

**Файл:** `backend/app/agent/config.py`

Добавить модель `MCPServerConfig` и расширить `AgentConfig`:

```python
class MCPServerConfig(BaseModel):
    transport: str  # "http", "sse", "stdio"
    url: str | None = None
    api_key_env: str | None = None
    command: str | None = None
    args: list[str] | None = None

class AgentConfig(BaseModel):
    llm: LLMConfig
    context: ContextConfig
    prompt: PromptConfig
    mcp_servers: dict[str, MCPServerConfig] = {}  # default: пустой (нет MCP)
```

`mcp_servers` с дефолтом `{}` — обратная совместимость с конфигами без MCP.

---

## Шаг 4 — MCP client factory

**Новый файл:** `backend/app/infra/mcp.py`

Функция `create_mcp_client()` — строит `MultiServerMCPClient` из `AgentConfig.mcp_servers`:

```python
import logging
import os

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.agent.config import MCPServerConfig

logger = logging.getLogger(__name__)


def build_mcp_connections(
    servers: dict[str, MCPServerConfig],
) -> dict[str, dict[str, object]]:
    """Convert MCPServerConfig dict → MultiServerMCPClient connections dict."""
    connections: dict[str, dict[str, object]] = {}
    for name, cfg in servers.items():
        conn: dict[str, object] = {"transport": cfg.transport}
        if cfg.url:
            conn["url"] = cfg.url
        if cfg.command:
            conn["command"] = cfg.command
        if cfg.args:
            conn["args"] = cfg.args
        # Inject API key as Authorization header
        if cfg.api_key_env:
            api_key = os.environ.get(cfg.api_key_env, "")
            if api_key:
                conn["headers"] = {"Authorization": f"Bearer {api_key}"}
            else:
                logger.warning(
                    "MCP server '%s': env var '%s' not set, skipping auth header",
                    name, cfg.api_key_env,
                )
        connections[name] = conn
    return connections


def create_mcp_client(
    servers: dict[str, MCPServerConfig],
) -> MultiServerMCPClient | None:
    """Create MultiServerMCPClient from config. Returns None if no servers configured."""
    if not servers:
        return None
    connections = build_mcp_connections(servers)
    return MultiServerMCPClient(connections)
```

Переиспользуемая логика: `build_mcp_connections` отделена от создания клиента для тестируемости.

---

## Шаг 5 — Wiring в main.py (graceful degradation)

**Файл:** `backend/app/main.py`

В `lifespan()` после создания `llm` и `all_tools`:

```python
from app.infra.mcp import create_mcp_client

# MCP external tools (graceful degradation — весь блок в try/except)
mcp_tools: list = []
try:
    mcp_client = create_mcp_client(agent_config.mcp_servers)
    if mcp_client is not None:
        mcp_tools = await mcp_client.get_tools()
        logger.info("Loaded %d MCP tools from %d server(s)",
                     len(mcp_tools), len(agent_config.mcp_servers))
except Exception:
    logger.warning("Failed to initialize MCP tools, starting without external tools",
                   exc_info=True)

all_tools = ks_tools + [load_skill, create_artifact] + mcp_tools
```

Добавить `import logging` и `logger = logging.getLogger(__name__)` в начало файла.

Граф строится как раньше — `build_graph(model=llm, tools=all_tools, ...)`. MCP tools — стандартные `BaseTool`, они прозрачно попадают в `ToolNode` и `bind_tools`.

---

## Шаг 6 — Env vars

**Файлы:** `.env.example`, `.env.local.example`

Добавить:
```
FIRECRAWL_API_KEY=your-firecrawl-api-key-here
```

---

## Шаг 7 — Обновление `infra/__init__.py`

**Файл:** `backend/app/infra/__init__.py`

Если в нём есть re-exports — добавить `create_mcp_client`. Если пустой — оставить как есть (import напрямую из `app.infra.mcp`).

---

## Файлы: сводка изменений

| Файл | Действие |
|------|----------|
| `backend/pyproject.toml` | Добавить зависимость `langchain-mcp-adapters>=0.2` |
| `configs/agent.yaml` | Добавить секцию `mcp_servers` |
| `backend/app/agent/config.py` | Добавить `MCPServerConfig`, расширить `AgentConfig` |
| `backend/app/infra/mcp.py` | **Новый файл** — `build_mcp_connections`, `create_mcp_client` |
| `backend/app/main.py` | Wiring MCP tools с graceful degradation |
| `.env.example` | Добавить `FIRECRAWL_API_KEY` |
| `.env.local.example` | Добавить `FIRECRAWL_API_KEY` |

---

## Верификация

**Агент выполняет все проверки самостоятельно**, по порядку. E2E-тест с Firecrawl (кейс 3) — только после того как архитектор добавит `FIRECRAWL_API_KEY` в `.env`.

### Кейс 1. `make check`
Выполнить `make check` (ruff check + ruff format + mypy). Должен проходить без ошибок.

### Кейс 2. Обратная совместимость — старт без MCP
- Временно убрать/закомментировать секцию `mcp_servers` в `configs/agent.yaml`
- Запустить `make dev`, проверить `curl localhost:8000/health` → 200
- Убедиться, что в логах нет ошибок связанных с MCP
- Вернуть `mcp_servers` обратно

### Кейс 3. Graceful degradation — MCP в конфиге, но нет API key
- Убедиться, что `FIRECRAWL_API_KEY` **не установлен** в env
- Запустить `make dev`
- Проверить логи: должен быть warning (api_key_env not set / failed to load MCP tools), сервер стартует
- `curl localhost:8000/health` → 200

### Кейс 4. E2E с Firecrawl (выполняется после получения ключа от архитектора)
- Архитектор добавляет `FIRECRAWL_API_KEY=fc-...` в `.env`
- Запустить `make dev`
- Проверить логи: `Loaded N MCP tools from 1 server(s)`
- Отправить запрос агенту с задачей web search (curl/httpie POST /messages с контентом типа "найди информацию о...")
- Убедиться: SSE stream содержит `tool_start` / `tool_end` для MCP tool, агент возвращает результат поиска

### Чеклист acceptance criteria
- [ ] MCP client подключается к Firecrawl серверу при старте
- [ ] MCP tools доступны агенту наравне с internal tools
- [ ] Агент может выполнить web search через MCP tool и вернуть результат
- [ ] Смена MCP-провайдера не требует изменения кода (только config)
- [ ] `make lint && make type-check` проходят

---

## Финальный шаг

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.
