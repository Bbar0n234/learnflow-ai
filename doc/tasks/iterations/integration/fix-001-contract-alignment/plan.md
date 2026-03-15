# Implementation Plan: fix-001 — Contract Alignment

## Context

Итерация fix-001 из `doc/tasks/tasklist-integration.md`. Цель: устранить расхождения между контрактами backend и frontend, обнаруженные при pre-integration аудите. Три проблемы: transient ArtifactCard, nullable mismatches, лишние create-response типы.

### Референсы

| Документ | Что берём |
|----------|-----------|
| [doc/workflow.md](doc/workflow.md) | Lifecycle итерации, артефакты |
| [doc/tech/conventions.md](doc/tech/conventions.md) | Git branch, commit format, code style |
| [doc/tech/backend.md](doc/tech/backend.md) | API schemas, SSE protocol, layered architecture |
| [doc/tech/frontend.md](doc/tech/frontend.md) | TypeScript types, state management, API modules |
| [doc/tasks/tasklist-integration.md](doc/tasks/tasklist-integration.md) | Состав работ, критерии приёмки |
| [Research: artifact-message binding](research agent output) | Patterns из Claude.ai, Open Canvas, Vercel; post-hoc linking |
| [Research: LangGraph timestamps](research agent output) | `additional_kwargs`, checkpointer сохраняет metadata |

### Быстро меняющиеся инструменты

| Инструмент | Релевантность для fix-001 | Проверка |
|-----------|--------------------------|----------|
| Docker / docker-compose | Не используется в этой итерации | — |
| Vite (proxy config) | Не используется в этой итерации | — |
| FastAPI (CORS, middleware) | Модификация schemas и routes — стабильный Pydantic API, не CORS/middleware | Версия fastapi>=0.135.1, pydantic>=2.0 — подтверждено |

### Решения архитектора

1. **Проблема 1 (ArtifactCard):** полноценная привязка артефакт → сообщение через post-hoc linking. Никаких временных решений.
2. **Проблема 1 (placement):** post-hoc update в ChatService (не в AgentRunner) — сохраняем чистоту слоёв.
3. **Проблема 1 (UX):** artifact cards inline в assistant-сообщении (в конце текста).
4. **Проблема 2 (created_at):** timestamps через `additional_kwargs` в LangChain messages.
5. **Проблема 2 (thread_id):** frontend `thread_id: string | null`.
6. **Проблема 3:** удалить `ProjectCreateResponse` / `ChatCreateResponse`, использовать полные типы.
7. **Doc updates:** актуализировать `backend.md` — POST responses с `updated_at`, `created_at` nullable, `thread_id` nullable.

---

## Шаг 0: Git branch

```bash
git fetch origin && git checkout -b fix/001-contract-alignment origin/develop
```

---

## Шаг 1: Artifact → Message binding (backend)

### 1.1 Модель — добавить `message_id` в Artifact

**Файл:** `backend/app/models/artifact.py`

Добавить поле:
```python
message_id: Mapped[str | None] = mapped_column(
    String(100), nullable=True, index=True,
)
```

Soft reference (строка), не FK — messages живут в LangGraph checkpointer, не в app-managed таблице. LangGraph message ID — строка типа `"lc_abc123..."`.

### 1.2 Alembic-миграция

```bash
cd backend && uv run alembic revision --autogenerate -m "add message_id to artifacts"
```

Проверить сгенерированный файл — должен содержать только `ADD COLUMN message_id VARCHAR(100)` + index.

### 1.3 ArtifactRepository — новые методы

**Файл:** `backend/app/repositories/artifact.py`

```python
async def set_message_id(self, artifact_ids: list[uuid.UUID], message_id: str) -> None:
    """Post-hoc: link artifacts to the final assistant message."""
    await self._session.execute(
        update(Artifact)
        .where(Artifact.id.in_(artifact_ids))
        .values(message_id=message_id)
    )
    await self._session.flush()

async def list_by_thread(self, thread_id: uuid.UUID) -> list[Artifact]:
    result = await self._session.execute(
        select(Artifact)
        .where(Artifact.thread_id == thread_id)
        .order_by(Artifact.created_at)
    )
    return list(result.scalars().all())
```

