# Технические соглашения

Практические соглашения по работе с репозиторием и кодом. Стек и обоснования — в [vision.md](../vision.md).

## Git

### Ветки

| Ветка | Назначение |
|-------|-----------|
| `main` | Стабильная версия, всегда рабочая |
| `develop` | Текущая разработка, интеграционная ветка |
| `<type>/<short-desc>` | Рабочие ветки от develop |

Типы рабочих веток — аналогично коммитам: `feat/`, `fix/`, `refactor/`, `chore/`, `docs/`.

Merge в develop — через PR. Merge в main — через PR из develop.

### Коммиты

Conventional Commits:

```
<type>(<scope>): <описание>
```

- **type:** `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `style`
- **scope** (опционально): `agent`, `api`, `frontend`, `db`, `infra`
- **описание:** lowercase, без точки в конце, императив

Примеры:
```
feat(agent): add ReAct loop with tool calling
fix(api): handle WebSocket disconnect gracefully
chore: configure ruff and pre-commit
```

### Flow

```
feature/add-skills ──→ develop ──→ main
fix/ws-disconnect  ──→ develop ──→ main
```

Рабочая ветка → PR в develop → code review → merge. Релиз: develop → PR в main.

## Структура проекта

uv workspace, monorepo. Конкретная структура директорий определяется в Phase C (Infrastructure Setup).

## Code Quality

- **Ruff** — линтер + форматер (заменяет flake8, isort, black)
- **Mypy** — статическая типизация
- **Pre-commit** — хуки перед коммитом (ruff, mypy)

Конфигурация (правила, настройки, порядок хуков) определяется в Phase C.

## Тестирование

Pytest. Структура и правила покрытия определяются в Phase C.

## Docker

docker-compose для локальной разработки. Сервисы и конфигурация определяются в Phase C.

## Makefile

Dev-команды (lint, test, run, docker, ...). Набор команд определяется в Phase C.

## Именование

**Python:** PEP 8.

| Элемент | Стиль | Пример |
|---------|-------|--------|
| Модули | snake_case | `knowledge_sphere.py` |
| Классы | PascalCase | `AgentRuntime` |
| Функции, методы | snake_case | `load_skill()` |
| Константы | UPPER_SNAKE | `MAX_CONTEXT_TOKENS` |
| Переменные | snake_case | `current_session` |

**Файлы:** snake_case (`agent_runtime.py`, `test_routes.py`).

**Директории:** snake_case (`knowledge_sphere/`, `api/`).

**Документация:** kebab-case для составных имён (`doc-transfer-plan.md`), lowercase для простых (`backend.md`).
