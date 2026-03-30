# Implementation Plan: feat-002 — Agent Observability & Tooling

## Context

Итерация feat-002 из [tasklist-post-mvp.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-002-agent-obs/doc/tasks/tasklist-post-mvp.md). Цель — улучшение observability агента и конфигурации инструментов. Три задачи из backlog:

1. **[P1] Reasoning tokens → Langfuse** — reasoning text в Langfuse для отладки поведения модели
2. **[P2] OpenRouter pricing → Langfuse** — программная инициализация model definitions с pricing
3. **[P2] MCP Firecrawl tool filtering** — allowlist инструментов по MCP-серверам

Scope: agent/backend. Параллельно с fix-001 (frontend), нулевой конфликт.

### Референсы

- [design-brief.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-002-agent-obs/doc/tasks/iterations/post-mvp/feat-002-agent-obs/design-brief.md) — экспериментальные данные, проверенный код, точки изменения
- [workflow.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-002-agent-obs/doc/workflow.md) — жизненный цикл итерации
- [conventions.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-002-agent-obs/doc/tech/conventions.md) — git flow, code quality, logging
- [backend.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-002-agent-obs/doc/tech/backend.md) — layered architecture, module structure
- [ADR-010](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-002-agent-obs/doc/tech/adr/ADR-010-langfuse-observability.md) — Langfuse strategy
- [ADR-007](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-002-agent-obs/doc/tech/adr/ADR-007-mcp-external-tools.md) — MCP external tools

### Верификация API (быстро меняющиеся библиотеки)

| Библиотека | Версия | Проверено | Результат |
|-----------|--------|-----------|-----------|
| `langchain-openai` | 1.1.11 | `_create_chat_result`, `_convert_chunk_to_generation_chunk` сигнатуры | Совпадает с design brief |
| `langfuse` | 4.0.1 | `models.create()`, `models.list()`, `CallbackHandler` additional_kwargs | Совпадает с design brief |
| `langchain-mcp-adapters` | 0.2.1 | `get_tools(server_name=)` | Совпадает с design brief |

`CallbackHandler` (строки 989-990): `additional_kwargs` пробрасываются целиком в generation observation — reasoning text попадёт в Langfuse автоматически.

---

## Шаг 1: Reasoning tokens → Langfuse

### 1.1 Расширить `LLMConfig` — `backend/app/agent/config.py`

Добавить `extra_body` в `LLMConfig`:

```python
class LLMConfig(BaseModel):
    model: str
    extra_body: dict[str, Any] = {}
```

Импорт `Any` из `typing`.

### 1.2 Добавить `ReasoningChatOpenAI` — `backend/app/infra/llm.py`

Класс из design brief (проверенный код). Наследник `ChatOpenAI` с двумя override:
- `_create_chat_result()` — извлекает `reasoning` из non-streaming response
- `_convert_chunk_to_generation_chunk()` — извлекает `reasoning` из streaming chunks

Reasoning text сохраняется в `AIMessage.additional_kwargs["reasoning"]`.

### 1.3 Обновить фабрику `create_llm()` — `backend/app/infra/llm.py`

Выбор класса по наличию `include_reasoning` в `extra_body`:

```python
def create_llm(settings: Settings, agent_config: AgentConfig) -> BaseChatModel:
    extra_body = agent_config.llm.extra_body
    use_reasoning = extra_body.get("include_reasoning", False) if extra_body else False
    llm_class = ReasoningChatOpenAI if use_reasoning else ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": agent_config.llm.model,
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
    }
    if extra_body:
        kwargs["extra_body"] = extra_body

    return llm_class(**kwargs)  # type: ignore[call-arg]
```

### 1.4 Конфиг — `configs/agent.yaml`

```yaml
llm:
  model: "z-ai/glm-5"
  extra_body:
    include_reasoning: true
    reasoning:
      effort: low
```

### 1.5 `make check`

Прогнать ruff + mypy, исправить ошибки.

---

## Шаг 2: OpenRouter pricing → Langfuse

### 2.1 Модель конфигурации — `backend/app/agent/config.py`

Добавить `ModelDefinitionConfig` и поле `models` в `AgentConfig`:

```python
class ModelDefinitionConfig(BaseModel):
    name: str
    match_pattern: str
    unit: str = "TOKENS"
    input_price: float | None = None
    output_price: float | None = None
    total_price: float | None = None

class AgentConfig(BaseModel):
    llm: LLMConfig
    context: ContextConfig
    prompt: PromptConfig
    summarization: SummarizationConfig | None = None
    mcp_servers: dict[str, MCPServerConfig] = {}
    models: list[ModelDefinitionConfig] = []
```

### 2.2 Инициализация model definitions — `backend/app/infra/langfuse.py`

Новая публичная функция `ensure_model_definitions()`. Паттерн аналогичен `_ensure_score_config()`:

```python
def ensure_model_definitions(models: list[ModelDefinitionConfig]) -> None:
    """Idempotently create Langfuse model definitions for cost tracking."""
    if not langfuse_enabled or not models:
        return
    langfuse = get_client()
    # ... check-then-create logic
```

Логика:
1. `langfuse.api.models.list(limit=100)` — получить существующие
2. Сравнить по `model_name` — пропустить уже существующие
3. `langfuse.api.models.create(...)` — создать отсутствующие

Не вызывается из `init_langfuse()`, т.к. конфиг моделей загружается позже.

### 2.3 Вызов из lifespan — `backend/app/main.py`

Добавить вызов `ensure_model_definitions()` после `load_agent_config()`:

```python
agent_config = load_agent_config()

try:
    ensure_model_definitions(agent_config.models)
except Exception:
    logger.warning("langfuse model definitions init failed", exc_info=True)
```

### 2.4 Конфиг — `configs/agent.yaml`

```yaml
models:
  - name: "z-ai/glm-5"
    match_pattern: "(?i)^z-ai/glm-5"
    unit: TOKENS
    input_price: 0.000001
    output_price: 0.0000032

  - name: "z-ai/glm-4.7-flash"
    match_pattern: "(?i)^z-ai/glm-4\\.7-flash"
    unit: TOKENS
    input_price: 0.000000125
    output_price: 0.0000005

  - name: "google/gemini-3.1-pro-preview"
    match_pattern: "(?i)^google/gemini-3\\.1-pro-preview"
    unit: TOKENS
    input_price: 0.000002
    output_price: 0.000012
```

### 2.5 `make check`

---

## Шаг 3: MCP Firecrawl tool filtering

### 3.1 Расширить `MCPServerConfig` — `backend/app/agent/config.py`

```python
class MCPServerConfig(BaseModel):
    transport: str
    url: str | None = None
    api_key_env: str | None = None
    command: str | None = None
    args: list[str] | None = None
    allowed_tools: list[str] = []
```

### 3.2 Per-server фильтрация — `backend/app/main.py`

Заменить текущий `mcp_client.get_tools()` на per-server фильтрацию:

```python
mcp_tools: list = []
try:
    mcp_client = create_mcp_client(agent_config.mcp_servers)
    if mcp_client is not None:
        for server_name, server_config in agent_config.mcp_servers.items():
            tools = await mcp_client.get_tools(server_name=server_name)
            if server_config.allowed_tools:
                allowed = set(server_config.allowed_tools)
                tools = [t for t in tools if t.name in allowed]
            mcp_tools.extend(tools)
        logger.info(
            "mcp tools loaded",
            tool_count=len(mcp_tools),
            server_count=len(agent_config.mcp_servers),
        )
except Exception:
    logger.warning(
        "mcp tools init failed, starting without external tools",
        exc_info=True,
    )
```

### 3.3 Конфиг — `configs/agent.yaml`

```yaml
mcp_servers:
  firecrawl:
    transport: http
    url: https://mcp.firecrawl.dev/v2/mcp
    api_key_env: FIRECRAWL_API_KEY
    allowed_tools:
      - firecrawl_scrape
      - firecrawl_search
```

### 3.4 `make check`

---

## Шаг 4: Финальная проверка

1. `make check` — ruff + mypy (CI gate)
2. Ручная верификация (запуск приложения):
   - Стартап: в логах видно `langfuse model definitions created` для новых моделей
   - Стартап: `mcp tools loaded, tool_count=2` (вместо 13+)
   - Отправить сообщение модели с reasoning → Langfuse trace содержит `additional_kwargs.reasoning`
   - Langfuse UI → Models: три модели с pricing
3. Просмотр Langfuse generation observation — убедиться, что reasoning text присутствует

---

## Шаг 5: Завершение итерации

1. Дождаться ревью и обратной связи от архитектора
2. После апрува — коммит и пуш
3. `summary.md` — отклонения от плана, принятые решения
4. Актуализация документации при необходимости

---

## Сводка изменений по файлам

| Файл | Шаг | Изменение |
|------|-----|-----------|
| `backend/app/agent/config.py` | 1,2,3 | `extra_body` в LLMConfig, `ModelDefinitionConfig`, `models` в AgentConfig, `allowed_tools` в MCPServerConfig |
| `backend/app/infra/llm.py` | 1 | Класс `ReasoningChatOpenAI`, обновление `create_llm()` |
| `backend/app/infra/langfuse.py` | 2 | Функция `ensure_model_definitions()` |
| `backend/app/main.py` | 2,3 | Вызов `ensure_model_definitions()`, per-server MCP tool filtering |
| `configs/agent.yaml` | 1,2,3 | `extra_body`, `models`, `allowed_tools` |

## Scope boundaries (из design brief)

**НЕ входит:**
- Стриминг reasoning text на фронтенд
- Кэширование reasoning в БД
- Автоматическая синхронизация pricing с OpenRouter API
- Prompt-based фильтрация MCP-инструментов