### 1.4 AgentRunner — метод для получения финального message_id

**Файл:** `backend/app/agent/runner.py`

```python
async def get_last_ai_message_id(self, *, thread_id: uuid.UUID) -> str | None:
    """Get ID of the last AIMessage without tool_calls (final user-facing message)."""
    config = {"configurable": {"thread_id": str(thread_id)}}
    state = await self._graph.aget_state(config)
    if not state.values:
        return None
    for m in reversed(state.values.get("messages", [])):
        if isinstance(m, AIMessage) and not getattr(m, "tool_calls", None):
            return str(m.id)
    return None
```

Обновить `AgentRunner` Protocol в `backend/app/services/agent_runner.py` — добавить метод.

### 1.5 ChatService — post-hoc linking + done event с message_id

**Файл:** `backend/app/services/chat.py`

Добавить `ArtifactRepository` как зависимость:
```python
class ChatService:
    def __init__(self, *, thread_view_repo, agent_runner, artifact_repo):
        self._thread_view_repo = thread_view_repo
        self._agent_runner = agent_runner
        self._artifact_repo = artifact_repo
```

Модифицировать `send_message()`:
```python
async def send_message(self, *, thread_id, project_id, user_id, content):
    artifact_ids: list[str] = []
    had_error = False

    async for event in self._agent_runner.stream(
        thread_id=thread_id, content=content,
        project_id=project_id, user_id=user_id,
    ):
        # Collect artifact IDs from stream events
        if event.type == "artifact_created":
            artifact_ids.append(event.data["id"])
        if event.type == "error":
            had_error = True
        yield event  # Forward all events from runner (runner no longer emits done)

    # error и done — взаимоисключающие терминальные события (SSE contract).
    # Если runner уже отправил error — не делаем post-hoc и не отправляем done.
    if had_error:
        return

    # Post-hoc: link artifacts to final message
    message_id: str | None = None
    try:
        if artifact_ids:
            message_id = await self._agent_runner.get_last_ai_message_id(
                thread_id=thread_id
            )
            if message_id:
                await self._artifact_repo.set_message_id(
                    [uuid.UUID(aid) for aid in artifact_ids],
                    message_id,
                )
    except Exception:
        # Post-hoc linking failure is non-critical:
        # artifacts remain linked to thread_id, just without message_id.
        # Don't break the stream — still emit done.
        logger.warning("Post-hoc artifact linking failed", exc_info=True)

    yield StreamEvent(type="done", data={"message_id": message_id or ""})
```

**Контракт:** `done` и `error` — mutually exclusive terminal events (`backend.md`). Runner emit-ит `error` при исключении. ChatService emit-ит `done` при успехе. Post-hoc linking обёрнут в try/except — его сбой не ломает стрим (артефакты остаются с `thread_id`).

### 1.6 AgentRunner.stream() — убрать yield done

**Файл:** `backend/app/agent/runner.py`

Удалить `yield StreamEvent(type="done", data={})` из `stream()` — done теперь emit-ится в ChatService. Runner отвечает только за graph events + error при исключении.

```python
# Было:
try:
    async for mode, data in self._graph.astream(...):
        ...
    yield StreamEvent(type="done", data={})    # УДАЛИТЬ
except Exception as e:
    yield StreamEvent(type="error", data={"detail": str(e)})  # Остаётся
```

### 1.7 deps.py — прокинуть ArtifactRepository в ChatService

**Файл:** `backend/app/api/deps.py`

```python
def get_chat_service(session: DBSession, request: Request) -> ChatService:
    return ChatService(
        thread_view_repo=ThreadViewRepository(session),
        agent_runner=request.app.state.agent_runner,
        artifact_repo=ArtifactRepository(session),  # NEW
    )
```

