# Технические соглашения

Практические соглашения по работе с репозиторием и кодом. Стек и обоснования — в [vision.md](../vision.md).

## Git

### Ветки

| Ветка | Назначение |
|-------|-----------|
| `main` | Стабильная версия, всегда рабочая |
| `develop` | Текущая разработка, интеграционная ветка |
| `<type>/<NNN>-<short-desc>` | Рабочие ветки от develop |

Типы рабочих веток — аналогично коммитам: `feat/`, `fix/`, `refactor/`, `chore/`, `docs/`.

Ветка привязана к итерации из tasklist: `<type>/<NNN>-<slug>`, где NNN — номер итерации в скоупе. Пример: `feat/001-api-layer`. При конфликте имён между скоупами — суффикс: `feat/001-api-layer-be`.

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
fix(api): handle SSE connection drop gracefully
chore: configure ruff and pre-commit
```

### Flow

```
feat/001-skills-system ──→ develop ──→ main
fix/002-sse-disconnect ──→ develop ──→ main
```

Рабочая ветка → PR в develop → code review → merge. Релиз: develop → PR в main.

## Структура проекта

uv workspace, monorepo. Конкретная структура директорий определяется в Phase C (Infrastructure Setup).

## Code Quality

Трёхуровневая защита:

| Уровень | Инструмент | Что ловит | Автофикс |
|---------|-----------|-----------|----------|
| 1 | ruff format | Визуальная консистентность | Полный |
| 2 | ruff check | Мёртвый код, антипаттерны | Частичный |
| 3 | mypy | Типовые несовместимости, None-access | Ручной |

**Frontend:** ESLint (`@typescript-eslint/recommended`) + Prettier.

**Pre-commit:** ruff check + ruff format + mypy. Enforcement gate перед каждым коммитом.

### Стратегия развития правил

Старт с MVP-каркаса (базовые наборы правил). Не пытаемся предусмотреть все кейсы заранее — правила дорабатываются итеративно по мере реальных проблем.

**Цикл улучшения:**

1. Столкнулись с проблемой (баг в проде, плохой код прошёл ревью, повторяющаяся ошибка)
2. Разобрались в причине — понять, что именно не поймали и почему
3. Проверили: решается ли это правилом линтера/типизации?
   - Да → добавить/включить правило, проверить на кодовой базе, зафиксировать
   - Нет → другой механизм (code review checklist, архитектурное решение, документация)
4. Убедились, что правило не создаёт шум (ложных срабатываний больше, чем пользы — откатить)

**Принципы:**
- Правило добавляется по факту проблемы, не "на всякий случай"
- `type: ignore` / `noqa` — только с комментарием причины, не для заглушки реальных багов
- Если правило стабильно мешает — убрать и задокументировать почему

Конкретные правила и конфигурация — в соответствующих конфиг-файлах (ruff.toml, pyproject.toml).

## Тестирование

Pytest. MVP без тестов — инфраструктура для запуска подготовлена (конфиг + директория), тесты добавляются после MVP.

## Docker

docker-compose для локальной разработки. Два режима запуска:

- **Docker** (`.env`) — полный стек в контейнерах
- **Local dev** (`.env.local`) — инфраструктура (PostgreSQL) в контейнерах, приложение локально

## Makefile

Dev-команды: docker-up/down/build, lint, format, type-check, check, lint-fe, format-fe, test, dev, dev-fe.

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
