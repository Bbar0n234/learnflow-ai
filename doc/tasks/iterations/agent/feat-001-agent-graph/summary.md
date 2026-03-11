# Post-Implementation Summary: agent/feat-001 — Agent Graph Skeleton

## Результат

Реализовано полностью. Минимально работающий агент: LangGraph StateGraph с ReAct loop, PostgreSQL persistence (Checkpointer + Store), LangGraphAgentRunner со streaming через SSE.

## Отклонения от плана

### Mypy-совместимость типов

План содержал упрощённые type annotations. При прохождении `make check` потребовались уточнения:

| Что | Решение |
|-----|---------|
| `build_graph() -> StateGraph` | → `StateGraph[Any, Any, Any, Any]` (generic с 4 параметрами) |
| `compile_graph(builder, *, ...)` | Добавлены полные type annotations, return type `CompiledStateGraph[Any, Any, Any, Any]` |
| `LangGraphAgentRunner.__init__(graph)` | `graph: Any` (CompiledStateGraph generic слишком verbose для Protocol-совместимости) |
| `create_checkpointer/store` return type | `from_conn_string()` возвращает `_AsyncGeneratorContextManager`, не сам Saver/Store. Тип: `AbstractAsyncContextManager[AsyncPostgresSaver]` |
| `ChatOpenAI(model=..., api_key=..., base_url=...)` | langchain-openai stubs не экспортируют kwargs → `type: ignore[call-arg]` |
| `[system] + trimmed` | Несовместимость `list[SystemMessage] + list[BaseMessage]` → `[system, *trimmed]` |

### Дополнительная dev-зависимость

`types-pyyaml` добавлен в `[dependency-groups] dev` для mypy-совместимости PyYAML. В плане не упоминался.

### Модель в configs/agent.yaml

План: `anthropic/claude-sonnet-4`. Изменено на `google/gemini-3-flash-preview` по запросу архитектора для тестирования. Модель меняется в YAML без изменения кода — конфигурация работает как задумано.

## Верификация

Все критерии приёмки пройдены:

| Критерий | Статус |
|----------|--------|
| Граф компилируется с checkpointer и store | ✅ |
| AgentRunner.stream() возвращает TextChunk и Done events | ✅ |
| Persistence: повторный запрос видит историю | ✅ |
| get_history() возвращает сообщения из checkpointer | ✅ |
| `make check` (ruff check + ruff format + mypy) | ✅ |

## Решения, принятые при реализации

- **`from __future__ import annotations`** в `graph.py` и `runner.py` — для forward references и упрощения generic-аннотаций.
- **`metadata` → `_metadata`** в runner.py — ruff B007 (unused loop variable). Метаданные stream_mode="messages" пока не используются, но доступны для будущих итераций.

## Актуализация документации

- `doc/tech/langgraph-reference.md` — добавлена секция "Runtime и context_schema" (актуальный API), RunnableConfig/InjectedStore помечены как legacy.
- Остальная проектная документация (`backend.md`, ADR) не требует изменений — реализация соответствует архитектуре.

## Артефакты

### Новые файлы
- `configs/agent.yaml` — agent-level config
- `backend/app/agent/config.py` — AgentConfig Pydantic model + loader
- `backend/app/agent/graph.py` — StateGraph, AgentContext, build/compile
- `backend/app/agent/runner.py` — LangGraphAgentRunner
- `backend/app/infra/llm.py` — create_llm() factory
- `backend/app/infra/langgraph.py` — create_checkpointer/store factories

### Изменённые файлы
- `backend/pyproject.toml` — зависимости (langgraph, langchain-openai, langchain-core, pyyaml, psycopg +pool)
- `backend/app/config.py` — llm_api_key, llm_base_url, langgraph_database_url
- `backend/app/main.py` — lifespan с LangGraph persistence + agent graph
- `backend/app/api/deps.py` — wiring через app.state.agent_runner
- `backend/app/agent/__init__.py` — re-export LangGraphAgentRunner
- `.env.example`, `.env.local.example` — LLM_API_KEY, LLM_BASE_URL
- `doc/tech/langgraph-reference.md` — секция Runtime/context_schema