---

## Шаг 2: ChatDetail response — включить артефакты в сообщения

### 2.1 Backend schema — artifacts в MessageOut

**Файл:** `backend/app/api/schemas/chats.py`

```python
from app.api.schemas.artifacts import ArtifactListItem

class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime | None = None
    artifacts: list[ArtifactListItem] = []
```

### 2.2 Backend route — GET chat detail с артефактами

**Файл:** `backend/app/api/routes/chats.py`

В `get_chat()`:
- Инжектировать `ArtifactServiceDep`
- Запросить артефакты по thread_id через `artifact_service` (используя новый `list_by_thread`)
- Сгруппировать по `message_id`
- При формировании `MessageOut` — добавить matching artifacts

```python
@router.get("/projects/{project_id}/chats/{chat_id}", response_model=ChatDetailResponse)
async def get_chat(
    chat_id: uuid.UUID,
    project: UserProject,
    service: ChatServiceDep,
    artifact_service: ArtifactServiceDep,
) -> ChatDetailResponse:
    chat_detail = await service.get_chat(chat_id)
    if chat_detail.thread_view.project_id != project.id:
        raise HTTPException(status_code=404, detail="Chat not found")

    # Get artifacts for this thread, group by message_id
    artifacts = await artifact_service.list_by_thread(chat_id)
    artifacts_by_msg: dict[str | None, list] = {}
    for a in artifacts:
        artifacts_by_msg.setdefault(a.message_id, []).append(
            ArtifactListItem.model_validate(a)
        )

    return ChatDetailResponse(
        thread_id=chat_detail.thread_view.thread_id,
        title=chat_detail.thread_view.title,
        messages=[
            MessageOut(
                id=m.id, role=m.role, content=m.content,
                created_at=m.created_at,
                artifacts=artifacts_by_msg.get(m.id, []),
            )
            for m in chat_detail.messages
        ],
    )
```

### 2.3 ArtifactService — добавить list_by_thread

**Файл:** `backend/app/services/artifact.py`

```python
async def list_by_thread(self, thread_id: uuid.UUID) -> list[Artifact]:
    return await self._artifact_repo.list_by_thread(thread_id)
```

### 2.4 ArtifactDetailResponse — добавить message_id

**Файл:** `backend/app/api/schemas/artifacts.py`

```python
class ArtifactDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    title: str
    type: str
    content: str
    thread_id: uuid.UUID | None
    message_id: str | None = None  # NEW
    created_at: datetime
```

---

## Шаг 3: Message timestamps (backend)

### 3.1 HumanMessage — инжектировать created_at

**Файл:** `backend/app/agent/runner.py`

```python
from datetime import datetime, timezone
from langchain_core.messages import HumanMessage

# В stream():
input_msg = {"messages": [
    HumanMessage(
        content=content,
        additional_kwargs={"created_at": datetime.now(timezone.utc).isoformat()},
    )
]}
```

### 3.2 AIMessage — инжектировать created_at после LLM-вызова

**Файл:** `backend/app/agent/graph.py`

```python
from datetime import datetime, timezone

# В agent_node(), после LLM-вызова:
response = await bound_model.ainvoke([system, *trimmed])
response.additional_kwargs["created_at"] = datetime.now(timezone.utc).isoformat()
return {"messages": [*result_prefix, response]}
```

### 3.3 get_history() — извлекать created_at из additional_kwargs

**Файл:** `backend/app/agent/runner.py`

```python
from datetime import datetime

def _parse_created_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)

# В get_history():
Message(
    id=str(m.id),
    role="user" if isinstance(m, HumanMessage) else "assistant",
    content=m.content if isinstance(m.content, str) else "",
    created_at=_parse_created_at(m.additional_kwargs.get("created_at")),
)
```

### 3.4 Обратная совместимость

