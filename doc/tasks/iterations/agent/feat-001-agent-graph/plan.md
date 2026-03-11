# Implementation Plan: agent/feat-001 — Agent Graph Skeleton

## Context

Итерация `agent/feat-001` — первая в скоупе Agent Runtime. Цель: минимально работающий агент — LangGraph-граф с ReAct loop, PostgreSQL persistence (Checkpointer + Store), AgentRunner со streaming. Пользователь может отправить сообщение и получить стримингом ответ LLM.

**Blocked by:** `backend-core/feat-001` — **снят** (все 5 backend-core итераций ✅ Done).

## Референсы

- **Таск-лист:** `doc/tasks/tasklist-agent.md` (feat-001)
- **Workflow:** `doc/workflow.md`
- **Conventions:** `doc/tech/conventions.md`
- **Архитектура:** `doc/tech/backend.md` (Agent Runtime, Module Structure, Persistence, SSE Protocol)
- **ADR-006:** `doc/tech/adr/ADR-006-custom-stategraph.md` (Custom StateGraph)
- **LangGraph Reference:** `doc/tech/langgraph-reference.md`

## Принятые решения (согласовано с архитектором)

| Вопрос | Решение |
|---|---|
| Runtime vs RunnableConfig | **Runtime + context_schema** с feat-001. `thread_id` в `configurable`, `project_id`/`user_id` в `Context` dataclass |
| LLM провайдер | **ChatOpenAI** (langchain-openai) через **OpenRouter** (OpenAI-compatible API) |
| Модель — env vs config | **YAML config** (`configs/agent.yaml`) для agent-level параметров. Settings — только infra (ключи, URL) |
| YAML формат | **Structured** (секции llm/context/prompt) + **Pydantic BaseModel** + PyYAML |
| YAML location | `configs/agent.yaml` — уровень репозитория |

## API валидация (быстро меняющиеся инструменты)

Проверено через MCP docs-langchain (11 марта 2026):

| Инструмент | Актуальный API |
|---|---|
| StateGraph, MessagesState | `from langgraph.graph import StateGraph, MessagesState, START, END` |
| ToolNode, tools_condition | `from langgraph.prebuilt import ToolNode, tools_condition` |
| Runtime | `from langgraph.runtime import Runtime` — в нодах custom StateGraph |
| AsyncPostgresSaver | `from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver` |
| AsyncPostgresStore | `from langgraph.store.postgres.aio import AsyncPostgresStore` |
| trim_messages | `from langchain_core.messages.utils import trim_messages, count_tokens_approximately` |
| ChatOpenAI | `from langchain_openai import ChatOpenAI` — с `base_url` для OpenRouter |

## Шаги реализации

### 0. Ветка

```bash
git fetch origin && git checkout -b feat/001-agent-graph origin/develop
```

### 1. Зависимости

**Файл:** `backend/pyproject.toml`

Добавить:
```
"langgraph>=0.4",
"langgraph-checkpoint-postgres>=2.0",
"langchain-openai>=0.3",
"langchain-core>=0.3",
"pyyaml>=6.0",
```

Изменить `psycopg[binary]` → `psycopg[binary,pool]` (LangGraph checkpoint-postgres использует psycopg connection pool).

После: `uv sync` для установки.

### 2. Agent YAML Config

**Новый файл:** `configs/agent.yaml`

```yaml
llm:
  model: "anthropic/claude-sonnet-4"

context:
  max_tokens: 100000

prompt:
  system: "You are a helpful AI learning assistant."
```

**Новый файл:** `backend/app/agent/config.py`

```python
import yaml
from pathlib import Path
from pydantic import BaseModel


class LLMConfig(BaseModel):
    model: str

class ContextConfig(BaseModel):
    max_tokens: int

class PromptConfig(BaseModel):
    system: str

class AgentConfig(BaseModel):
    llm: LLMConfig
    context: ContextConfig
    prompt: PromptConfig


def load_agent_config(path: Path | None = None) -> AgentConfig:
    if path is None:
        # configs/agent.yaml at repo root
        path = Path(__file__).resolve().parents[3] / "configs" / "agent.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return AgentConfig(**data)
```

- Pydantic BaseModel (не BaseSettings) — валидация, типизация, без env override
- Путь по умолчанию: `<repo_root>/configs/agent.yaml`
- `parents[3]`: `config.py → agent/ → app/ → backend/ → repo_root`

### 3. Infra Config (Settings)

**Файл:** `backend/app/config.py`

Добавить в `Settings` только infra-поля:
```python
llm_api_key: str = ""                                 # LLM_API_KEY
llm_base_url: str = "https://openrouter.ai/api/v1"    # LLM_BASE_URL
```

