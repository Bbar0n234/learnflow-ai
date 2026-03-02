# LangGraph Reference

# TODO: куда нибудь бы вынести его в поддиректорию reference/ ...

Референс для Phase D. Собрано в ходе Phase B (февраль 2026). Тезисный формат — cheatsheet, не tutorial.

## API эволюция

### Timeline

| Когда | Что |
|-------|-----|
| ~mid 2025 | `state_modifier` и `messages_modifier` deprecated → заменены на `prompt` |
| mid-late 2025 | `pre_model_hook`, `post_model_hook`, `response_format` добавлены в create_react_agent |
| Октябрь 2025 (LangGraph v1.0) | `create_react_agent` из `langgraph.prebuilt` deprecated. Замена: `create_agent` из `langchain.agents` |
| Октябрь 2025 (LangChain v1.0) | `create_agent` с middleware-системой. Под капотом — тот же LangGraph, возвращает `CompiledStateGraph` |
| langgraph-prebuilt 1.0.8 | Последний релиз (февраль 2026), create_react_agent работает с deprecation warning |

### Import paths

```
# Deprecated (работает, удаление в LangGraph v2.0)
from langgraph.prebuilt import create_react_agent

# Новый рекомендованный (нестабильно, были баги в v1.1.0)
from langchain.agents import create_agent

# Core API (наш выбор, см. ADR-006)
from langgraph.graph import StateGraph, MessagesState, START, END
```

### create_react_agent — сигнатура (актуальная)

```
create_react_agent(
    model,                    # str | BaseChatModel | Callable[(state, runtime) -> model]
    tools,                    # Sequence[BaseTool | Callable] | ToolNode
    *,
    prompt=None,              # str | SystemMessage | Callable[(state) -> messages]
    pre_model_hook=None,      # нода перед каждым LLM call (для trim/summarize)
    post_model_hook=None,     # нода после LLM call (для HITL, guardrails)
    response_format=None,     # schema для structured output
    state_schema=None,        # кастомный TypedDict (должен содержать messages)
    context_schema=None,      # schema для runtime context
    checkpointer=None,
    store=None,
    interrupt_before=None,
    interrupt_after=None,
    version="v2",             # v2: параллельное исполнение tools через Send API
    name=None,
) -> CompiledStateGraph
```

### create_agent (LangChain) — ключевые отличия от create_react_agent

- `system_prompt` вместо `prompt` (только статический текст)
- `middleware` вместо hooks: `@dynamic_prompt`, `@wrap_model_call`, `@before_model`, `@after_model`, `@wrap_tool_call`
- `context_schema` + `ToolRuntime` для типизированного доступа к context, store, state
- `cache` параметр для кэширования

## ToolNode (prebuilt)

```
from langgraph.prebuilt import ToolNode
```

Используется как нода в любом StateGraph (не привязан к create_react_agent).

**Поддерживает:**
- InjectedStore, InjectedState, ToolRuntime — инжекция, скрыта от LLM schema
- Command returns из tools — state update + routing
- Параллельное исполнение tool calls
- Error handling (configurable strategies)
- Валидация, фильтрация ошибок injected-параметров

**Когда нужен кастомный tool node:**
- Динамическая регистрация tools в runtime
- Нестандартные форматы выхода
- Кастомная routing-логика из tool execution

Для нашего MVP — prebuilt ToolNode достаточен.

## InjectedStore / InjectedState

Аннотации типов для инжекции в tools. Скрыты от LLM-schema.

### InjectedStore — доступ к LangGraph Store

```
from langgraph.prebuilt import InjectedStore
from langgraph.store.base import BaseStore

@tool
def update_sphere(
    facts: str,                                          # видит LLM
    store: Annotated[BaseStore, InjectedStore()]          # скрыто от LLM
) -> str:
    store.put(("project", project_id, "sphere"), "index", {"content": facts})
    return "Updated"
```

Граф должен быть скомпилирован с store: `builder.compile(checkpointer=..., store=store)`.

### InjectedState — read-only доступ к graph state

```
from langgraph.prebuilt import InjectedState

@tool
def my_tool(
    query: str,
    state: Annotated[dict, InjectedState]               # скрыто, read-only
) -> str:
    messages = state["messages"]
    ...
```

Можно инжектить конкретное поле: `Annotated[dict, InjectedState("user_info")]`.

### RunnableConfig — доступ к config из tools

```
from langchain_core.runnables import RunnableConfig

@tool
def my_tool(query: str, config: RunnableConfig) -> str:
    user_id = config["configurable"]["user_id"]
    project_id = config["configurable"]["project_id"]
    ...
```

### ToolRuntime — единый объект (альтернатива)

```
from langgraph.prebuilt import ToolRuntime

@tool
def my_tool(query: str, runtime: ToolRuntime) -> str:
    state = runtime.state
    store = runtime.store
    config = runtime.config
    ...
```

## Command API vs conditional edges

### Conditional edges — routing без state update

```
from langgraph.prebuilt import tools_condition

builder.add_conditional_edges("agent", tools_condition)
# tool_calls → "tools", нет → END
```

Или кастомная routing-функция:

```
def should_continue(state) -> Literal["tools", "__end__"]:
    if state["messages"][-1].tool_calls:
        return "tools"
    return END

builder.add_conditional_edges("agent", should_continue)
```

### Command — routing + state update в одном return

```
from langgraph.types import Command

def my_node(state) -> Command[Literal["node_b", "node_c"]]:
    return Command(update={"foo": "bar"}, goto="node_b")
```