Старые сообщения без `additional_kwargs["created_at"]` → `created_at=None`. Schema `MessageOut.created_at: datetime | None = None` уже поддерживает это.

---

## Шаг 4: Frontend types — nullable fields

**Файл:** `frontend/src/shared/api/types.ts`

### 4.1 Message.created_at → nullable

```typescript
export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string | null;  // was: string
  artifacts: Artifact[];       // NEW
}
```

### 4.2 ArtifactDetail.thread_id → nullable

```typescript
export interface ArtifactDetail {
  id: string;
  title: string;
  type: string;
  content: string;
  thread_id: string | null;  // was: string
  message_id: string | null; // NEW
  created_at: string;
}
```

### 4.3 ChatDetail — включить artifacts

```typescript
// ChatDetail не меняется — artifacts теперь часть Message
export interface ChatDetail {
  thread_id: string;
  title: string;
  messages: Message[];
}
```

---

## Шаг 5: Frontend — удалить лишние create-response типы

**Файл:** `frontend/src/shared/api/types.ts`

Удалить:
```typescript
// DELETE:
export interface ProjectCreateResponse { ... }
export interface ChatCreateResponse { ... }
```

**Файл:** `frontend/src/shared/api/projects.ts`

```diff
- export async function createProject(data: CreateProjectRequest): Promise<ProjectCreateResponse> {
+ export async function createProject(data: CreateProjectRequest): Promise<Project> {
```

Обновить mock: возвращать полный `Project` с `updated_at`.

**Файл:** `frontend/src/shared/api/chats.ts`

```diff
- export async function createChat(projectId: string, data: CreateChatRequest): Promise<ChatCreateResponse> {
+ export async function createChat(projectId: string, data: CreateChatRequest): Promise<Chat> {
```

Обновить mock: возвращать полный `Chat` с `updated_at`.

---

## Шаг 6: Frontend — унификация artifact type naming + рендеринг

### 6.1 Унификация type/artifact_type

**Проблема:** SSE-протокол использует `artifact_type` (backend переименовывает `type → artifact_type` в `runner.py:95` чтобы не конфликтовать с `event.type`). Серверные данные (`Artifact`, `ArtifactListItem`) используют `type`. `ArtifactCard` и `StreamingArtifact` сейчас используют `artifact_type`.

**Решение:** привести `ArtifactCard` и `StreamingArtifact` к `type`. Маппинг `artifact_type → type` — в точке получения SSE-события.

**Файл:** `frontend/src/stores/stream-store.ts`

```diff
export interface StreamingArtifact {
  id: string;
  title: string;
- artifact_type: string;
+ type: string;
}
```

**Файл:** `frontend/src/features/chat/hooks/useAgentStream.ts`

```diff
case "artifact_created":
  addArtifact({
    id: event.id,
    title: event.title,
-   artifact_type: event.artifact_type,
+   type: event.artifact_type,  // SSE field → unified field
  });
```

**Файл:** `frontend/src/features/chat/components/ArtifactCard.tsx`

```diff
interface ArtifactCardProps {
- artifact: { id: string; title: string; artifact_type: string };
+ artifact: { id: string; title: string; type: string };
  projectId: string;
}

// В JSX:
- {artifact.artifact_type}
+ {artifact.type}
```

Теперь `ArtifactCard` принимает единый shape для streaming и persisted artifacts.

### 6.2 MessageItem — рендерить artifact cards

**Файл:** `frontend/src/features/chat/components/MessageItem.tsx`

Для assistant-сообщений с `message.artifacts.length > 0` — рендерить `ArtifactCard` компоненты в конце текста сообщения. `Artifact` type (из `types.ts`) содержит `{ id, title, type, created_at }` — совместим с обновлённым `ArtifactCard` props.

### 6.3 MessageList — streaming vs finalized artifacts

**Файл:** `frontend/src/features/chat/components/MessageList.tsx`

- Во время стрима: `streamingArtifacts` из Zustand store (как сейчас, но уже с `type` вместо `artifact_type`)
- После done + query invalidation: artifact cards из `message.artifacts[]` (серверные данные)

