# Post-Implementation Summary: feat-004 — Service Layer

## Результат

Реализация полностью соответствует плану. Все критерии приёмки выполнены. Отклонений от плана нет.

## Что сделано

### Новые файлы (7)

- `services/exceptions.py` — `EntityNotFoundError` (framework-agnostic, API Layer конвертирует в HTTP 404)
- `services/agent_runner.py` — доменные типы (`StreamEvent`, `Message`) + `AgentRunner` Protocol + `StubAgentRunner`
- `services/sphere.py` — `SphereData` + `SphereService` Protocol + `StubSphereService`
- `services/project.py` — `ProjectService` (create, get, list, update, delete)
- `services/artifact.py` — `ArtifactService` (get, list — read-only для API)
- `services/chat.py` — `ChatDetail` + `ChatService` (create_chat, list_chats, get_chat, list_recent, send_message, cancel)
- `services/__init__.py` — реэкспорт всех публичных символов (12 имён)

### Изменения в существующих файлах (1)

- `repositories/thread_view.py` — добавлен метод `touch()` (расширение feat-003 для корректной работы `list_recent`)

## Паттерны

- **DI:** constructor injection во всех сервисах (`__init__(self, *, repo: Repo)`) — wiring в `deps.py` (feat-005)
- **Error handling:** `EntityNotFoundError` в сервисном слое, без зависимости от FastAPI
- **Protocol:** `AgentRunner` и `SphereService` как `typing.Protocol` — потребитель определяет контракт
- **Stub-реализации:** `StubAgentRunner` и `StubSphereService` позволяют работать без реального агента
- **Доменные типы:** `StreamEvent`, `Message`, `SphereData`, `ChatDetail` — dataclass-ы как контракт между слоями

## Контракты для следующих итераций

### feat-005 (API Layer)

- `ChatService.send_message` — async generator. API Layer **обязан** pre-validate существование чата **до** создания `StreamingResponse` (иначе ошибка уйдёт внутри уже открытого потока). Контракт зафиксирован в docstring метода.
- `EntityNotFoundError` → exception handler для конвертации в HTTP 404.
- Wiring сервисов через `deps.py` (constructor injection pattern готов).

### feat-agent (Agent Layer)

- Реализация `AgentRunner` Protocol: `stream()`, `get_history()`, `cancel()`.
- `stream()` — `def` (не `async def`), возвращает `AsyncIterator[StreamEvent]`.

### feat-sphere (Knowledge Sphere)

- Реализация `SphereService` Protocol: `get()`, `update()`.

## Верификация

- `make check` (ruff check + ruff format --check + mypy) — всё проходит
- 6 методов в ProjectService, 2 в ArtifactService, 6 в ChatService
- AgentRunner Protocol (3 метода) + StubAgentRunner
- SphereService Protocol (2 метода) + StubSphereService
