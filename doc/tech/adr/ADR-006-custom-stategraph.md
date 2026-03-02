# ADR-006: Custom StateGraph для Agent Runtime

## Статус

Принято

## Контекст

Agent Runtime реализуется на LangGraph (зафиксировано в [vision.md](../../vision.md)). Вопрос: как строить граф агента — использовать готовую функцию или собирать вручную.

API LangGraph эволюционировал за 2025:
- `create_react_agent` из `langgraph.prebuilt` — **deprecated** с LangGraph v1.0 (октябрь 2025). Работает, удаление планируется в v2.0.
- `create_agent` из `langchain.agents` (LangChain v1.0) — официальная замена. Под капотом тот же LangGraph, возвращает `CompiledStateGraph`. Новая система middleware, `system_prompt`, `context_schema`.
- `StateGraph` из `langgraph.graph` — core API LangGraph. Явные ноды, рёбра, условные переходы. Полный контроль.

## Решение

Custom StateGraph (core LangGraph API). Два узла (agent + tools), один conditional edge. Сложность системы — в context engineering внутри agent-ноды и в tools, не в топологии графа.

## Альтернативы

### create_react_agent из langgraph.prebuilt (отклонено)

**Причина:** deprecated с октября 2025. Начинать новый проект на deprecated API — создаёт технический долг с первого дня.

### create_agent из langchain.agents (отклонено)

**Причины:**
- Экосистема нестабильна (баги в v1.1.0, import path менялся)
- LangChain-абстракции ломаются на нетривиальных кейсах — подтверждено практическим опытом и community feedback
- Middleware-система не даёт выигрыша по сравнению с обычными нодами в кастомном графе
- Нет ценности для разработчика, знающего LangGraph — дополнительный слой абстракции без пользы

### Functional API — @entrypoint + @task (отклонено для основного агента)

**Причина:** нет визуализации графа, ограниченный time-travel, хуже subgraph composition. Может использоваться для вспомогательных задач.

## Следствия

- Полный контроль над графом — добавление нод, sub-agents, кастомная логика без борьбы с абстракциями
- Нет deprecation risk — StateGraph = core API, фундамент LangGraph
- Минимальный boilerplate — ~40 строк для ReAct-цикла
- Переиспользуем из `langgraph.prebuilt`: ToolNode, tools_condition, InjectedStore, InjectedState
- Миграция на Command API для мульти-агентности — тривиальная, при необходимости
