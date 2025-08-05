# UV Dependency Management - Comprehensive Overview

## 🏗️ Архитектура проекта

Проект использует **UV workspace** с архитектурой множественных пакетов для разделения функциональности и изоляции зависимостей.

### Структура workspace

```
aiseller/
├── pyproject.toml              # Root workspace configuration
├── uv.lock                     # Unified lockfile for entire workspace
├── app/                        # aiseller-bot package
│   ├── pyproject.toml         # Bot-specific dependencies
│   └── ...
├── api/                        # aiseller-api package  
│   ├── pyproject.toml         # API-specific dependencies
│   └── ...
└── Makefile                   # Workflow automation
```

## 📦 UV Workspace Configuration

### Root Configuration (`pyproject.toml`)

```toml
[tool.uv.workspace]
members = [
    "app",     # aiseller-bot package
    "api"      # aiseller-api package  
]
```

**Ключевые особенности:**
- **Unified lockfile**: Один `uv.lock` файл для всего workspace
- **Cross-package dependencies**: Пакеты могут зависеть друг от друга
- **Shared development tools**: Общие инструменты разработки для всех пакетов
- **Consistent versioning**: Одинаковые версии зависимостей across packages

## 🎯 Изоляция пакетов

### Package 1: aiseller-bot (`app/`)

```toml
[project]
name = "aiseller-bot"
version = "0.2.0"
description = "AISeller Telegram Bot with AI-powered conversations"
requires-python = ">=3.11"
dependencies = []  # Managed by UV commands

[dependency-groups]
prod = [
    "aiohttp>=3.12.15",
    "asyncpg>=0.30.0", 
    "dependency-injector>=4.48.1",
    "langchain>=0.3.27",
    "langchain-openai>=0.3.28",
    "langgraph>=0.6.1",
    "langgraph-checkpoint-postgres>=2.0.23",
    "loguru>=0.7.3",
    "openai>=1.97.1",
    "psycopg>=3.2.9",
    "pymupdf>=1.26.3",
    "python-dateutil>=2.9.0.post0",
    "python-dotenv>=1.1.1",
    "python-telegram-bot>=22.3",
]
dev = [
    "black>=25.1.0",
    "isort>=6.0.1", 
    "mypy>=1.17.0",
    "ruff>=0.12.7",
]
test = [
    "pytest>=8.4.1",
    "pytest-asyncio>=1.1.0",
]
```

### Package 2: aiseller-api (`api/`)

```toml
[project]
name = "aiseller-api"
version = "0.4.0"
description = "AISeller API backend"
requires-python = ">=3.10"
dependencies = []  # Managed by UV commands

[dependency-groups]
prod = [
    "aiosqlite>=0.21.0",
    "alembic>=1.16.4",
    "asyncpg>=0.30.0",
    "email-validator>=2.2.0",
    "fastapi>=0.116.1",
    "fastapi-users[sqlalchemy]>=14.0.1",
    "greenlet>=3.2.3",
    "passlib[bcrypt]>=1.7.4",
    "psycopg>=3.2.9",
    "pydantic>=2.11.7",
    "pydantic-settings>=2.10.1",
    "python-dateutil>=2.9.0.post0",
    "python-jose>=3.5.0",
    "python-multipart>=0.0.20",
    "pyyaml>=6.0.2",
    "sqlalchemy>=2.0.42",
    "structlog>=25.4.0",
    "uvicorn>=0.35.0",
]
dev = [
    "black>=25.1.0",
    "mypy>=1.17.0",
    "ruff>=0.12.7",
    "types-passlib>=1.7.7.20250602",
    "types-python-jose>=3.5.0.20250531",
    "types-pyyaml>=6.0.12.20250516",
]
test = [
    "httpx>=0.28.1",
    "pytest>=8.4.1",
    "pytest-asyncio>=1.1.0",
    "pytest-cov>=6.2.1",
    "testcontainers[postgres]>=4.12.0",
]
```

## 🔧 Dependency Groups Strategy

### 1. Production Dependencies (`prod`)
- **Назначение**: Зависимости, требуемые в production environment
- **Принцип**: Минимальный набор для функционирования приложения
- **Управление**: `uv sync --group prod`

