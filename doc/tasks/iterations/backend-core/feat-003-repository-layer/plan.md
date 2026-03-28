# Implementation Plan: feat-003 — Repository Layer

## Context

Итерация feat-003 из tasklist-backend-core: async CRUD-репозитории для каждой app-managed сущности. Blocked-by зависимость feat-002 (ORM-модели + Alembic) — выполнена. Репозитории — нижний уровень data access, используются Service Layer и Agent tools напрямую.

## Референсы

| Документ | Назначение |
|----------|-----------|
| [workflow.md](../../../../workflow.md) | Процесс итерации |
| [conventions.md](../../../tech/conventions.md) | Git, naming, code quality |
| [tasklist-backend-core.md](../../tasklist-backend-core.md) | Описание итерации feat-003 |
| [backend.md](../../../tech/backend.md) | Архитектура, API schemas, persistence |

## Верифицированные версии инструментов

| Инструмент | Версия | API проверен через |
|-----------|--------|-------------------|
| SQLAlchemy | 2.0.48 | `inspect` пакета |
| AsyncSession | — | `execute`, `get`, `add`, `delete`, `flush`, `scalars`, `refresh` |
| `implicit_returning` | `True` | server_default values доступны после flush |

FastAPI, Alembic, Pydantic — не задействованы в этой итерации (нет новых эндпоинтов, миграций, схем).

## Шаг 0: Ветка

```bash
git fetch origin && git checkout -b feat/003-repository-layer origin/develop
```

Ветка: `feat/003-repository-layer` (conventions.md: `<type>/<NNN>-<short-desc>`).

## Дизайн репозиториев

### Общие паттерны

- **Конструктор:** `__init__(self, session: AsyncSession)` — session через DI, без базового класса (4 репозитория, overhead абстракции не оправдан)
- **Мутации:** `session.add()` + `session.flush()` после create/update/delete. Flush записывает в БД в рамках текущей транзакции, но не коммитит. Server-default значения (`created_at`, `updated_at`) доступны через RETURNING (PostgreSQL). **Commit — ответственность Service Layer.**
- **Чтение:** get_by_id возвращает `Entity | None` (404 — решение Service/API Layer). Списки — `list[Entity]`.
- **Типизация:** все методы полностью аннотированы (mypy `disallow_untyped_defs = true`)

### Файлы

```
backend/app/repositories/
├── __init__.py          # re-export всех репозиториев
├── user.py              # UserRepository
├── project.py           # ProjectRepository
├── thread_view.py       # ThreadViewRepository
└── artifact.py          # ArtifactRepository
```

---

### UserRepository (`user.py`)

```python
class UserRepository:
    def __init__(self, session: AsyncSession) -> None: ...

    async def get_by_id(self, user_id: uuid.UUID) -> User | None
        # session.get(User, user_id)

    async def get_or_create(self, name: str) -> User
        # PostgreSQL INSERT ON CONFLICT DO NOTHING (атомарный upsert):
        #   pg_insert(User).values(name=name)
        #       .on_conflict_do_nothing(index_elements=["name"])
        # Если conflict → DO NOTHING (без ошибки), затем SELECT для получения existing row.
        # Если нет conflict → INSERT, flush.
        # Атомарно на уровне БД, без rollback, транзакция остаётся чистой.
```

---

### ProjectRepository (`project.py`)

```python
class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None: ...

    async def create(self, *, user_id: uuid.UUID, name: str) -> Project
        # Project(user_id=user_id, name=name), add, flush

    async def get_by_id(self, project_id: uuid.UUID) -> Project | None
        # session.get(Project, project_id)

    async def list_by_user(self, user_id: uuid.UUID) -> list[Project]
        # select(Project).where(Project.user_id == user_id)
        #     .order_by(Project.updated_at.desc())

    async def update(self, project: Project, *, name: str) -> Project
        # project.name = name, flush
        # updated_at обновится через onupdate=func.now()

    async def delete(self, project: Project) -> None
        # session.delete(project), flush
        # CASCADE удалит связанные thread_views и artifacts
```

---

