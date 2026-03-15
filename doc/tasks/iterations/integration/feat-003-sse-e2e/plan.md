# Implementation Plan: feat-003 — SSE Streaming E2E

## Context

Предыдущие итерации (feat-001, fix-001, feat-002) связали backend и frontend: REST API работает через реальные HTTP-вызовы, контракты согласованы, `useAgentStream` переключён на реальный `fetch()`. Однако **полный SSE-поток не был верифицирован E2E** (feat-002 summary: "full flow не верифицирован — зависит от настроенного LLM agent"), а **cancel на бэкенде — заглушка** (`return True`). Эта итерация закрывает SSE-интеграцию: реальный cancel, обработка ошибок, E2E-верификация всех 6 event types.

## Референсы

| Документ | Роль |
|----------|------|
| [doc/workflow.md](../../doc/workflow.md) | Процесс итераций |
| [doc/tech/conventions.md](../../doc/tech/conventions.md) | Git flow, code quality |
| [doc/tasks/tasklist-integration.md](../../doc/tasks/tasklist-integration.md) | Исходный таск-лист |
| [doc/tech/backend.md](../../doc/tech/backend.md) | SSE Streaming Protocol, API endpoints, Service Layer |
| [doc/tech/frontend.md](../../doc/tech/frontend.md) | SSE lifecycle, Stream Store, Query invalidation |
| [iterations/integration/feat-002-frontend-backend/summary.md](../../doc/tasks/iterations/integration/feat-002-frontend-backend/summary.md) | Known issues: cancel promise, SSE E2E |
| [iterations/integration/fix-001-contract-alignment/summary.md](../../doc/tasks/iterations/integration/fix-001-contract-alignment/summary.md) | Контрактные решения |

## Быстро меняющиеся инструменты — проверка

| Инструмент | Версия | Статус |
|-----------|--------|--------|
| Vite | 7.3.1 (`http-proxy-3`) | Proxy корректно проксирует SSE (streaming responses), изменений не требуется |
| FastAPI | >=0.135.1 | `StreamingResponse` поддерживает cancel через await points в async generators. Текущий подход (ручной return `StreamingResponse`) работает, т.к. наши генераторы используют `async for`. Новый стиль (`response_class=StreamingResponse`) — необязателен |

## Шаг 0: Создание ветки

```bash
git fetch origin && git checkout -b feat/003-sse-e2e origin/develop
```

## Что уже реализовано (требует только E2E-верификации)

Анализ кода показал, что основная SSE-инфраструктура уже на месте:

- **`useAgentStream`** (`frontend/src/features/chat/hooks/useAgentStream.ts`) — подключён к реальному `fetch()`, парсит все 6 SSE event types
- **`stream-store`** (`frontend/src/stores/stream-store.ts`) — Zustand store с `startStream/appendText/setTool/addArtifact/endStream`
- **TanStack Query invalidation** — `done` → invalidate chat + recents, `artifact_created` → invalidate artifacts
- **Backend SSE endpoint** (`backend/app/api/routes/messages.py`) — `StreamingResponse` + `_event_generator`
- **`ChatService.send_message()`** (`backend/app/services/chat.py`) — async generator с post-hoc artifact linking
- **`LangGraphAgentRunner.stream()`** (`backend/app/agent/runner.py`) — `astream()` с `stream_mode=["messages", "updates"]`, error handling
- **UI компоненты** — `ToolIndicator`, `ArtifactCard`, `MessageList` (streaming mode), `ChatInput` (cancel button)

## Шаг 1: Backend — Cancel в AgentRunner

**Файл:** `backend/app/agent/runner.py`

Cancel реализуется внутри `LangGraphAgentRunner` (его публичный интерфейс — backend.md:253). Используется `asyncio.Event` по `thread_id`.

### Изменения в `LangGraphAgentRunner`:

```python
import asyncio

class LangGraphAgentRunner:
    def __init__(self, graph: Any) -> None:
        self._graph = graph
        self._cancel_events: dict[uuid.UUID, asyncio.Event] = {}

    async def stream(self, *, thread_id, content, project_id, user_id):
        cancel_event = asyncio.Event()
        self._cancel_events[thread_id] = cancel_event
        try:
            config = {"configurable": {"thread_id": str(thread_id)}}
            # ... existing context/input setup ...

            async for mode, data in self._graph.astream(
                input_msg, config,
                stream_mode=["messages", "updates"],
                context=context,
            ):
                if cancel_event.is_set():
                    yield StreamEvent(type="error", data={"detail": "Cancelled"})
                    return

                if mode == "messages":
                    # ... existing text_chunk logic ...
                elif mode == "updates":
                    for event in self._process_updates(data):
                        yield event

        except Exception as e:
            yield StreamEvent(type="error", data={"detail": str(e)})
        finally:
            self._cancel_events.pop(thread_id, None)

    async def cancel(self, *, thread_id: uuid.UUID) -> bool:
        event = self._cancel_events.get(thread_id)
        if event is None:
            return False
        event.set()
        return True
```