### 2. Development Dependencies (`dev`)
- **Назначение**: Инструменты для разработки (linting, formatting, type checking)
- **Принцип**: Не включаются в production builds
- **Управление**: `uv sync --group dev`

### 3. Test Dependencies (`test`)
- **Назначение**: Зависимости для тестирования
- **Принцип**: Изолированы от production и development
- **Управление**: `uv sync --group test`

### 4. Combined Groups
```bash
# Установка всех групп разом
uv sync --group dev --group test

# Или через multiple groups
uv sync --extra dev
```

## 🛠️ Workflow Commands

### Package-Specific Operations

```makefile
# Синхронизация зависимостей конкретного пакета
sync-api:
	uv sync --package aiseller-api

sync-bot:
	uv sync --package aiseller-bot

# Запуск сервисов
run-api:
	uv run --package aiseller-api uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

run-bot:
	uv run --package aiseller-bot python -m app.main

# Тестирование
test-api:
	uv run --package aiseller-api pytest api/tests/

test-bot:
	uv run --package aiseller-bot pytest tests/

# Линтинг
lint:
	uv run --package aiseller-bot ruff check .
	uv run --package aiseller-api ruff check api/

# Форматирование
format:
	uv run --package aiseller-bot black .
	uv run --package aiseller-api black api/
```

### Global Operations

```makefile
# Установка всех зависимостей
install:
	uv sync

# Установка с dev зависимостями
install-dev:
	uv sync --group dev

# Production установка
prod-install:
	uv sync --package aiseller-bot --group prod
	uv sync --package aiseller-api --group prod

# Полное тестирование
test-all:
	uv run pytest
```

## 🎯 Принципы изоляции

### 1. Package-Level Isolation
- **Отдельные namespace**: `aiseller-bot` vs `aiseller-api`
- **Независимые версии**: Каждый пакет имеет свою версию
- **Специфичные зависимости**: Каждый пакет декларирует только необходимые зависимости

### 2. Environment Isolation
- **Virtual Environment**: UV автоматически создает изолированное окружение
- **Dependency Resolution**: UV разрешает конфликты зависимостей на уровне workspace
- **Lock File**: Единый uv.lock обеспечивает reproducible builds

### 3. Group-Level Isolation
```bash
# Только production зависимости
uv sync --group prod

# Только dev инструменты
uv sync --group dev  

# Только тестовые зависимости
uv sync --group test

# Комбинирование групп
uv sync --group prod --group test
```

## 📁 Структура зависимостей

### Bot Package Dependencies (AI/ML focused)
```
aiseller-bot/
├── AI/ML Stack:
│   ├── langchain>=0.3.27          # LLM framework
│   ├── langchain-openai>=0.3.28   # OpenAI integration
│   ├── langgraph>=0.6.1           # Workflow graphs
│   └── openai>=1.97.1             # OpenAI API client
├── Database:
│   ├── asyncpg>=0.30.0           # PostgreSQL async driver
│   └── psycopg>=3.2.9            # PostgreSQL sync driver
├── Bot Framework:
│   └── python-telegram-bot>=22.3 # Telegram Bot API
└── Utilities:
    ├── aiohttp>=3.12.15          # HTTP client
    ├── loguru>=0.7.3             # Logging
    └── pymupdf>=1.26.3           # PDF processing
```

### API Package Dependencies (Web/API focused)
```
aiseller-api/
├── Web Framework:
│   ├── fastapi>=0.116.1          # Modern web framework
│   ├── uvicorn>=0.35.0           # ASGI server
│   └── python-multipart>=0.0.20 # Form data handling
├── Database:
│   ├── sqlalchemy>=2.0.42        # ORM
│   ├── alembic>=1.16.4           # Migrations
│   ├── asyncpg>=0.30.0           # PostgreSQL async
│   └── aiosqlite>=0.21.0         # SQLite async
├── Authentication:
│   ├── fastapi-users[sqlalchemy]>=14.0.1  # User management
│   ├── python-jose>=3.5.0        # JWT handling
│   └── passlib[bcrypt]>=1.7.4    # Password hashing
└── Validation:
    ├── pydantic>=2.11.7          # Data validation
    ├── pydantic-settings>=2.10.1 # Settings management
    └── email-validator>=2.2.0    # Email validation
```

