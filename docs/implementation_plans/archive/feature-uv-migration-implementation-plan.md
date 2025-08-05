# Feature: Migration from Poetry to UV - Implementation Plan

## Архитектура решения

Проект будет мигрирован на **UV workspace** с архитектурой множественных пакетов для разделения функциональности bot и learnflow компонентов, аналогично успешному подходу из существующего UV проекта.

### Целевая структура

```
learnflow-ai/
├── pyproject.toml              # Root workspace configuration
├── uv.lock                     # Unified lockfile for entire workspace
├── bot/                        # learnflow-bot package
│   ├── pyproject.toml         # Bot-specific dependencies
│   ├── __init__.py
│   ├── __main__.py
│   └── main.py
├── learnflow/                  # learnflow-core package
│   ├── pyproject.toml         # Core-specific dependencies
│   └── ...
└── Makefile                   # Workflow automation
```

## API и интерфейсы

### 1. Root Workspace Configuration
**Файл**: `pyproject.toml` (корневой)
- **Назначение**: Конфигурация UV workspace с указанием пакетов-членов
- **Содержимое**: Секция `[tool.uv.workspace]` с members = ["bot", "learnflow"]
- **Особенности**: Минимальная конфигурация, без зависимостей

### 2. Bot Package Configuration
**Файл**: `bot/pyproject.toml`
- **Назначение**: Конфигурация бота с Telegram-специфичными зависимостями
- **Dependency Groups**:
  - `prod`: aiogram, telegramify-markdown, pydantic-settings
  - `dev`: ruff, black, mypy
  - `test`: pytest, pytest-asyncio
- **Python**: `>=3.11`

### 3. Learnflow Package Configuration
**Файл**: `learnflow/pyproject.toml`
- **Назначение**: Конфигурация основного AI/ML функционала
- **Dependency Groups**:
  - `prod`: langgraph, fastapi, uvicorn, langchain, langchain-openai, pillow, и др.
  - `dev`: ruff, black, mypy
  - `test`: pytest, pytest-asyncio, httpx[testing]
- **Python**: `>=3.11`

### 4. Makefile Automation
**Файл**: `Makefile`
- **Назначение**: Автоматизация команд разработки
- **Методы**:
  - `install`: полная установка всех зависимостей
  - `sync-bot` / `sync-learnflow`: синхронизация конкретного пакета
  - `run-bot` / `run-learnflow`: запуск сервисов
  - `test-bot` / `test-learnflow` / `test-all`: тестирование
  - `lint` / `format`: проверка кода

## Взаимодействие компонентов

### 1. Dependency Resolution
- UV создает единый `uv.lock` файл для всего workspace
- Конфликты зависимостей разрешаются на уровне workspace
- Общие зависимости (например, pydantic-settings) используются в одной версии

### 2. Package Isolation
- Каждый пакет имеет независимую конфигурацию
- Bot пакет изолирован от AI/ML зависимостей learnflow
- Возможность запуска и разработки пакетов независимо

### 3. Cross-Package Dependencies
- При необходимости learnflow пакет может зависеть от bot пакета через workspace dependencies
- Использование `uv run --package` для выполнения команд в контексте конкретного пакета

## Edge Cases и особенности

### 1. Конфликты версий Python
- Текущий проект требует `>=3.13`
- Необходимо проверить совместимость всех зависимостей с Python 3.13
- При конфликтах - понижение требований до `>=3.11`

### 2. Миграция существующих скриптов
- Docker файлы нужно обновить для использования UV
- CI/CD пайплайны требуют изменения команд установки
- Существующие запуск команды через `python -m` сохраняются

### 3. Dependency Groups Migration
- Poetry группы `tool.poetry.group.bot` → UV `[dependency-groups] prod`
- Poetry группы `tool.poetry.group.learnflow` → UV `[dependency-groups] prod`
- Добавление новых групп `dev` и `test` для каждого пакета

### 4. Lock File Migration
- `poetry.lock` удаляется
- `uv.lock` создается автоматически при первом `uv sync`
- Возможные различия в resolved версиях зависимостей

## Технологии

### Инструменты миграции
- **UV CLI**: Основной инструмент управления зависимостями
- **Make**: Автоматизация workflow команд
- **Docker**: Обновление образов для использования UV

### Dependency Groups Strategy
- **Production**: Минимальный набор для runtime
- **Development**: Linting, formatting, type checking
- **Testing**: Pytest и тестовые утилиты

### Docker Integration
- Использование официального UV Docker image: `ghcr.io/astral-sh/uv:python3.13-bookworm-slim`
- Установка только production зависимостей в контейнерах
- Команды запуска через `uv run`

## Порядок реализации

### Этап 1: Подготовка workspace структуры
1. Создание корневого `pyproject.toml` с workspace конфигурацией
2. Создание `bot/pyproject.toml` и `learnflow/pyproject.toml`
3. Перенос зависимостей из Poetry групп в UV dependency groups

### Этап 2: Миграция зависимостей
1. Анализ текущих зависимостей в `poetry.lock`
2. Создание UV конфигурации с аналогичными зависимостями
3. Первичный `uv sync` и решение конфликтов

### Этап 3: Автоматизация и тестирование
1. Создание `Makefile` с основными командами
2. Тестирование запуска обоих пакетов
3. Проверка корректности dependency resolution

### Этап 4: Обновление инфраструктуры
1. Обновление Docker файлов
2. Обновление документации
3. Удаление Poetry файлов

### Этап 5: Валидация
1. Сравнение функциональности до и после миграции
2. Проверка performance (время установки, размер окружения)
3. Тестирование CI/CD пайплайнов

## Критерии готовности

- ✅ Оба пакета успешно устанавливаются через `uv sync`
- ✅ Bot запускается через `uv run --package learnflow-bot`
- ✅ Learnflow API запускается через `uv run --package learnflow-core`
- ✅ Все тесты проходят в новом окружении
- ✅ Docker образы успешно собираются с UV
- ✅ Makefile команды работают корректно
- ✅ Удалены Poetry файлы (pyproject.toml Poetry секции, poetry.lock)