Переход бесшовный: после `endStream()` → query refetch → messages уже содержат `artifacts[]`.

### 6.4 Mock данные — добавить artifacts в messages

**Файл:** `frontend/src/shared/api/chats.ts`

Добавить `artifacts: []` к mock-сообщениям. Для одного-двух assistant-сообщений добавить mock artifact references.

### 6.5 Mock artifacts fallback — thread_id nullable

**Файл:** `frontend/src/shared/api/artifacts.ts`

Обновить fallback в `getArtifact()`: `thread_id: null` вместо `thread_id: ""`.

---

## Шаг 7: Doc updates

**Файл:** `doc/tech/backend.md`

### 7.1 Schemas — POST responses

```diff
POST /projects
-  Response: { id: UUID, name: str, created_at: datetime }
+  Response: { id: UUID, name: str, created_at: datetime, updated_at: datetime }

POST /projects/{id}/chats
-  Response: { thread_id: UUID, title: str, created_at: datetime }
+  Response: { thread_id: UUID, title: str, created_at: datetime, updated_at: datetime }
```

### 7.2 Schemas — Chat detail messages

```diff
GET /projects/{id}/chats/{cid}
-  Response: { thread_id, title, messages: [{ id, role, content, created_at }] }
+  Response: { thread_id, title, messages: [{ id, role, content, created_at?, artifacts: [{ id, title, type, created_at }] }] }
```

### 7.3 Schemas — Artifact detail

```diff
GET /projects/{id}/artifacts/{aid}
-  Response: { id, title, type, content, thread_id, created_at }
+  Response: { id, title, type, content, thread_id?, message_id?, created_at }
```

### 7.4 Persistence — Artifact model

```diff
Artifact
-├── id, project_id, thread_id, title, type, content, created_at
+├── id, project_id, thread_id, message_id, title, type, content, created_at
```

---

## Шаг 8: Верификация

### 8.1 Статический анализ

```bash
make lint && make type-check   # backend: ruff + mypy
make lint-fe                    # frontend: ESLint
cd frontend && npx tsc -b      # TypeScript strict
```

Все три команды — 0 ошибок.

### 8.2 Миграция

```bash
make docker-up                  # PostgreSQL
make migrate                    # alembic upgrade head
```

Проверить: колонка `message_id` VARCHAR(100) в таблице `artifacts`, nullable, с индексом.

### 8.3 E2E тест-кейсы (backend — с запущенным backend + LLM)

Предусловия: `make docker-up && make migrate && make dev` (backend запущен). Все запросы с header `X-User-Name: test`.

#### E2E-1: Artifact → message binding (happy path)

1. Создать проект: `POST /projects` → запомнить `project_id`
2. Создать чат: `POST /projects/{project_id}/chats` → запомнить `thread_id`
3. Отправить сообщение, провоцирующее создание артефакта: `POST /projects/{project_id}/chats/{thread_id}/messages` с `{"content": "Create a study plan for distributed systems and save it as an artifact"}`
4. Читать SSE-поток, проверить:
   - [ ] Поток содержит `text_chunk` events
   - [ ] Поток содержит `tool_start` event с `tool: "create_artifact"`
   - [ ] Поток содержит `tool_end` event
   - [ ] Поток содержит `artifact_created` event с `{id, title, artifact_type}`
   - [ ] Поток завершается `done` event с непустым `message_id`
   - [ ] После `done` нет других events
5. GET chat detail: `GET /projects/{project_id}/chats/{thread_id}`
   - [ ] Последнее assistant-сообщение имеет `artifacts: [{id, title, type, created_at}]`
   - [ ] `artifacts[0].id` совпадает с `id` из `artifact_created` SSE event
6. GET artifact detail: `GET /projects/{project_id}/artifacts/{artifact_id}`
   - [ ] `message_id` заполнен (строка типа `"lc_..."`)
   - [ ] `thread_id` совпадает с `thread_id` чата
   - [ ] `content` не пустой

