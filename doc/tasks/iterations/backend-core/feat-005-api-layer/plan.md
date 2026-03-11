# Implementation Plan: feat-005 — API Layer (REST + SSE каркас)

## Context

Итерация feat-005 — финальный слой бэкенд-каркаса. Все нижние слои готовы: модели (feat-002), репозитории (feat-003), сервисы с Protocol-интерфейсами для агента и шара (feat-004). Цель — HTTP-интерфейс приложения: REST endpoints, SSE-стриминг, auth dependency, PDF-экспорт артефактов, CORS.

## Референсы

- [doc/workflow.md](../../doc/workflow.md) — рабочий процесс, формат итераций
- [doc/tech/conventions.md](../../doc/tech/conventions.md) — git flow, именование, code quality
- [doc/tasks/tasklist-backend-core.md](../../doc/tasks/tasklist-backend-core.md) — исходный таск-лист
- [doc/tech/backend.md](../../doc/tech/backend.md) — архитектура API, schemas, SSE protocol, persistence
- [doc/tasks/iterations/backend-core/feat-004-service-layer/summary.md](../../doc/tasks/iterations/backend-core/feat-004-service-layer/summary.md) — контракты из предыдущей итерации

## Шаг 0: Ветка

```bash
git fetch origin && git checkout -b feat/005-api-layer origin/develop
```

## Шаг 1: Config — CORS origins

**Файл:** `backend/app/config.py`

Добавить поле `cors_origins: list[str]` в `Settings`. Default: `["http://localhost:3000", "http://localhost:5173"]` (стандартные порты фронтенд dev-серверов). Настраивается через env var `CORS_ORIGINS` (JSON-список).

## Шаг 2: deps.py — FastAPI Dependencies

**Файл:** `backend/app/api/deps.py`

Центральное место wiring — связывает API Layer с нижними слоями через FastAPI Depends.

### Dependencies:

1. **`get_db_session()`** — `AsyncGenerator[AsyncSession]`, yield session from `request.app.state.session_factory()`, commit on success, rollback on error, close always.

2. **`get_current_user()`** — извлечение `X-User-Name` header, `get_or_create` через `UserRepository`. Без заголовка → 401. Возвращает ORM `User`.

3. **Service factories** (каждый — отдельная dependency-функция):
   - `get_project_service(session)` → `ProjectService(project_repo=ProjectRepository(session))`
   - `get_artifact_service(session)` → `ArtifactService(artifact_repo=ArtifactRepository(session))`
   - `get_chat_service(session)` → `ChatService(thread_view_repo=ThreadViewRepository(session), agent_runner=StubAgentRunner())`
   - `get_sphere_service()` → `StubSphereService()`

4. **`get_user_project()`** — dependency для всех project-scoped endpoints: принимает `project_id` из path, `current_user` из deps; проверяет что проект существует и принадлежит пользователю (project.user_id == user.id). Иначе 404. Возвращает ORM `Project`.

### Верификация принадлежности вложенных ресурсов к проекту

Помимо `get_user_project` (проект принадлежит пользователю), роутеры **обязаны** проверять, что вложенный ресурс принадлежит проекту из URL. Без этого `GET /projects/{A}/chats/{chat_from_B}` вернёт чат из чужого проекта — API-контракт нарушен.

**Подход:** проверка в роутере после получения ресурса — `resource.project_id == project.id`, иначе 404. Не меняем сервисный слой — проверка на уровне API Layer (его зона ответственности):
- **chats:** `chat_detail.thread_view.project_id == project.id`
- **messages (SSE, cancel):** pre-validate через `ThreadViewRepository.get_by_id()`, затем `thread_view.project_id == project.id`
- **artifacts:** `artifact.project_id == project.id`
- **sphere:** `project_id` берётся из validated project (get_user_project), передаётся в SphereService напрямую — проверка не нужна

## Шаг 3: Pydantic Schemas

**Директория:** `backend/app/api/schemas/`

Все schema-файлы по одному на ресурс. Общие соглашения из backend.md:
- UUID для всех ID
- Списки в обёртке `{ items: [...] }`
- `ConfigDict(from_attributes=True)` для маппинга из ORM-моделей

### schemas/projects.py
- `ProjectCreate(name: str)`
- `ProjectUpdate(name: str)`
- `ProjectResponse(id: UUID, name: str, created_at: datetime, updated_at: datetime)` — from_attributes
- `ProjectListResponse(items: list[ProjectResponse])`