`Command[Literal[...]]` — type annotation обязательна (для валидации и визуализации графа).

**Когда Command:** мульти-агентные handoffs, одновременное обновление state и routing.
**Когда conditional edges:** чистая маршрутизация, как в ReAct loop (наш MVP).

**Command из tools:**

```
@tool
def my_tool(tool_call_id: Annotated[str, InjectedToolCallId]) -> Command:
    return Command(update={
        "custom_key": "value",
        "messages": [ToolMessage(content="...", tool_call_id=tool_call_id)]
    })
```

ToolMessage с matching tool_call_id обязателен в update.

## Context engineering

### В кастомном графе — внутри agent-ноды

```
def agent_node(state, config):
    # 1. System prompt (Based Prompt + KS Index)
    ks_index = store.get(...)  # из Store
    system = SystemMessage(content=f"{BASED_PROMPT}\n\n{ks_index}")

    # 2. Trim messages (локально, не в state)
    trimmed = trim_messages(state["messages"], max_tokens=..., strategy="last")

    # 3. LLM call
    response = model.invoke([system] + trimmed)

    # 4. Результат → в state (полная история)
    return {"messages": [response]}
```

### trim_messages

```
from langchain_core.messages.utils import trim_messages, count_tokens_approximately

trimmed = trim_messages(
    messages,
    strategy="last",                    # keep recent
    token_counter=count_tokens_approximately,
    max_tokens=10000,
    include_system=True,                # system message всегда сохраняется
    start_on="human",
    end_on=("human", "tool"),
)
```

### SummarizationNode (prebuilt)

```
from langgraph.prebuilt import SummarizationNode

summarization = SummarizationNode(
    token_counter=count_tokens_approximately,
    model=summarization_model,
    max_tokens=4000,
    max_summary_tokens=500,
    output_messages_key="llm_input_messages",
)
```

Может использоваться как pre_model_hook или как отдельная нода.

### RemoveMessage — точечное удаление

```
from langchain_core.messages import RemoveMessage
from langgraph.graph.message import REMOVE_ALL_MESSAGES

# Удалить конкретные сообщения
{"messages": [RemoveMessage(id=m.id) for m in old_messages]}

# Удалить все
{"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES)]}
```

## Functional API

Альтернатива Graph API. Декораторы вместо графа.

```
from langgraph.func import entrypoint, task

@task
def call_llm(messages):
    return model.invoke(messages)

@entrypoint(checkpointer=checkpointer)
def agent(messages):
    response = call_llm(messages).result()
    while response.tool_calls:
        tool_results = [call_tool(tc).result() for tc in response.tool_calls]
        messages = add_messages(messages, [response, *tool_results])
        response = call_llm(messages).result()
    return add_messages(messages, response)
```

**Когда Functional API:** линейные workflow, быстрый прототип, retrofitting в существующий код.
**Когда Graph API:** сложные агенты, визуализация, time-travel, subgraph composition.

Обе API на одном runtime, можно миксовать.

## Мульти-агент паттерны

### Subagents — compiled graph как нода

```
sub_agent = sub_builder.compile()

parent_builder.add_node("sub_agent", sub_agent)  # shared state
# или через wrapper-ноду если state schema разный
```

Checkpointer для subgraph: `False` (без overhead), `None` (per-invocation), `True` (stateful).

### Паттерны

| Паттерн | Описание |
|---------|----------|
| Supervisor | Центральный агент делегирует специалистам |
| Swarm | Агенты автономно передают контроль друг другу |
| Handoffs | Динамическая передача через Command(goto=...) |
| Pipeline | Последовательная цепочка агентов |

Библиотека `langgraph-supervisor` для supervisor-паттерна.

Эволюционный путь зафиксирован в [ADR-001](adr/ADR-001-general-agent.md): single agent → orchestrator + sub-agents → hierarchical.

## Persistence

### Checkpointer — storage format

- Полные state snapshots (не дельты), сериализация через msgpack (JsonPlusSerializer)
- Таблицы: `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`
- Примитивы (str, int) → JSONB inline. Сложные объекты (messages) → BYTEA в checkpoint_blobs
- Десериализация длинных историй может быть медленной (4+ сек)

### Получение истории

```
config = {"configurable": {"thread_id": "..."}}
snapshot = graph.get_state(config)
messages = snapshot.values["messages"]
```

### Листинг threads (OSS LangGraph)

Нет встроенного API. Решение: app-managed таблица `thread_views` (см. [backend.md](backend.md) / Persistence).

### Store — cross-thread память

```
store.put(namespace_tuple, key, value_dict)
store.get(namespace_tuple, key)
store.search(namespace_tuple, query=..., limit=...)
```

Namespace — tuple: `("project", project_id, "sphere")`. Поддерживает semantic search (embeddings).

## LangChain 1.0 vs LangGraph — резюме

| Аспект | LangChain create_agent | LangGraph StateGraph |
|--------|----------------------|---------------------|
| Для кого | Быстрый старт, стандартные агенты | Полный контроль, кастомные workflow |
| Кастомизация | Middleware (ограничено) | Произвольные ноды и рёбра |
| Мульти-агент | Нет | Subgraphs, supervisor, swarm |
| Стабильность | API в flux | Core API, стабилен |
| Абстракции | Ломаются на нетривиальном | Нет лишних абстракций |
| Рекомендация команды LangChain | "Start high, drop low" | Для production custom agents |

Наш выбор: LangGraph StateGraph. Обоснование: [ADR-006](adr/ADR-006-custom-stategraph.md).
