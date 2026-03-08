---
name: uv-package-manager
description: >
  Управление Python-зависимостями через UV package manager.
  Используй когда: uv, uv sync, uv add, uv run, uv lock, uv pip,
  pyproject.toml, dependency-groups, optional-dependencies,
  workspace, монорепозиторий, monorepo, requirements.txt,
  pip compile, виртуальное окружение Python, venv, установка пакетов.
---

# UV Package Manager

## Обзор

UV — современный package manager для Python от Astral (авторы Ruff). Замена pip, pip-tools, poetry, pipenv. Написан на Rust, работает в 10-100x быстрее pip.

**Ключевые концепции:**
- `pyproject.toml` — источник истины для зависимостей
- `uv.lock` — lock-файл с точными версиями (рекомендуется вместо requirements.txt)
- `.venv` — виртуальное окружение (создаётся автоматически)

## Базовые команды

### Инициализация проекта

```bash
# Новый проект
uv init myproject
cd myproject

# Инициализация в существующей директории
uv init

# Создать как библиотеку (с src/ layout)
uv init --lib

# Создать пакет в workspace
uv init --package packages/mylib
```

### Управление зависимостями

```bash
# Добавить зависимость
uv add fastapi
uv add "httpx>=0.25"

# Добавить dev-зависимость (в группу dev)
uv add --dev pytest ruff mypy

# Добавить в произвольную группу
uv add --group docs sphinx mkdocs

# Добавить в optional-dependencies (для пользователей пакета)
uv add --optional postgres asyncpg

# Удалить зависимость
uv remove httpx

# Обновить зависимость
uv lock --upgrade-package fastapi
```

### Синхронизация окружения

```bash
# Синхронизировать все зависимости (создаёт .venv если нет)
uv sync

# Без dev-зависимостей
uv sync --no-dev

# С конкретной группой
uv sync --group docs

# Все группы
uv sync --all-groups

# Только указанная группа (без проекта)
uv sync --only-group test

# Для workspace — все пакеты
uv sync --all-packages

# Для workspace — конкретный пакет
uv sync --package backend
```

### Запуск команд

```bash
# Запуск в виртуальном окружении
uv run python script.py
uv run pytest
uv run ruff check .

# Запуск для конкретного пакета в workspace
uv run --package backend uvicorn app:main --reload

# Без dev-зависимостей
uv run --no-dev python script.py
```

### Lock-файл

```bash
# Обновить lock-файл
uv lock

# Обновить все зависимости
uv lock --upgrade

# Обновить конкретный пакет
uv lock --upgrade-package requests

# Проверить что lock актуален
uv lock --check
```

## Dependency Groups (PEP 735)

### Когда что использовать

| Тип | Публикуется в PyPI | Назначение |
|-----|-------------------|------------|
| `[project.dependencies]` | Да | Основные зависимости пакета |
| `[project.optional-dependencies]` | Да | Опциональные фичи для пользователей |
| `[dependency-groups]` | Нет | Dev-инструменты (test, lint, docs) |

### Синтаксис в pyproject.toml

```toml
[project]
dependencies = [
    "fastapi>=0.100",
    "pydantic>=2.0",
]

# Для пользователей пакета (pip install mypackage[postgres])
[project.optional-dependencies]
postgres = ["asyncpg>=0.29"]
redis = ["redis>=5.0"]

# Только для разработки (не публикуется)
[dependency-groups]
test = [
    "pytest>=8.0",
    "pytest-cov",
    "pytest-asyncio",
]
lint = [
    "ruff>=0.4",
    "mypy>=1.10",
]
docs = [
    "sphinx>=7.0",
    "mkdocs",
]
# Композиция групп
dev = [
    {include-group = "test"},
    {include-group = "lint"},
    "ipython",
]
```

### Команды для групп

```bash
# Добавление
uv add --dev pytest          # В группу dev
uv add --group lint ruff     # В группу lint
uv add --optional api httpx  # В optional-dependencies.api

# Синхронизация
uv sync                      # dev по умолчанию
uv sync --group docs         # + docs
uv sync --all-groups         # Все группы
uv sync --only-group test    # Только test
uv sync --no-dev             # Без dev
```

### Настройка default-groups

```toml
[tool.uv]
default-groups = ["dev"]  # Синхронизируются по умолчанию
```

## Workspaces (Монорепозитории)

### Конфигурация

**Корневой pyproject.toml:**

```toml
[project]
name = "my-monorepo"
version = "0.1.0"
requires-python = ">=3.12"

[tool.uv.workspace]
members = [
    "backend",
    "bot",
    "packages/*",
]
exclude = ["packages/deprecated"]

[dependency-groups]
dev = []
experiments = ["jupyterlab", "pandas"]
```

**Пакет в workspace:**

```toml
# backend/pyproject.toml
[project]
name = "backend"
version = "0.1.0"
dependencies = [
    "shared-lib",      # Зависимость от другого workspace member
    "fastapi>=0.100",
]

# ВАЖНО: указать что shared-lib из workspace
[tool.uv.sources]
shared-lib = { workspace = true }

[dependency-groups]
dev = ["pytest", "ruff", "mypy"]
```