### schemas/chats.py
- `ChatCreate(title: str | None = None)` — default "New Chat"
- `ChatResponse(thread_id: UUID, title: str, created_at: datetime, updated_at: datetime)` — from_attributes
- `ChatListResponse(items: list[ChatResponse])`
- `ChatRecentItem(thread_id: UUID, title: str, project_id: UUID, project_name: str, updated_at: datetime)`
- `ChatRecentResponse(items: list[ChatRecentItem])`
- `MessageOut(id: str, role: str, content: str, created_at: datetime | None = None)`
- `ChatDetailResponse(thread_id: UUID, title: str, messages: list[MessageOut])`

### schemas/messages.py
- `MessageCreate(content: str)`
- `CancelResponse(ok: bool)`

### schemas/artifacts.py
- `ArtifactListItem(id: UUID, title: str, type: str, created_at: datetime)` — from_attributes
- `ArtifactListResponse(items: list[ArtifactListItem])`
- `ArtifactDetailResponse(id: UUID, title: str, type: str, content: str, thread_id: UUID | None, created_at: datetime)` — from_attributes

### schemas/sphere.py
- `SphereUpdate(content: str)`
- `SphereResponse(project_id: UUID, content: str, updated_at: datetime)`

### schemas/__init__.py
Re-export всех публичных имён.

## Шаг 4: Routers

**Директория:** `backend/app/api/routes/`

Один файл на ресурс.

**Стратегия префиксов:** роутеры с единым базовым путём используют `APIRouter(prefix=...)`. Роутеры с routes под разными путями (chats: `/projects/.../chats/...` + `/chats/recent`) используют **full paths без prefix** — явно и читаемо, никакой магии с множественным include.

### routes/projects.py — `APIRouter(prefix="/projects", tags=["projects"])`
- `POST /` → `ProjectService.create_project`
- `GET /` → `ProjectService.list_projects`
- `GET /{project_id}` → через `get_user_project` dep
- `PUT /{project_id}` → `ProjectService.update_project`
- `DELETE /{project_id}` → 204 No Content

### routes/chats.py — `APIRouter(tags=["chats"])`, **без prefix**
- `POST /projects/{project_id}/chats` → `ChatService.create_chat`
- `GET /projects/{project_id}/chats` → `ChatService.list_chats`
- `GET /projects/{project_id}/chats/{chat_id}` → `ChatService.get_chat` + **проверка** `thread_view.project_id == project.id`
- `GET /chats/recent` → `ChatService.list_recent` (query param `limit: int = 10`)

### routes/messages.py — `APIRouter(tags=["messages"])`, **без prefix**
- `POST /projects/{project_id}/chats/{chat_id}/messages` → SSE stream + **проверка** thread принадлежит project
- `POST /projects/{project_id}/chats/{chat_id}/cancel` → `ChatService.cancel` + **проверка**

### routes/artifacts.py — `APIRouter(tags=["artifacts"])`, **без prefix**
- `GET /projects/{project_id}/artifacts` → `ArtifactService.list_artifacts`
- `GET /projects/{project_id}/artifacts/{artifact_id}` → `ArtifactService.get_artifact` + **проверка** `artifact.project_id == project.id`
- `GET /projects/{project_id}/artifacts/{artifact_id}/download` → query param `format: md | pdf` + **проверка**

### routes/sphere.py — `APIRouter(tags=["sphere"])`, **без prefix**
- `GET /projects/{project_id}/sphere` → `SphereService.get` (project_id из validated project)
- `PUT /projects/{project_id}/sphere` → `SphereService.update`

### routes/__init__.py
Импорт всех routers для удобной регистрации.

## Шаг 5: SSE Streaming (POST /messages)

**Подход:** plain `StreamingResponse` из Starlette с `media_type="text/event-stream"`. Без sse-starlette — протокол type-in-data простой, доп. зависимость не оправдана.

**Wire format:** `data: {"type": "...", ...payload}\n\n` — каждое событие на отдельной строке.

**Реализация в routes/messages.py:**
1. Pre-validate: chat существует (через `ChatService.get_chat` или direct repo check) — **до** создания StreamingResponse (контракт из feat-004 summary)
2. Async generator: маппит `StreamEvent` → SSE wire format: `f"data: {json.dumps({'type': event.type, **event.data})}\n\n"`
3. `StreamingResponse(event_generator(), media_type="text/event-stream")` — headers: `Cache-Control: no-cache`, `X-Accel-Buffering: no`

## Шаг 6: PDF-экспорт артефактов

**Endpoint:** `GET /projects/{project_id}/artifacts/{artifact_id}/download?format=md|pdf`