## 🔄 Development Workflow

### 1. Initial Setup
```bash
# Клонирование и настройка
git clone <repo>
cd aiseller
make dev-setup  # = uv sync --group dev
```

### 2. Development Cycle
```bash
# Работа с конкретным пакетом
make sync-bot                    # Синхронизация зависимостей бота
make run-bot                     # Запуск бота
make test-bot                    # Тестирование бота

# Работа с API
make sync-api                    # Синхронизация зависимостей API
make run-api                     # Запуск API сервера
make test-api                    # Тестирование API
```

### 3. Code Quality Workflow
```bash
# Линтинг всего проекта
make lint                        # Проверка обоих пакетов

# Форматирование
make format                      # Форматирование обоих пакетов

# Типизация
make check                       # MyPy проверка
```

### 4. Testing Workflow
```bash
# Модульные тесты
make test-bot                    # Тесты бота
make test-api                    # Тесты API
make test-all                    # Все тесты

# С coverage
uv run pytest --cov=app --cov-report=html
```

## 🚀 Production Deployment

### Docker Integration
```dockerfile
# Используется UV для установки зависимостей
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# Копирование конфигурации
COPY pyproject.toml uv.lock ./

# Установка только production зависимостей
RUN uv sync --group prod --no-dev

# Запуск через uv
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Production Commands
```bash
# Production установка (только необходимые зависимости)
uv sync --group prod

# Запуск конкретного пакета в production
uv run --package aiseller-api uvicorn app.main:app --host 0.0.0.0 --port 8000
uv run --package aiseller-bot python -m app.main
```

## 🔍 Мониторинг зависимостей

### Dependency Tree
```bash
# Просмотр дерева зависимостей
uv tree

# Для конкретного пакета
uv tree --package aiseller-api
```

### Security & Updates
```bash
# Обновление зависимостей
uv sync --upgrade

# Обновление конкретного пакета
uv upgrade fastapi

# Аудит безопасности (через дополнительные инструменты)
uv run safety check
```

## 🎯 Best Practices

### 1. Dependency Management
- ✅ **Version Pinning**: Используйте `>=version` для гибкости
- ✅ **Group Separation**: Четкое разделение prod/dev/test зависимостей
- ✅ **Regular Updates**: Регулярное обновление зависимостей
- ✅ **Security Auditing**: Периодический аудит безопасности

### 2. Package Design
- ✅ **Single Responsibility**: Каждый пакет имеет четкую функцию
- ✅ **Minimal Dependencies**: Только необходимые зависимости
- ✅ **Clear Interfaces**: Четкие интерфейсы между пакетами
- ✅ **Independent Versioning**: Независимое версионирование пакетов

### 3. Development Workflow
- ✅ **Package-Specific Commands**: Используйте `--package` для изоляции
- ✅ **Group-Specific Installation**: Устанавливайте только нужные группы
- ✅ **Automated Testing**: Автоматизация через Makefile
- ✅ **Consistent Environment**: Используйте `uv.lock` для воспроизводимости

## 📋 Quick Reference

### Essential Commands
```bash
# Workspace management
uv sync                                    # Sync all packages
uv sync --group dev                        # Sync with dev dependencies
uv sync --package aiseller-api            # Sync specific package

# Package operations  
uv run --package aiseller-api pytest      # Run command in package context
uv add --package aiseller-api fastapi     # Add dependency to specific package

# Development
make install-dev                          # Full development setup
make test-all                             # Run all tests
make lint                                 # Code quality checks
```

### Directory Structure for Your Project
```
your-project/
├── pyproject.toml              # Root workspace config
│   └── [tool.uv.workspace]
│       └── members = ["package1", "package2"]
├── uv.lock                     # Unified lockfile
├── package1/                   # First package
│   ├── pyproject.toml         # Package-specific config
│   │   ├── [project] name = "your-package1"
│   │   └── [dependency-groups]
│   │       ├── prod = [...]
│   │       ├── dev = [...]
│   │       └── test = [...]
│   └── src/
└── package2/                   # Second package
    ├── pyproject.toml         # Package-specific config
    └── src/
```

Эта архитектура обеспечивает максимальную гибкость, изоляцию и управляемость зависимостей в проектах любой сложности.