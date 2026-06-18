# Эмпирика: re-entry thread после исключения в tool-ноде

Версии: langgraph 1.1.3, langgraph-prebuilt 1.0.8, langgraph-checkpoint 4.0.1.

## Вывод (TL;DR)
Проблема **воспроизводится и серьёзна**. Когда tool-нода бросает не-`ToolInvocationError` (наш `RuntimeError`) посреди ReAct-шага, в checkpoint остаётся **«висячий» `AIMessage` с `tool_calls` без парного `ToolMessage`**. При следующем входе на тот же `thread_id` с новым `HumanMessage` (как всегда делает `runner.py`) LangGraph отбрасывает pending tool-задачу и дописывает `HumanMessage` сразу за висячим `AIMessage(tool_calls)`. История становится **навсегда невалидной** для OpenAI-совместимого API → первый же LLM-вызов на следующем запуске получает 400. **Агент не может продолжить на этом thread.**

## Семантика LangGraph
- Checkpoint пишется на границе super-step, не внутри ноды. Упавшая нода свой write не производит → `ToolMessage` не появляется, а закоммиченный шаг `agent` (с `tool_calls`) остаётся.
- Дефолтный `ToolNode._default_handle_tool_errors` пробрасывает всё, кроме `ToolInvocationError` → `RuntimeError` всплывает из `graph.astream`.
- Resume с новым вводом стартует новый super-step от входа графа, pending-задача отбрасывается (сирота не лечится).

## Репро (изолированный мини-StateGraph + InMemorySaver)
- RUN 1 (стор=None): `RuntimeError`, `next=('tools',)`, в state `AIMessage(tool_calls)` без `ToolMessage`. Висячий tool_call воспроизведён.
- RUN 2 (новый HumanMessage, тот же thread): pending `tools` отброшена, `HumanMessage` встал за висячим `AIMessage(tool_calls)`. Реальный `trim_messages` из `agent_node` сироту НЕ убирает при нормальном бюджете → в OpenAI уходит `[..., AI(tool_calls), Human]` → 400.
- Контроль (`ainvoke(None)` без нового ввода): история зажилась бы корректно — но `runner.py` так не делает.
- Важно: ленивая проверка «по id» давала ложный VALID; при уникальных id и строгой contig-проверке — стабильный INVALID.

## Важная оговорка про store-is-None
`agent_node` сам требует стор (`graph.py:225-226` → `RuntimeError`) **до** генерации tool_calls. Поэтому при *полном* отсутствии стора первым падает `agent_node` → сироты НЕТ, история валидна (просто допишется HumanMessage). Висячий tool_call от стора — в узком окне: стор есть на чтении в agent_node, но падает на записи в KS/memory-tool (транзиент), либо уходит между шагами. Зато **общий класс** (любой не-`ToolInvocationError` в tools → сирота) бьёт широко и от стора не зависит: транзиентные сбои стора, падения MCP-tool, баги в tools.

## Рекомендации
1. **Стоп новой порчи (1 строка):** `ToolNode(tools, handle_tool_errors=True)` в `graph.py:339`. Эмпирически проверено: любое исключение → `ToolMessage(status="error")`, ReAct-шаг завершается, история валидна, агент получает текст ошибки и восстанавливается. Штатный паттерн ReAct.
2. **Лечение уже испорченных threads:** репарация на входе (в `runner.py` перед `astream` или в `CheckpointHistory`) — найти `AIMessage` с неотвеченными `tool_calls`, синтезировать `ToolMessage(status="error", tool_call_id=..., content="Tool call interrupted; not executed.")` через `aupdate_state`. Закрывает пары → следующий вход валиден. `handle_tool_errors` старые сироты НЕ чинит.

Файлы: `graph.py:339` (ToolNode), `graph.py:225-226` (store-guard agent_node), `tools/knowledge_sphere.py:19-22`, `tools/user_memory.py:7-10`, `runner.py:157-234`.
Репро-скрипты (временные): `/tmp/repro_dangling_toolcall.py`, `/tmp/repro_reentry.py`, `/tmp/repro_strict.py`.
