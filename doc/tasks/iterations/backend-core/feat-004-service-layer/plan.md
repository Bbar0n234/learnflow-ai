# Implementation Plan: feat-004 — Service Layer

## Context

Итерация feat-004 из tasklist-backend-core: сервисный слой — оркестрация между API и Repository/Agent. Определение интерфейсов (Protocol) для Agent Runtime и Knowledge Sphere, stub-реализации для работы без агента.

Blocked-by зависимость feat-003 (Repository Layer) — выполнена. Service Layer — следующий слой в восходящей сборке: Infra → Models → Repositories → **Services** → API.

## Референсы

| Документ | Назначение |
|----------|-----------|
| [workflow.md](../../../../workflow.md) | Процесс итерации |
| [conventions.md](../../../../tech/conventions.md) | Git, naming, code quality |
| [tasklist-backend-core.md](../../../tasklist-backend-core.md) | Описание итерации feat-004 |
| [backend.md](../../../../tech/backend.md) | Архитектура, API schemas, persistence, SSE protocol |

## Верифицированные версии инструментов

| Инструмент | Версия | API проверен через |
|-----------|--------|-------------------|
| FastAPI | 0.135.1 | Не задействован в этой итерации напрямую |
| SQLAlchemy | 2.0.48 | Используется через существующие репозитории |
| pydantic | 2.12.5 | Не задействован (schemas — feat-005) |
| pydantic-settings | 2.13.1 | Не задействован |
| Python | 3.12 | `typing.Protocol`, `collections.abc.AsyncIterator`, `dataclasses` — stdlib |

Новые пакеты не добавляются. Сервисный слой использует только stdlib и уже установленные зависимости через существующий repository layer.

## Шаг 0: Ветка

```bash
git fetch origin && git checkout -b feat/004-service-layer origin/develop
```

Ветка: `feat/004-service-layer` (conventions.md: `<type>/<NNN>-<short-desc>`).

## Архитектурные решения

### Error handling: EntityNotFoundError

Сервисы проверяют существование сущностей при get/update/delete. Нужен механизм для сигнализации "not found".

**Предлагаемый подход:** определить `EntityNotFoundError` в сервисном слое. API Layer (feat-005) добавит exception handler для конвертации в HTTP 404.

```python
# services/exceptions.py
class EntityNotFoundError(Exception):
    def __init__(self, entity: str, entity_id: object) -> None:
        self.entity = entity
        self.entity_id = entity_id
        super().__init__(f"{entity} {entity_id} not found")
```

Обоснование: сервисы не должны зависеть от FastAPI (separation of layers). Прямой raise HTTPException — нарушение границ слоёв. **Одобрено архитектором.**

### ThreadView.updated_at при send_message

Сообщения хранятся в checkpointer, не в app-таблицах. Отправка сообщения не триггерит SQL UPDATE на ThreadView → `updated_at` не обновляется → `list_recent` (сортировка по `updated_at desc`) сломана.

**Решение:** обновлять `updated_at` **до** делегирования в stream. Семантика: факт отправки сообщения пользователем = "последняя активность" в чате, независимо от ответа агента.

**Реализация:** добавить метод `touch()` в `ThreadViewRepository` (расширение feat-003). Метод выполняет UPDATE для обновления `updated_at` без изменения других полей.

```python
# repositories/thread_view.py — новый метод
async def touch(self, thread_view: ThreadView) -> None:
    """Update updated_at without changing other fields."""
    thread_view.title = thread_view.title  # trigger onupdate
    await self._session.flush()
```

### Async generator: контракт для API Layer

`send_message` — async generator (содержит `yield`). Тело не выполняется при вызове, а только при первом `__anext__()`. Это значит, что `EntityNotFoundError` выбросится уже внутри streaming-контекста, после отправки HTTP 200 клиенту.

**Решение:** проверка в `send_message` — defense in depth. Primary validation — ответственность API Layer (feat-005): проверить существование чата **до** создания `StreamingResponse`. Контракт зафиксирован в docstring метода.