**Гранулярность cancel-проверки:**
- Между итерациями `astream()` — это уровень graph events
- Для text generation: каждые ~50-200ms (каждый AIMessageChunk)
- Для tool execution: после завершения tool node (до нескольких секунд для MCP tools)
- Для MVP приемлемо — spec не требует мгновенной отмены, "Cancel прерывает генерацию" = стрим закрывается

**Что НЕ меняется в ChatService:**
- `ChatService.cancel()` уже делегирует в `self._agent_runner.cancel(thread_id)` — работает as-is
- `ChatService.__init__()` — без изменений (нет нового параметра)
- `deps.py`, `main.py` — без изменений

## Шаг 2: Backend — Сохранение had_error логики

**Файл:** `backend/app/services/chat.py`

`ChatService.send_message()` не меняется в этой итерации. Критичная логика `had_error` уже корректна.

**Связь с cancel:** когда runner эмитит `error` (cancel или LLM-ошибка), ChatService получает его, ставит `had_error = True`, yield'ит клиенту. После цикла — `had_error` check → `return`. Done не отправляется. SSE-контракт соблюдён.

## Шаг 3: Frontend — Fix cancel

**Файл:** `frontend/src/features/chat/hooks/useAgentStream.ts`

Две проблемы (feat-002 known issues + ревью):

### 3a. Unhandled promise + isCancellingRef reset

**Почему reset в catch:** если POST /cancel не дошёл до сервера, cancel не произошёл. `isCancellingRef = true` подавит последующие реальные error events. Reset позволяет показать ошибки пользователю.

**Почему НЕ abort fetch:** по SSE-протоколу (backend.md:219), при cancel сервер отправляет `error` event → клиент получает его через SSE → `endStream()`. Если abort'нуть fetch, клиент не получит error event. Client-side abort — только при unmount (cleanup effect, строка 28).

## Шаг 4: Frontend — Обработка неожиданного завершения стрима

**Файл:** `frontend/src/features/chat/hooks/useAgentStream.ts`

Edge case: сервер закрывает соединение без отправки terminal event (done/error) — например, crash бэкенда. Сейчас `reader.read()` вернёт `{ done: true }`, цикл выйдет, но `endStream()` не вызовется → UI навсегда зависнет в streaming mode.

Решение — `terminated` flag перед main loop, проверка после выхода из цикла.

## Шаг 5: Линтинг

```bash
make lint && make type-check   # backend
make lint-fe                   # frontend (ESLint + TypeScript)
```

## Шаг 6: E2E верификация (Chrome, реальный backend + LLM)

| Тест | Что проверяем | Критерий приёмки |
|------|---------------|------------------|
| SSE-1: text_chunk | Отправка сообщения → текст появляется инкрементально | Чанк за чанком, не весь сразу |
| SSE-2: tool_start / tool_end | Агент вызывает tool → индикатор | ToolIndicator появляется при tool_start, исчезает при tool_end |
| SSE-3: artifact_created | Агент создаёт артефакт → карточка в чате | ArtifactCard в streaming bubble, список артефактов обновляется |
| SSE-4: done | Генерация завершена | Chat query инвалидируется, полное сообщение из сервера, streamStore в idle |
| SSE-5: error | Ошибка LLM | Сообщение об ошибке в UI, stream не зависает |
| SSE-6: cancel | Кнопка Cancel → POST /cancel → error event | UI в idle без ошибки, стрим прекращается |
| SSE-7: network drop | Отключить backend mid-stream | "Connection lost" в UI, stream не зависает |
| SSE-8: повторная отправка | После done/error/cancel — новое сообщение | Новый стрим работает корректно |

## Шаг 7: Документация итерации

- Создать `doc/tasks/iterations/integration/feat-003-sse-e2e/plan.md` (этот план)
- Обновить `tasklist-integration.md`: статус feat-003 → In Progress, добавить ветку

## Финальный шаг: Ревью

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.

## Затрагиваемые файлы (summary)

| Файл | Изменение |
|------|-----------|
| `backend/app/agent/runner.py` | + `_cancel_events` dict, cancel check в `stream()`, реальный `cancel()` |
| `frontend/src/features/chat/hooks/useAgentStream.ts` | Fix cancel promise + isCancellingRef reset, handle unexpected stream end |