### ThreadViewRepository (`thread_view.py`)

```python
class ThreadViewRepository:
    def __init__(self, session: AsyncSession) -> None: ...

    async def create(self, *, project_id: uuid.UUID, title: str) -> ThreadView
        # ThreadView(project_id=project_id, title=title), add, flush

    async def get_by_id(self, thread_id: uuid.UUID) -> ThreadView | None
        # session.get(ThreadView, thread_id)

    async def list_by_project(self, project_id: uuid.UUID) -> list[ThreadView]
        # select(ThreadView).where(ThreadView.project_id == project_id)
        #     .order_by(ThreadView.updated_at.desc())

    async def list_recent(self, user_id: uuid.UUID, *, limit: int = 10) -> list[ThreadView]
        # JOIN с Project для фильтрации по user_id
        # select(ThreadView)
        #     .join(ThreadView.project)
        #     .where(Project.user_id == user_id)
        #     .options(contains_eager(ThreadView.project))
        #     .order_by(ThreadView.updated_at.desc())
        #     .limit(limit)
        #
        # contains_eager: project уже загружен через JOIN, не нужен отдельный запрос.
        # API /chats/recent возвращает project_id + project_name → service достанет из thread_view.project.

    async def update(self, thread_view: ThreadView, *, title: str) -> ThreadView
        # thread_view.title = title, flush

    async def delete(self, thread_view: ThreadView) -> None
        # session.delete(thread_view), flush
```

---

### ArtifactRepository (`artifact.py`)

```python
class ArtifactRepository:
    def __init__(self, session: AsyncSession) -> None: ...

    async def create(
        self, *, project_id: uuid.UUID, title: str, type: str, content: str,
        thread_id: uuid.UUID | None = None,
    ) -> Artifact
        # Artifact(...), add, flush

    async def get_by_id(self, artifact_id: uuid.UUID) -> Artifact | None
        # session.get(Artifact, artifact_id)

    async def list_by_project(self, project_id: uuid.UUID) -> list[Artifact]
        # select(Artifact).where(Artifact.project_id == project_id)
        #     .order_by(Artifact.created_at.desc())

    async def delete(self, artifact: Artifact) -> None
        # session.delete(artifact), flush
```

Примечание: API не определяет PUT/PATCH для артефактов (создаются агентом, иммутабельны после создания), поэтому метод `update` не реализуется. CRUD из описания итерации покрыт: Create + Read + Delete.

---

### `__init__.py`

Re-export всех репозиториев:
```python
from app.repositories.artifact import ArtifactRepository
from app.repositories.project import ProjectRepository
from app.repositories.thread_view import ThreadViewRepository
from app.repositories.user import UserRepository

__all__ = ["UserRepository", "ProjectRepository", "ThreadViewRepository", "ArtifactRepository"]
```

## Порядок реализации

1. **UserRepository** — самый простой, отработка паттерна (конструктор, get, get_or_create)
2. **ProjectRepository** — CRUD + list, стандартный паттерн
3. **ThreadViewRepository** — CRUD + list_by_project + list_recent (JOIN)
4. **ArtifactRepository** — CRD + list
5. **`__init__.py`** — обновить re-exports
6. **`make check`** — ruff check + ruff format --check + mypy

## Обновление tasklist

После реализации — обновить `tasklist-backend-core.md`:
- feat-003 статус: 📋 Planned → 🚧 In Progress (при старте) → ✅ Done (после merge)
- Overview таблица: обновить статус
- Чекбоксы: отметить выполненные
- Артефакты: добавить ссылку на plan.md и summary.md

## Верификация

1. `make check` — ruff check + ruff format --check + mypy проходят
2. Ручная проверка: все методы из состава работ реализованы
   - UserRepository: get_by_id, get_or_create
   - ProjectRepository: create, get_by_id, list_by_user, update, delete
   - ThreadViewRepository: create, get_by_id, list_by_project, list_recent, update, delete
   - ArtifactRepository: create, get_by_id, list_by_project, delete
3. Паттерн DI: session через конструктор во всех репозиториях

## Финальный шаг

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.