### Wiring: паттерн инъекции зависимостей

Аналогично репозиториям — constructor injection. Зависимости объявляются в `__init__`:

```python
class ProjectService:
    def __init__(self, *, project_repo: ProjectRepository) -> None: ...

class ChatService:
    def __init__(self, *, thread_view_repo: ThreadViewRepository, agent_runner: AgentRunner) -> None: ...
```

Инстанцирование (wiring) — ответственность `deps.py` (feat-005). В этой итерации определяем паттерн, не wire-up.

## Дизайн

### Файловая структура

```
backend/app/services/
├── __init__.py           # re-export сервисов
├── exceptions.py         # EntityNotFoundError
├── project.py            # ProjectService
├── artifact.py           # ArtifactService
├── chat.py               # ChatService + ChatDetail
├── agent_runner.py       # AgentRunner Protocol + StubAgentRunner + StreamEvent, Message
└── sphere.py             # SphereService Protocol + StubSphereService + SphereData
```

### Доменные типы

Типы — контракт между Service и Agent слоями. Определяются рядом с Protocol (в services/), т.к. потребляющий слой определяет интерфейс.

```python
# agent_runner.py
from dataclasses import dataclass
from datetime import datetime
from typing import Any

@dataclass(frozen=True)
class StreamEvent:
    """SSE event из agent stream. Маппинг на wire-формат — в API Layer."""
    type: str       # "text_chunk", "tool_start", "tool_end", "artifact_created", "done", "error"
    data: dict[str, Any]  # Payload: {"content": "..."}, {"tool": "..."}, etc.

@dataclass(frozen=True)
class Message:
    """Сообщение из истории чата (из checkpointer)."""
    id: str
    role: str           # "user" | "assistant"
    content: str
    created_at: datetime | None = None
```

```python
# sphere.py
from dataclasses import dataclass
from datetime import datetime
import uuid

@dataclass(frozen=True)
class SphereData:
    """Knowledge Sphere проекта."""
    project_id: uuid.UUID
    content: str
    updated_at: datetime
```

```python
# chat.py
from dataclasses import dataclass
from app.models.thread_view import ThreadView
from app.services.agent_runner import Message

@dataclass
class ChatDetail:
    """ThreadView + история сообщений из checkpointer."""
    thread_view: ThreadView
    messages: list[Message]
```

### Protocol: AgentRunner

Публичный интерфейс Agent Layer. Определяется в services/ — потребитель определяет контракт.

```python
# agent_runner.py
import uuid
from collections.abc import AsyncIterator
from typing import Protocol

class AgentRunner(Protocol):
    def stream(
        self,
        *,
        thread_id: uuid.UUID,
        content: str,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> AsyncIterator[StreamEvent]: ...

    async def get_history(
        self,
        *,
        thread_id: uuid.UUID,
    ) -> list[Message]: ...

    async def cancel(
        self,
        *,
        thread_id: uuid.UUID,
    ) -> bool: ...
```

**stream()** — `def` (не `async def`), т.к. возвращает AsyncIterator напрямую. Реализация — async generator function. Caller: `async for event in runner.stream(...)`.

**get_history()** — coroutine, возвращает список сообщений из checkpointer.

**cancel()** — coroutine, возвращает успешность отмены.

### Protocol: SphereService

```python
# sphere.py
import uuid
from typing import Protocol

class SphereService(Protocol):
    async def get(self, *, project_id: uuid.UUID) -> SphereData: ...
    async def update(self, *, project_id: uuid.UUID, content: str) -> SphereData: ...
```

### Stub: StubAgentRunner

```python
# agent_runner.py
class StubAgentRunner:
    async def stream(
        self, *, thread_id: uuid.UUID, content: str,
        project_id: uuid.UUID, user_id: uuid.UUID,
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type="text_chunk", data={"content": f"Stub response to: {content}"})
        yield StreamEvent(type="done", data={})

    async def get_history(self, *, thread_id: uuid.UUID) -> list[Message]:
        return []

    async def cancel(self, *, thread_id: uuid.UUID) -> bool:
        return True
```

