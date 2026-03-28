# Implementation Plan: feat-002 — SQLAlchemy Models + Alembic Migrations

## Context

Итерация feat-001 создала скелет приложения: FastAPI app factory, pydantic-settings конфиг, async engine + session factory. Следующий шаг — ORM-модели для app-managed таблиц и инфраструктура миграций через Alembic. Это фундамент для Repository Layer (feat-003).

## Референсы

| Документ | Что берём |
|----------|-----------|
| [doc/tech/backend.md](../../doc/tech/backend.md) | Persistence: схема таблиц, связи, Module Structure |
| [doc/tech/conventions.md](../../doc/tech/conventions.md) | Git branch naming, commit format, code style |
| [doc/workflow.md](../../doc/workflow.md) | Lifecycle итерации, артефакты |
| [doc/tasks/tasklist-backend-core.md](../../doc/tasks/tasklist-backend-core.md) | Состав работ, критерии приёмки |
| feat-001 summary | Текущий код, версии пакетов |

## Версии инструментов (проверено)

| Инструмент | Версия | Заметки |
|-----------|--------|---------|
| SQLAlchemy | 2.0.48 | Declarative 2.0 API (Mapped, mapped_column, DeclarativeBase) |
| Pydantic | 2.12.5 | — |
| pydantic-settings | 2.13.1 | — |
| Alembic | не установлен | Добавляем в зависимости |
| psycopg (async) | 3.3.3 | `postgresql+psycopg://` — совместим с async_engine_from_config |

## Решения архитектора

**Artifact.thread_id — ondelete:** `SET NULL` + nullable. Артефакт принадлежит проекту (основной родитель), thread_id — контекст создания. При удалении чата артефакт выживает, thread_id обнуляется.

---

## Шаги реализации

### 0. Git branch

```bash
git fetch origin && git checkout -b feat/002-models-migrations origin/develop
```

Ветка: `feat/002-models-migrations` (из tasklist, по conventions.md).

### 1. Добавить Alembic в зависимости

**Файл:** `backend/pyproject.toml`

```
dependencies = [
    ...
    "alembic>=1.15",
]
```

Затем `uv sync` для установки.

### 2. Создать Base class

**Файл (новый):** `backend/app/models/base.py`

DeclarativeBase — отдельный модуль для чистого импорта из моделей и из Alembic env.py.

```python
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

### 3. ORM-модели

**Файл (новый):** `backend/app/models/user.py`

```python
class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    projects: Mapped[list["Project"]] = relationship(back_populates="user", cascade="all, delete-orphan")
```

**Файл (новый):** `backend/app/models/project.py`

```python
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user: Mapped["User"] = relationship(back_populates="projects")
    thread_views: Mapped[list["ThreadView"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="project", cascade="all, delete-orphan")
```

**Файл (новый):** `backend/app/models/thread_view.py`

```python
class ThreadView(Base):
    __tablename__ = "thread_views"

    thread_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="thread_views")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="thread_view")
```

**Файл (новый):** `backend/app/models/artifact.py`

```python
class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    thread_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("thread_views.thread_id", ondelete="SET NULL"), index=True, nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    type: Mapped[str] = mapped_column(String(50))  # "markdown" | расширяемо
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="artifacts")
    thread_view: Mapped["ThreadView | None"] = relationship(back_populates="artifacts")
```

**Файл:** `backend/app/models/__init__.py` — реэкспорт для удобного импорта:

```python
from app.models.base import Base
from app.models.user import User
from app.models.project import Project
from app.models.thread_view import ThreadView
from app.models.artifact import Artifact

__all__ = ["Base", "User", "Project", "ThreadView", "Artifact"]
```

### 4. Alembic init

```bash
cd backend && uv run alembic init -t async alembic
```

Создаст `backend/alembic.ini` и `backend/alembic/` (env.py, script.py.mako, versions/).

### 5. Настроить Alembic

**Файл:** `backend/alembic.ini`

- Оставить `sqlalchemy.url =` пустым (URL берём из Settings в env.py для SSOT).

**Файл:** `backend/alembic/env.py`

Ключевые изменения в сгенерированном шаблоне:

1. Импортировать `Base.metadata` как `target_metadata`
2. Читать DB URL из `app.config.Settings` вместо alembic.ini
3. Передать URL в `config.set_main_option("sqlalchemy.url", settings.database_url)`

Паттерн из документации Alembic (async template уже содержит `run_async_migrations` + `connection.run_sync`):

```python
from app.models import Base  # noqa: F401 — ensure all models registered
from app.config import Settings

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    settings = Settings()
    url = settings.database_url
    context.configure(url=url, target_metadata=target_metadata, ...)
    ...

async def run_async_migrations() -> None:
    settings = Settings()
    config.set_main_option("sqlalchemy.url", settings.database_url)
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    ...
```

### 6. Сгенерировать initial migration

```bash
cd backend && uv run alembic revision --autogenerate -m "create app tables"
```

Проверить сгенерированный файл в `backend/alembic/versions/` — убедиться, что все 4 таблицы, FK, indexes присутствуют.

### 7. Makefile targets

**Файл:** `Makefile` — добавить:

```makefile
migrate:  ## Run alembic upgrade head
	cd backend && uv run alembic upgrade head

migration:  ## Create new alembic migration (autogenerate)
	cd backend && uv run alembic revision --autogenerate -m "$(msg)"

downgrade:  ## Run alembic downgrade (one step)
	cd backend && uv run alembic downgrade -1
```

### 8. Верификация (критерии приёмки)

```bash
# 1. Миграция создаёт все таблицы
make docker-up          # PostgreSQL
make migrate            # alembic upgrade head
# Проверить: таблицы users, projects, thread_views, artifacts существуют

# 2. Откат работает
cd backend && uv run alembic downgrade base
# Проверить: таблицы удалены

# 3. FK constraints корректны
make migrate
# Проверить через psql: \d artifacts — FK на projects и thread_views

# 4. Линтеры проходят
make check              # ruff check + ruff format --check + mypy
```

### 9. Артефакты итерации

- `doc/tasks/iterations/backend-core/feat-002-models-migrations/plan.md` — этот план (копия)
- `doc/tasks/iterations/backend-core/feat-002-models-migrations/summary.md` — после завершения
- Обновить статус в `tasklist-backend-core.md`

### 10. Финальный шаг

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.