#### E2E-2: Множественные артефакты в одном стриме

1. Использовать существующий проект/чат из E2E-1
2. Отправить сообщение: `{"content": "Create two artifacts: 1) an outline for the lecture, 2) a quiz with 5 questions. Save each as a separate artifact."}`
3. Читать SSE-поток, проверить:
   - [ ] Два `artifact_created` events (с разными `id`)
   - [ ] `done` event с `message_id`
4. GET chat detail:
   - [ ] Последнее assistant-сообщение имеет `artifacts` с 2 элементами
   - [ ] Оба artifact `id` совпадают с SSE events
5. GET каждый artifact detail:
   - [ ] У обоих одинаковый `message_id` (тот же, что в `done`)

#### E2E-3: Message timestamps

1. Использовать чат из E2E-1
2. GET chat detail → проверить messages:
   - [ ] Новые сообщения (созданные после изменений) имеют `created_at` с ISO datetime
   - [ ] `created_at` — разумная дата (не null, не epoch, не far future)
   - [ ] User messages и assistant messages оба имеют `created_at`

#### E2E-4: Стрим без артефактов

1. Создать новый чат
2. Отправить простой вопрос: `{"content": "What is the CAP theorem?"}`
3. Читать SSE-поток:
   - [ ] `text_chunk` events
   - [ ] `done` event (с пустым или отсутствующим `message_id` — артефактов не было)
   - [ ] Нет `artifact_created` events
4. GET chat detail:
   - [ ] Assistant message имеет `artifacts: []` (пустой массив)

#### E2E-5: Error handling — SSE contract

1. Спровоцировать ошибку (например, невалидный LLM API key или отключить LLM)
2. Отправить сообщение в чат
3. Проверить SSE-поток:
   - [ ] `error` event с `detail`
   - [ ] **Нет** `done` event после `error` (взаимоисключающие)
   - [ ] Соединение закрыто после `error`

#### E2E-6: Nullable fields — artifact detail без thread

1. Создать артефакт через чат (E2E-1)
2. Удалить чат (если endpoint есть) или напрямую: `DELETE` ThreadView → `SET NULL` на artifact.thread_id
3. GET artifact detail:
   - [ ] `thread_id: null`
   - [ ] Артефакт по-прежнему доступен (content, title — на месте)

#### E2E-7: REST contract — create response types

1. `POST /projects` с `{"name": "test"}`:
   - [ ] Response содержит `id`, `name`, `created_at`, `updated_at`
   - [ ] `updated_at` присутствует (не undefined/null)
2. `POST /projects/{id}/chats` с `{"title": "test chat"}`:
   - [ ] Response содержит `thread_id`, `title`, `created_at`, `updated_at`
   - [ ] `updated_at` присутствует

### 8.4 E2E тест-кейсы (frontend — mock mode, dev server)

Предусловия: `make dev-fe`, браузер.

#### FE-1: Artifact cards в финализированном чате (mock)

1. Открыть чат с mock-данными, где assistant-сообщение имеет `artifacts: [...]`
   - [ ] ArtifactCard рендерится inline в конце assistant-сообщения
   - [ ] Карточка показывает `title` и `type` (не пустые)
   - [ ] Клик на карточку → навигация на `/projects/{id}/artifacts/{aid}`

#### FE-2: Streaming artifact cards → finalized (mock)

1. Открыть чат, отправить сообщение (mock SSE)
2. Во время стрима:
   - [ ] ArtifactCard появляется inline при `artifact_created` event
   - [ ] Карточка показывает `title` и `type` (не `artifact_type`)
3. После done:
   - [ ] Query invalidation → chat refetch
   - [ ] Artifact card по-прежнему видна (теперь из серверных данных `message.artifacts[]`)
   - [ ] Карточка не мигает/не исчезает при transition