### Stub: StubSphereService

```python
# sphere.py
from datetime import datetime, timezone

class StubSphereService:
    async def get(self, *, project_id: uuid.UUID) -> SphereData:
        return SphereData(
            project_id=project_id,
            content="",
            updated_at=datetime.now(timezone.utc),
        )

    async def update(self, *, project_id: uuid.UUID, content: str) -> SphereData:
        return SphereData(
            project_id=project_id,
            content=content,
            updated_at=datetime.now(timezone.utc),
        )
```

### ProjectService

```python
# project.py
class ProjectService:
    def __init__(self, *, project_repo: ProjectRepository) -> None:
        self._project_repo = project_repo

    async def create_project(self, *, user_id: uuid.UUID, name: str) -> Project:
        return await self._project_repo.create(user_id=user_id, name=name)

    async def get_project(self, project_id: uuid.UUID) -> Project:
        project = await self._project_repo.get_by_id(project_id)
        if project is None:
            raise EntityNotFoundError("Project", project_id)
        return project

    async def list_projects(self, user_id: uuid.UUID) -> list[Project]:
        return await self._project_repo.list_by_user(user_id)

    async def update_project(self, project_id: uuid.UUID, *, name: str) -> Project:
        project = await self.get_project(project_id)  # raises if not found
        return await self._project_repo.update(project, name=name)

    async def delete_project(self, project_id: uuid.UUID) -> None:
        project = await self.get_project(project_id)  # raises if not found
        await self._project_repo.delete(project)
```

### ArtifactService

```python
# artifact.py
class ArtifactService:
    def __init__(self, *, artifact_repo: ArtifactRepository) -> None:
        self._artifact_repo = artifact_repo

    async def get_artifact(self, artifact_id: uuid.UUID) -> Artifact:
        artifact = await self._artifact_repo.get_by_id(artifact_id)
        if artifact is None:
            raise EntityNotFoundError("Artifact", artifact_id)
        return artifact

    async def list_artifacts(self, project_id: uuid.UUID) -> list[Artifact]:
        return await self._artifact_repo.list_by_project(project_id)
```

Read-only для API. Артефакты создаются агентом через tool `create_artifact` → прямой вызов `ArtifactRepository` (см. правила вызовов в backend.md).

### ChatService

```python
# chat.py
class ChatService:
    def __init__(
        self,
        *,
        thread_view_repo: ThreadViewRepository,
        agent_runner: AgentRunner,
    ) -> None:
        self._thread_view_repo = thread_view_repo
        self._agent_runner = agent_runner

    async def create_chat(self, *, project_id: uuid.UUID, title: str) -> ThreadView:
        return await self._thread_view_repo.create(project_id=project_id, title=title)

    async def list_chats(self, project_id: uuid.UUID) -> list[ThreadView]:
        return await self._thread_view_repo.list_by_project(project_id)

    async def get_chat(self, thread_id: uuid.UUID) -> ChatDetail:
        thread_view = await self._thread_view_repo.get_by_id(thread_id)
        if thread_view is None:
            raise EntityNotFoundError("Chat", thread_id)
        messages = await self._agent_runner.get_history(thread_id=thread_id)
        return ChatDetail(thread_view=thread_view, messages=messages)

    async def list_recent(self, user_id: uuid.UUID, *, limit: int = 10) -> list[ThreadView]:
        return await self._thread_view_repo.list_recent(user_id, limit=limit)

    async def send_message(
        self,
        *,
        thread_id: uuid.UUID,
        project_id: uuid.UUID,
        user_id: uuid.UUID,
        content: str,
    ) -> AsyncIterator[StreamEvent]:
        """Stream agent response.

        IMPORTANT for API Layer (feat-005): this is an async generator —
        the body executes lazily on first __anext__(), not at call time.
        API must pre-validate chat existence BEFORE creating StreamingResponse
        to return a clean 404 instead of an error inside an already-opened stream.
        Validation here is defense in depth.
        """
        # Verify chat exists (defense in depth — see docstring)
        thread_view = await self._thread_view_repo.get_by_id(thread_id)
        if thread_view is None:
            raise EntityNotFoundError("Chat", thread_id)
        # Mark chat as active (updated_at) before streaming
        await self._thread_view_repo.touch(thread_view)
        # Delegate to agent
        async for event in self._agent_runner.stream(
            thread_id=thread_id,
            content=content,
            project_id=project_id,
            user_id=user_id,
        ):
            yield event

    async def cancel(self, *, thread_id: uuid.UUID) -> bool:
        return await self._agent_runner.cancel(thread_id=thread_id)
```

