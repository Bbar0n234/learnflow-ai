# Post-Implementation Summary: feat-002 — SQLAlchemy Models + Alembic Migrations

## Результат

Реализация соответствует плану. Все критерии приёмки выполнены.

## Что сделано

- `models/base.py` — DeclarativeBase, отдельный модуль для чистого импорта
- `models/user.py` — User (id UUID PK, name unique, created_at)
- `models/project.py` — Project (id UUID PK, user_id FK CASCADE, name, created_at, updated_at)
- `models/thread_view.py` — ThreadView (thread_id UUID PK, project_id FK CASCADE, title, created_at, updated_at)
- `models/artifact.py` — Artifact (id UUID PK, project_id FK CASCADE, thread_id FK SET NULL nullable, title, type, content, created_at)
- `models/__init__.py` — реэкспорт всех моделей
- Alembic: `alembic.ini` (URL из Settings — SSOT), `alembic/env.py` (async, metadata из Base)
- Initial migration: `4512c02eeb05_create_app_tables.py` — 4 таблицы, FK, indexes
- Makefile: `migrate`, `migration`, `downgrade` targets
- Зависимость: `alembic>=1.15` в pyproject.toml (установилась 1.18.4)

## Отклонения от плана

### TYPE_CHECKING imports для forward references

**План:** forward references через строковые аннотации (`Mapped["Project"]`).

**Проблема:** ruff F821 — модели в отдельных файлах, строка `"Project"` в `user.py` не резолвится статическим анализатором (класс `Project` определён в другом модуле).

**Решение:** добавлены `from __future__ import annotations` + `TYPE_CHECKING` блоки с условными импортами. Стандартный паттерн для SQLAlchemy моделей в отдельных файлах — импорты выполняются только для статического анализа, в рантайме SQLAlchemy резолвит строковые ссылки через свой mapper registry.

## Версии установленных пакетов

| Пакет | Версия |
|-------|--------|
| Alembic | 1.18.4 |
| SQLAlchemy | 2.0.48 |

## Верификация

- `alembic upgrade head` — создаёт 4 таблицы (users, projects, thread_views, artifacts) + alembic_version
- `alembic downgrade base` — все app-таблицы удалены
- FK constraints проверены через `\d artifacts`:
  - `artifacts_project_id_fkey` → projects(id) ON DELETE CASCADE
  - `artifacts_thread_id_fkey` → thread_views(thread_id) ON DELETE SET NULL
- Indexes: ix_projects_user_id, ix_thread_views_project_id, ix_artifacts_project_id, ix_artifacts_thread_id
- `make check` (ruff check + ruff format --check + mypy) — всё проходит
