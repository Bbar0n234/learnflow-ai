# ADR-014: Graph Factory — per-request graph build

## Статус

Принято (обновлено: контекст расширен Track C)

## Контекст

feat-003 вводит две оси per-request динамики:

1. **Track A — Runtime model switching.** Модель LLM определяется per-request на основе каскада overrides (thread → project → user → Langfuse → config file).
2. **Track C — Per-user MCP tools.** Каждый пользователь может подключить свои MCP серверы на уровне user/project/thread. Набор tools различается per-request.

Текущая архитектура: LLM создаётся один раз при старте (`create_llm()` в `lifespan`), привязывается к tools (`model.bind_tools(tools)`) и запекается в closure `agent_node` через `build_graph()`. `ToolNode(tools)` тоже получает tools при конструкции. Граф компилируется один раз. Смена модели или tools требует перезапуска сервиса.

Нужно: менять модель и набор tools без перезапуска, с гранулярностью до отдельного чата.

## Рассмотренные варианты

### A: Graph Factory (per-request build + compile)

Пересоздавать `StateGraph` + `compile()` на каждый запрос с нужными model и tools. Checkpointer и store — shared (передаются по ссылке).

- **За:** чистый контракт — и `bind_tools`, и `ToolNode` получают правильные tools естественным путём; один механизм для обоих осей динамики (model + tools); `agent_node` остаётся чистым оркестратором без dynamic resolution; паттерн LangGraph Platform (graph factory per-request).
- **Против:** per-request compilation overhead.

**Оценка overhead:** `compile()` для 2-node графа (agent + tools, 3 edges) — создание Python-объектов без I/O. Стоимость ~1–5ms. Для сравнения: MCP `get_tools()` = 100–200ms, LLM call = 1000–30000ms. Compile — шум на фоне полезной работы.

### B: Per-user graph instances

Кэш compiled graphs по user_id или config hash — каждый пользователь получает свой экземпляр графа.

- **За:** полная изоляция пользователей.
- **Против:** memory overhead (N пользователей × compiled graph); инвалидация кэша при изменении MCP серверов или model config; LangGraph документация рекомендует против этого подхода при неизменной топологии.

### C: Dynamic resolution в agent_node + ToolNode interceptor

Один compiled graph. Model resolve и `bind_tools()` per-invocation внутри `agent_node()`. User tools передаются через `AgentContext`, `ToolNode` использует `awrap_tool_call` для перехвата вызовов user tools.

- **За:** один graph, zero overhead на compilation; `bind_tools()` — лёгкая операция.
- **Против:** два раздельных механизма для одной задачи: `bind_tools` для модели + `awrap_tool_call` для ToolNode; interceptor вызывается для ВСЕХ tool calls (overhead на global tools); dynamic tools не проходят через стандартный `__init__` ToolNode (InjectedState вычисляется on-the-fly, edge case).

## Решение

Вариант A — Graph Factory (per-request build + compile).

## Обоснование

- **Один механизм** для обоих осей динамики. Model resolve и tool resolve выполняются ДО графа. `build_graph(model, tools)` запекает всё при конструкции. Нет interceptors, нет двух путей injection.
- **Negligible overhead.** Для 2-node графа compile — sub-millisecond. Checkpointer и store shared, привязка по ссылке.
- **LangGraph Platform pattern.** LangGraph Platform (LangSmith hosting) использует graph factory per-request — граф создаётся для каждого invocation с нужным контекстом.
- **Checkpointer compatibility.** Checkpoints keyed by `thread_id`, не зависят от конкретного graph instance. Разные per-request графы корректно читают/пишут один и тот же checkpoint.
- **Простой `agent_node`.** Не нужно знать про model switching или dynamic tools — model и tools уже запечены в closure.
- Вариант C (ранее рассмотренный) отклонён: с появлением Track C (per-user tools) interceptor (`awrap_tool_call`) недостаточно элегантен, а Graph Factory решает обе задачи одним механизмом.

## Следствия

- `AgentRunner` хранит `GraphFactory` (не один compiled graph). Для state queries (get_history, get_last_ai_message_id) используется base graph с global tools.
- `AgentContext` упрощается: только `project_id` и `user_id`. `model_config` и user tools не нужны в context — они запечены в graph instance.
- Cascade resolve модели и MCP tools выполняется **до** вызова графа (в ChatService через `ModelConfigResolver` и `MCPToolResolver`). Результаты передаются в `AgentRunner.stream()` как параметры.
- `build_graph()` не меняется — уже принимает `model` и `tools` как параметры. Изменяется точка вызова: из lifespan (один раз) → per-request (в runner).
- `agent_node` рефакторится (Track A): извлечение функций (_reduce_context, _fetch_base_prompt, _build_system_message, _invoke_llm), но без dynamic model/tool logic внутри.