- `format=md` → `Response` с `Content-Disposition: attachment; filename="{title}.md"`, `media_type="text/markdown"`
- `format=pdf` → конвертация Markdown→HTML→PDF, `Response` с `Content-Disposition: attachment`, `media_type="application/pdf"`

**Стек конвертации (решение архитектора):** pdfkit + wkhtmltopdf + markdown

**Pipeline:** Markdown → HTML (`markdown` lib + `mdx_math` для LaTeX-формул) → PDF (`pdfkit.from_string()` → wkhtmltopdf)

**Реализация:** утилитная функция `convert_md_to_pdf(content: str) -> bytes` в отдельном модуле `app/api/export.py`:
1. `markdown.markdown(content, extensions=["mdx_math"])` → HTML
2. Обёртка в HTML-шаблон с MathJax CDN для рендеринга формул
3. `pdfkit.from_string(html, False, options={"javascript-delay": 5000})` → PDF bytes

**Pip-зависимости** (`backend/pyproject.toml`):
- `markdown>=3.5`
- `python-markdown-math>=0.8`
- `pdfkit>=1.0.0`

**System dependency** (`Dockerfile`):
- `apt-get install -y wkhtmltopdf`

## Шаг 7: Exception Handling

**Файл:** `backend/app/main.py`

Зарегистрировать exception handler для `EntityNotFoundError` → HTTP 404:
```python
@app.exception_handler(EntityNotFoundError)
async def entity_not_found_handler(request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})
```

## Шаг 8: CORS Middleware

**Файл:** `backend/app/main.py`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Для доступа к settings в create_app: передать через параметр или загрузить напрямую.

## Шаг 9: Router Registration

**Файл:** `backend/app/main.py`

```python
from app.api.routes import projects, chats, messages, artifacts, sphere
app.include_router(projects.router)
app.include_router(chats.router)
app.include_router(messages.router)
app.include_router(artifacts.router)
app.include_router(sphere.router)
```

## Шаг 10: Верификация

1. `make check` (ruff check + ruff format --check + mypy) — всё зелёное
2. `make docker-up` → `make migrate` → `make dev`
3. Ручная проверка endpoints через curl:
   - `POST /projects` (с X-User-Name header) → 200
   - `GET /projects` → 200, `{ items: [] }`
   - Полный CRUD-цикл projects
   - `POST /projects/{id}/chats` → создание чата
   - `POST /projects/{id}/chats/{cid}/messages` → SSE stream с stub-ответом
   - `GET /chats/recent` → список
   - `GET /projects/{id}/sphere` → stub-данные
   - Запрос без X-User-Name → 401
   - Запрос несуществующего ресурса → 404
   - Невалидный payload → 422
   - `GET /projects/{A}/chats/{chat_from_B}` → 404 (верификация принадлежности)
   - `GET /projects/{A}/artifacts/{artifact_from_B}` → 404

## Шаг 11: Post-implementation

- Дождаться ревью и обратной связи от архитектора перед коммитом и пушем

## Новые файлы (summary)

| Файл | Назначение |
|------|-----------|
| `api/deps.py` | Dependencies: session, user, services, project ownership |
| `api/schemas/projects.py` | Pydantic schemas для projects |
| `api/schemas/chats.py` | Pydantic schemas для chats + messages (response) |
| `api/schemas/messages.py` | Pydantic schemas для messages (request, cancel) |
| `api/schemas/artifacts.py` | Pydantic schemas для artifacts |
| `api/schemas/sphere.py` | Pydantic schemas для sphere |
| `api/schemas/__init__.py` | Re-exports |
| `api/routes/projects.py` | Router: projects CRUD |
| `api/routes/chats.py` | Router: chats + recent |
| `api/routes/messages.py` | Router: SSE messages + cancel |
| `api/routes/artifacts.py` | Router: artifacts list/detail/download |
| `api/routes/sphere.py` | Router: sphere get/update |
| `api/routes/__init__.py` | Router imports |
| `api/export.py` | PDF-конвертация: Markdown → HTML → PDF (pdfkit) |

## Модифицируемые файлы

| Файл | Изменение |
|------|-----------|
| `config.py` | + cors_origins |
| `main.py` | + router registration, CORS middleware, exception handler |
| `backend/pyproject.toml` | + PDF dependency |
| `Dockerfile` | + system deps для PDF |

---

## Решённые вопросы

- **PDF-конвертация:** pdfkit + wkhtmltopdf + markdown (решение архитектора на основе опыта предыдущего проекта)
