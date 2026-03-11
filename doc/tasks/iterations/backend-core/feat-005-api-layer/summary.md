# Post-Implementation Summary: feat-005 — API Layer (REST + SSE)

## Результат

Реализация в целом соответствует плану. API Layer полностью функционален — все endpoints, SSE-стриминг, auth dependency, PDF-экспорт, CORS. Попутно исправлены инфраструктурные проблемы, обнаруженные при интеграции.

## Что сделано

### Новые файлы (14)

- `api/deps.py` — FastAPI dependencies: session, user auth, service factories, project ownership
- `api/export.py` — PDF-конвертация: Markdown -> HTML (markdown + mdx_math) -> PDF (pdfkit)
- `api/schemas/projects.py` — Pydantic schemas для projects
- `api/schemas/chats.py` — Pydantic schemas для chats, messages (response), recent
- `api/schemas/messages.py` — Pydantic schemas для messages (request), cancel
- `api/schemas/artifacts.py` — Pydantic schemas для artifacts
- `api/schemas/sphere.py` — Pydantic schemas для sphere
- `api/schemas/__init__.py` — реэкспорт всех публичных схем
- `api/routes/projects.py` — Router: projects CRUD (prefix="/projects")
- `api/routes/chats.py` — Router: chats + recent (без prefix, full paths)
- `api/routes/messages.py` — Router: SSE messages + cancel
- `api/routes/artifacts.py` — Router: artifacts list/detail/download
- `api/routes/sphere.py` — Router: sphere get/update
- `api/routes/__init__.py` — реэкспорт всех routers

### Изменения в существующих файлах (8)

- `config.py` — добавлено `cors_origins`, убраны `env_file` и `extra="ignore"` (рефакторинг env)
- `main.py` — router registration, CORS middleware, EntityNotFoundError exception handler
- `backend/pyproject.toml` — добавлены зависимости: markdown, python-markdown-math, pdfkit; mypy config перенесён в корень
- `Dockerfile` — apt-get install wkhtmltopdf
- `Makefile` — LOAD_ENV pattern, alembic через `-c backend/alembic.ini`
- `pyproject.toml` (root) — перенесён [tool.mypy] из backend, добавлен types-Markdown в dev deps
- `repositories/project.py` — добавлен `session.refresh()` после update
- `repositories/thread_view.py` — добавлен `session.refresh()` после update и touch

## Отклонения от плана

### 1. Рефакторинг env-конфигурации

**План:** добавить `cors_origins` в Settings, остальное без изменений.

**Реализация:** полный рефакторинг подхода к env-файлам, согласованный с архитектором.

**Причина:** при интеграции обнаружилась цепочка проблем — порт 5432 занят другим проектом, CWD-зависимость при запуске alembic из `cd backend`, pydantic-settings подтягивал Docker-only переменные из `.env`.

**Решение:**
- Settings читает только `os.environ` + дефолты (без `env_file`)
- `.env` — базовая конфигурация (infra + app), читается docker-compose и Makefile
- `.env.local` — только переопределения для локального режима (обычно только `DATABASE_URL`)
- Makefile: `LOAD_ENV` загружает `.env` (база) затем `.env.local` (overrides) в shell env
- Alembic запускается из корня через `-c backend/alembic.ini` вместо `cd backend &&`

### 2. Перенос mypy config в корневой pyproject.toml

**План:** mypy overrides для pdfkit/mdx_math в `backend/pyproject.toml`.

**Реализация:** весь `[tool.mypy]` перенесён в корневой `pyproject.toml`.

**Причина:** mypy запускается из корня (`uv run mypy backend/`), ищет конфиг в CWD — не находил `backend/pyproject.toml`. Предсуществующий баг, проявился при добавлении pdfkit без type stubs.

### 3. session.refresh() после update в репозиториях

**План:** не предусмотрено (проблема в нижнем слое).

**Реализация:** добавлен `await session.refresh()` после flush в `ProjectRepository.update`, `ThreadViewRepository.update` и `ThreadViewRepository.touch`.

**Причина:** `onupdate=func.now()` генерирует значение на стороне БД. После flush SQLAlchemy помечает `updated_at` как expired. Pydantic's `model_validate(from_attributes=True)` обращается к атрибуту синхронно -> MissingGreenlet (lazy load в sync контексте).

## Верификация

- `make check` (ruff + mypy) — чисто
- `make migrate` — работает через LOAD_ENV
- 19 curl-тестов: auth (401), CRUD projects, chats (create/list/detail/recent), SSE stream, cancel, sphere (get/put), artifacts, 404/422, ownership verification (cross-project access -> 404), delete (204)