### Команды для workspace

```bash
# Синхронизация всех пакетов
uv sync --all-packages

# Конкретный пакет
uv sync --package backend

# Запуск для конкретного пакета
uv run --package backend uvicorn app:main --reload
uv run --package bot python -m bot.main

# Сборка конкретного пакета
uv build --package backend

# Добавление зависимости в конкретный пакет
uv add --package backend httpx
```

### Типичная структура

```
my-monorepo/
├── pyproject.toml          # Workspace config
├── uv.lock                  # Единый lock-файл
├── .python-version
│
├── packages/
│   ├── core/
│   │   ├── pyproject.toml
│   │   └── src/core/
│   └── utils/
│       ├── pyproject.toml
│       └── src/utils/
│
├── services/
│   ├── backend/
│   │   ├── pyproject.toml
│   │   └── src/backend/
│   └── worker/
│       ├── pyproject.toml
│       └── src/worker/
│
└── Makefile
```

### Docker для workspace

```dockerfile
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Сначала только файлы конфигурации (кэширование)
COPY pyproject.toml uv.lock ./
COPY backend/pyproject.toml backend/

# Установить зависимости без проекта
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package backend --no-install-project --frozen

# Затем код
COPY backend/src backend/src

# Установить проект
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package backend --frozen

CMD ["uv", "run", "--package", "backend", "uvicorn", "backend.main:app"]
```

## Работа с requirements.txt

### Когда использовать

- **uv.lock** — рекомендуется для всех проектов с UV
- **requirements.txt** — совместимость с системами без UV (CI, Docker)

### Генерация из pyproject.toml

```bash
# uv pip compile (pip-tools стиль)
uv pip compile pyproject.toml -o requirements.txt

# С extras
uv pip compile pyproject.toml --extra dev -o requirements-dev.txt

# С группами
uv pip compile pyproject.toml --group test -o requirements-test.txt

# С хешами (безопасность)
uv pip compile pyproject.toml --generate-hashes -o requirements.txt

# Кросс-платформенный
uv pip compile pyproject.toml --universal -o requirements.txt
```

### Экспорт из uv.lock

```bash
# Экспорт в requirements.txt
uv export --format requirements.txt -o requirements.txt

# Без dev
uv export --format requirements.txt --no-dev -o requirements.txt

# Для конкретного пакета workspace
uv export --format requirements.txt --package backend -o requirements.txt
```

### Установка из requirements.txt

```bash
# Установить (не удаляет лишние)
uv pip install -r requirements.txt

# Синхронизировать (удаляет лишние)
uv pip sync requirements.txt
```

### pip-совместимый интерфейс

```bash
# Полный pip-совместимый интерфейс
uv pip install fastapi
uv pip install -e .
uv pip freeze > requirements.txt
uv pip list
uv pip show fastapi
uv pip uninstall fastapi
```

## Типичные Makefile команды

```makefile
.PHONY: install lint format typecheck test run-backend

install:  ## Установить все зависимости
	uv sync --all-packages

lint:  ## Проверить код
	uv run ruff check .

lint-fix:  ## Автоисправление
	uv run ruff check . --fix

format:  ## Форматирование
	uv run ruff format .

typecheck:  ## Проверка типов
	uv run mypy backend bot

test:  ## Запуск тестов
	uv run pytest -v

run-backend:  ## Запуск backend
	uv run --package backend uvicorn backend.main:app --reload

run-bot:  ## Запуск bot
	uv run --package bot python -m bot.main

# Комплексная проверка
check: format lint typecheck test
	@echo "All checks passed!"
```

## Полезные команды

```bash
# Информация о пакете
uv pip show fastapi

# Дерево зависимостей
uv tree
uv tree --package backend

# Очистка кэша
uv cache clean

# Python версии
uv python list
uv python install 3.13
uv python pin 3.13

# Создать venv явно
uv venv
uv venv --python 3.13

# Информация о проекте
uv version
```

## Troubleshooting

### Lock-файл устарел

```bash
# Ошибка: "Resolved requirements are not up to date"
uv lock
uv sync
```

### Конфликт версий

```bash
# Посмотреть почему конфликт
uv lock -v

# Принудительно обновить
uv lock --upgrade
```

### Проблемы с кэшем

```bash
uv cache clean
uv sync --refresh
```

### Workspace пакет не находится

```toml
# Убедиться что в обоих местах:
# 1. В dependencies
dependencies = ["shared-lib"]

# 2. В sources
[tool.uv.sources]
shared-lib = { workspace = true }
```

### Debug режим

```bash
uv sync -v      # Verbose
uv sync -vv     # Very verbose
UV_LOG=debug uv sync
```

## Миграция

### С pip на UV

```bash
# Импорт из requirements.txt
uv add -r requirements.txt

# С сохранением версий
uv add -r requirements.txt -c requirements.txt
```

### С Poetry на UV

```bash
# UV понимает poetry.lock
uv sync  # Автоматически конвертирует
```