### `__init__.py`

```python
from app.services.agent_runner import AgentRunner, Message, StreamEvent, StubAgentRunner
from app.services.artifact import ArtifactService
from app.services.chat import ChatDetail, ChatService
from app.services.exceptions import EntityNotFoundError
from app.services.project import ProjectService
from app.services.sphere import SphereData, SphereService, StubSphereService

__all__ = [
    "AgentRunner",
    "ArtifactService",
    "ChatDetail",
    "ChatService",
    "EntityNotFoundError",
    "Message",
    "ProjectService",
    "SphereData",
    "SphereService",
    "StreamEvent",
    "StubAgentRunner",
    "StubSphereService",
]
```

## Изменения в существующих файлах

### repositories/thread_view.py — добавить метод `touch()`

```python
async def touch(self, thread_view: ThreadView) -> None:
    """Update updated_at without changing other fields."""
    thread_view.title = thread_view.title  # mark dirty to trigger onupdate
    await self._session.flush()
```

Расширение feat-003 репозитория. Необходимо для корректной работы `list_recent` (sidebar) — `updated_at` должен отражать последнюю активность чата.

## Порядок реализации

1. **repositories/thread_view.py** — добавить метод `touch()` (расширение feat-003)
2. **services/exceptions.py** — `EntityNotFoundError`
3. **services/agent_runner.py** — доменные типы (`StreamEvent`, `Message`) + `AgentRunner` Protocol + `StubAgentRunner`
4. **services/sphere.py** — `SphereData` + `SphereService` Protocol + `StubSphereService`
5. **services/project.py** — `ProjectService`
6. **services/artifact.py** — `ArtifactService`
7. **services/chat.py** — `ChatDetail` + `ChatService` (включая touch + docstring контракт)
8. **services/`__init__.py`** — re-exports
9. **`make check`** — ruff check + ruff format --check + mypy

## Обновление tasklist

После реализации — обновить `tasklist-backend-core.md`:
- feat-004 статус: 📋 Planned → 🚧 In Progress (при старте) → ✅ Done (после merge)
- Overview таблица: обновить статус
- Чекбоксы: отметить выполненные
- Артефакты: добавить ссылки на plan.md и summary.md

## Верификация

1. `make check` — ruff check + ruff format --check + mypy проходят
2. Ручная проверка:
   - ProjectService: create, get, list, update, delete
   - ArtifactService: get, list
   - ChatService: create_chat, list_chats, get_chat, list_recent, send_message, cancel
   - AgentRunner Protocol: stream, get_history, cancel
   - SphereService Protocol: get, update
   - StubAgentRunner и StubSphereService реализуют свои Protocol
   - EntityNotFoundError используется в сервисах
3. DI-паттерн: зависимости через конструктор во всех сервисах

## Post-implementation summary

В `summary.md` обязательно зафиксировать:
- Расширение feat-003: метод `touch()` добавлен в `ThreadViewRepository`
- Контракт async generator для feat-005: API Layer должен pre-validate перед StreamingResponse
- Любые другие отклонения от плана, принятые решения, нюансы

## Финальный шаг

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.