Добавить computed property для LangGraph DB URL:
```python
@property
def langgraph_database_url(self) -> str:
    """PostgreSQL URL для LangGraph (без +psycopg диалекта)."""
    return self.database_url.replace("+psycopg", "")
```

**Файл:** `.env.example` — обновить:
```
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://openrouter.ai/api/v1
```
Убрать `LLM_MODEL` (модель теперь в `configs/agent.yaml`).

**Файл:** `.env.local.example` — аналогично добавить `LLM_API_KEY`, `LLM_BASE_URL`.

### 4. Infra: LLM client + Checkpointer/Store factory

**Новый файл:** `backend/app/infra/llm.py`

```python
from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from app.config import Settings
from app.agent.config import AgentConfig


def create_llm(settings: Settings, agent_config: AgentConfig) -> BaseChatModel:
    return ChatOpenAI(
        model=agent_config.llm.model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
    )
```

- `settings` — infra (ключ, URL)
- `agent_config` — agent-level (модель)
- OpenRouter через `base_url`

**Новый файл:** `backend/app/infra/langgraph.py`

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.store.postgres.aio import AsyncPostgresStore


def create_checkpointer(db_url: str) -> AsyncPostgresSaver:
    return AsyncPostgresSaver.from_conn_string(db_url)

def create_store(db_url: str) -> AsyncPostgresStore:
    return AsyncPostgresStore.from_conn_string(db_url)
```

Фабрики аналогичны `infra/db.py`. Возвращают async context managers.

### 5. Context Schema

**В файле** `backend/app/agent/graph.py` (или отдельный модуль):

```python
from dataclasses import dataclass


@dataclass
class AgentContext:
    project_id: str
    user_id: str
```

Используется как `context_schema` при создании StateGraph и передаётся через `context=` при вызове графа.

### 6. Agent Graph + Agent Node

**Новый файл:** `backend/app/agent/graph.py`

```
START → agent → tools_condition → tools (ToolNode) → agent (цикл)
                    └── no tool_calls → END
```

```python
from dataclasses import dataclass
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.messages.utils import trim_messages, count_tokens_approximately
from langgraph.graph import StateGraph, MessagesState, START
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime

from app.agent.config import AgentConfig


@dataclass
class AgentContext:
    project_id: str
    user_id: str


def build_graph(
    model: BaseChatModel,
    tools: list,
    agent_config: AgentConfig,
) -> StateGraph:
    bound_model = model.bind_tools(tools)

    async def agent_node(
        state: MessagesState, runtime: Runtime[AgentContext]
    ) -> dict:
        system = SystemMessage(content=agent_config.prompt.system)

        trimmed = trim_messages(
            state["messages"],
            strategy="last",
            token_counter=count_tokens_approximately,
            max_tokens=agent_config.context.max_tokens,
            start_on="human",
            end_on=("human", "tool"),
        )

        response = await bound_model.ainvoke([system] + trimmed)
        return {"messages": [response]}

    tool_node = ToolNode(tools)

    builder = StateGraph(MessagesState, context_schema=AgentContext)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder


def compile_graph(builder, *, checkpointer, store):
    return builder.compile(checkpointer=checkpointer, store=store)
```

- `Runtime[AgentContext]` — типизированный доступ к context (project_id, user_id) и store
- `agent_config` — захвачен closure, параметры из YAML
- `bound_model = model.bind_tools(tools)` — явный bind
- В feat-001 tools=[] — ToolNode существует но не вызывается

### 7. AgentRunner: реальная реализация

**Новый файл:** `backend/app/agent/runner.py`

Класс `LangGraphAgentRunner`, реализующий Protocol `AgentRunner` из `services/agent_runner.py`.

**stream():**
```python
async def stream(self, *, thread_id, content, project_id, user_id):
    config = {"configurable": {"thread_id": str(thread_id)}}
    context = AgentContext(
        project_id=str(project_id),
        user_id=str(user_id),
    )
    input_msg = {"messages": [{"role": "user", "content": content}]}

    try:
        async for msg_chunk, metadata in self._graph.astream(
            input_msg, config, stream_mode="messages",
            context=context,
        ):
            if (
                hasattr(msg_chunk, "content")
                and isinstance(msg_chunk.content, str)
                and msg_chunk.content
            ):
                yield StreamEvent(
                    type="text_chunk",
                    data={"content": msg_chunk.content},
                )
        yield StreamEvent(type="done", data={})
    except Exception as e:
        yield StreamEvent(type="error", data={"detail": str(e)})