#### FE-3: TypeScript strict — nullable handling

1. `cd frontend && npx tsc -b` — 0 ошибок
2. Grep по коду: нет `ProjectCreateResponse`, нет `ChatCreateResponse`
3. `Message.created_at` — все использования проверяют на null
4. `ArtifactDetail.thread_id` — все использования проверяют на null

#### FE-4: Create project/chat — полные типы

1. Создать проект через UI (модалка)
   - [ ] Проект появляется в sidebar (данные из mock, включая `updated_at`)
   - [ ] Нет console errors
2. Создать чат через UI
   - [ ] Чат появляется в списке
   - [ ] Нет console errors

---

## Шаг 9: Артефакты итерации

- `doc/tasks/iterations/integration/fix-001-contract-alignment/plan.md` — этот план
- `doc/tasks/iterations/integration/fix-001-contract-alignment/summary.md` — после завершения
- Обновить статус в `doc/tasks/tasklist-integration.md`
- Обновить `doc/tech/backend.md` (шаг 7)

---

## Шаг 10: Финальный шаг

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.

---

## Файлы для модификации (сводка)

### Backend — модификация

| Файл | Изменение |
|------|-----------|
| `backend/app/models/artifact.py` | + `message_id` field |
| `backend/app/repositories/artifact.py` | + `set_message_id()`, `list_by_thread()` |
| `backend/app/services/artifact.py` | + `list_by_thread()` |
| `backend/app/services/agent_runner.py` | + `get_last_ai_message_id()` в Protocol |
| `backend/app/agent/runner.py` | + `get_last_ai_message_id()`, timestamps в HumanMessage, `created_at` в `get_history()`, убрать yield done |
| `backend/app/agent/graph.py` | + `created_at` в `additional_kwargs` после LLM-вызова |
| `backend/app/services/chat.py` | + `artifact_repo` dep, post-hoc linking в `send_message()`, emit done с message_id |
| `backend/app/api/deps.py` | + `ArtifactRepository` в `get_chat_service()` |
| `backend/app/api/schemas/chats.py` | + `artifacts` в `MessageOut` |
| `backend/app/api/schemas/artifacts.py` | + `message_id` в `ArtifactDetailResponse` |
| `backend/app/api/routes/chats.py` | + артефакты в GET chat detail, inject `ArtifactServiceDep` |

### Backend — новый файл

| Файл | Назначение |
|------|-----------|
| `backend/alembic/versions/xxx_add_message_id.py` | Alembic migration (autogenerate) |

### Frontend — модификация

| Файл | Изменение |
|------|-----------|
| `frontend/src/shared/api/types.ts` | `Message.created_at` nullable, `Message.artifacts`, `ArtifactDetail.thread_id` nullable, `ArtifactDetail.message_id`, удалить `*CreateResponse` |
| `frontend/src/shared/api/projects.ts` | `createProject` → `Promise<Project>`, обновить mock |
| `frontend/src/shared/api/chats.ts` | `createChat` → `Promise<Chat>`, обновить mock, `artifacts: []` в mock messages |
| `frontend/src/shared/api/artifacts.ts` | fallback `thread_id: null` |
| `frontend/src/stores/stream-store.ts` | `StreamingArtifact`: `artifact_type` → `type` |
| `frontend/src/features/chat/hooks/useAgentStream.ts` | маппинг `event.artifact_type` → `type` при `addArtifact` |
| `frontend/src/features/chat/components/ArtifactCard.tsx` | prop `artifact_type` → `type` |
| `frontend/src/features/chat/components/MessageItem.tsx` | + рендеринг `message.artifacts` через `ArtifactCard` |
| `frontend/src/features/chat/components/MessageList.tsx` | finalized artifacts из server data |

### Документация

| Файл | Изменение |
|------|-----------|
| `doc/tech/backend.md` | POST responses, nullable fields, message artifacts, Artifact model |
| `doc/tasks/tasklist-integration.md` | Статус fix-001 |