```

- `thread_id` в `configurable` (checkpointer), `project_id`/`user_id` в `context` (Runtime)
- `stream_mode="messages"` — `(AIMessageChunk, metadata)` per token
- Фильтрация: только string content (не tool_calls, не пустой)

**get_history():**
```python
async def get_history(self, *, thread_id):
    config = {"configurable": {"thread_id": str(thread_id)}}
    state = await self._graph.aget_state(config)
    if not state.values:
        return []
    messages = state.values.get("messages", [])
    return [
        Message(id=str(m.id), role=..., content=...)
        for m in messages
        if isinstance(m, (HumanMessage, AIMessage))
        and not getattr(m, "tool_calls", None)
    ]
```

**cancel():**
```python
async def cancel(self, *, thread_id):
    return True  # MVP stub
```

### 8. Wiring: Lifespan + Dependencies + env

**Файл:** `backend/app/main.py`

```python
from app.agent.config import load_agent_config
from app.infra.langgraph import create_checkpointer, create_store
from app.infra.llm import create_llm
from app.agent.graph import build_graph, compile_graph
from app.agent.runner import LangGraphAgentRunner

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    agent_config = load_agent_config()

    engine = create_engine(settings)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
    app.state.engine = engine
    app.state.session_factory = create_session_factory(engine)

    # LangGraph persistence
    lg_db_url = settings.langgraph_database_url
    async with (
        create_store(lg_db_url) as store,
        create_checkpointer(lg_db_url) as checkpointer,
    ):
        await store.setup()
        await checkpointer.setup()

        # Agent graph
        llm = create_llm(settings, agent_config)
        builder = build_graph(model=llm, tools=[], agent_config=agent_config)
        graph = compile_graph(builder, checkpointer=checkpointer, store=store)
        app.state.agent_runner = LangGraphAgentRunner(graph)

        yield

    await engine.dispose()
```

**Файл:** `backend/app/api/deps.py`

```python
def get_chat_service(session: DBSession, request: Request) -> ChatService:
    return ChatService(
        thread_view_repo=ThreadViewRepository(session),
        agent_runner=request.app.state.agent_runner,
    )
```

- Добавить `Request` как параметр
- Убрать `StubAgentRunner` import

**Файл:** `backend/app/agent/__init__.py`

```python
from app.agent.runner import LangGraphAgentRunner
```

### 9. Обновление langgraph-reference.md

Дополнить `doc/tech/langgraph-reference.md` секцией про `Runtime` и `context_schema` (актуальный API). Пометить `RunnableConfig` и `InjectedStore` как legacy-паттерны.

### 10. Что НЕ входит в feat-001

- Tools (feat-002, feat-003, feat-004)
- Knowledge Sphere integration (feat-002)
- Skills (feat-003)
- MCP tools (feat-004)
- Based Prompt (feat-005, сейчас — заглушка в YAML)
- History compaction / summarization (feat-005)
- Реальная cancel() (будущие итерации)

## Артефакты — новые файлы

```
configs/
└── agent.yaml                    # Agent-level config (YAML, committed)

backend/app/
├── agent/
│   ├── config.py                 # AgentConfig Pydantic model + loader
│   ├── graph.py                  # StateGraph, AgentContext, build/compile
│   └── runner.py                 # LangGraphAgentRunner
└── infra/
    ├── llm.py                    # create_llm() factory
    └── langgraph.py              # create_checkpointer/store factories
```

## Верификация

1. `uv sync` — зависимости установлены
2. `make docker-up` — PostgreSQL запущен
3. Настроить `.env` / `.env.local`:
   - `LLM_API_KEY=<ключ OpenRouter>`
   - `LLM_BASE_URL=https://openrouter.ai/api/v1`
4. Проверить `configs/agent.yaml` — модель, промпт
5. `make dev` — приложение стартует, checkpointer/store setup создаёт LangGraph-таблицы
6. **Тест streaming:**
   ```bash
   curl -X POST http://localhost:8000/projects \
     -H "X-User-Name: test" -H "Content-Type: application/json" \
     -d '{"name": "Test"}'
   # → project_id

   curl -X POST http://localhost:8000/projects/<id>/chats \
     -H "X-User-Name: test" -H "Content-Type: application/json" \
     -d '{"title": "Test chat"}'
   # → thread_id

   curl -N -X POST http://localhost:8000/projects/<id>/chats/<cid>/messages \
     -H "X-User-Name: test" -H "Content-Type: application/json" \
     -d '{"content": "Hello, who are you?"}'
   # → поток text_chunk events + done
   ```
7. **Тест persistence:** повторный запрос в тот же chat — агент видит историю
8. `make check` — ruff check, ruff format --check, mypy проходят

## Финальный шаг

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.
