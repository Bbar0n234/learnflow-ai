# Технические соглашения

Практические соглашения по работе с репозиторием и кодом. Стек и обоснования — в [vision.md](../vision.md).

## Git

### Ветки

| Ветка | Назначение |
|-------|-----------|
| `main` | Стабильная версия, всегда рабочая |
| `develop` | Текущая разработка, интеграционная ветка |
| `<scope>/<type>-<NNN>-<slug>` | Рабочие ветки от develop |

Scope — краткий код области работы. Типы — аналогично коммитам: `feat`, `fix`, `refactor`, `chore`, `docs`.

| Scope | Код |
|-------|-----|
| backend-core | `be` |
| frontend | `fe` |
| agent | `ag` |
| integration | `int` |
| production | `prod` |
| infrastructure | `infra` |

Ветка привязана к итерации из tasklist: `<scope>/<type>-<NNN>-<slug>`, где NNN — номер итерации в скоупе. Пример: `prod/feat-001-auth`, `be/fix-002-sse-reconnect`.

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
ag/feat-001-skills-system ──→ develop ──→ main
be/fix-002-sse-reconnect  ──→ develop ──→ main
```

Рабочая ветка → PR в develop → code review → merge. Релиз: develop → PR в main.

Merged ветки удаляются (GitHub auto-delete после merge PR). Локальные tracking-ветки — периодическая очистка.

## Структура проекта

uv workspace, monorepo.

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

### Конфигурация через env-файлы

Код (Settings) читает только `os.environ` + дефолты — не знает про файлы. Env-файлы загружаются в окружение внешним инструментом (Makefile / docker-compose).

| Файл | Содержимое | Кто читает |
|------|-----------|------------|
| `.env` (gitignored) | Базовая конфигурация: infra (POSTGRES_*) + app (DATABASE_URL, LLM_*) | docker-compose, Makefile (как база) |
| `.env.local` (gitignored) | Только переопределения для local dev (обычно DATABASE_URL с localhost) | Makefile (поверх .env) |
| `.env.example` | Шаблон `.env` | Коммитится в репо |
| `.env.local.example` | Шаблон `.env.local` | Коммитится в репо |

Переключение между режимами — другая команда, не редактирование файла.

## Makefile

Dev-команды: docker-up (full stack), docker-up-db (only PostgreSQL), docker-up-redis (only Redis), docker-down, docker-build, docker-logs, lint, format, type-check, check, lint-fe, format-fe, test, dev, dev-fe.

Backend-команды (dev, migrate, test) используют `LOAD_ENV` — загрузку `.env` (база) затем `.env.local` (overrides) в shell env. Docker-команды — без `LOAD_ENV` (docker-compose читает `.env` самостоятельно).

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

## Documentation Formatting

В Markdown-документах:
- **Диаграммы** — Mermaid (не ASCII-art)
- **Таблицы** — Markdown tables

ASCII-art допустим в интерактивном диалоге (чат), где Mermaid не рендерится. При фиксации результатов из чата в документы — конвертировать ASCII-диаграммы в Mermaid.

### Mermaid Styling

Диаграммы должны быть читаемы на тёмной теме IDE:
- **Не использовать `fill:`** на нодах — светлые фоны нечитаемы на тёмной теме, тёмные — на светлой
- Для семантического разделения — **`stroke:` цвета** + разные формы нод (`[]`, `()`, `{}`, `([])`)
- Подписи и легенды — комментариями или отдельными нодами без стилей

## Prompt Naming

Системные промпты в Langfuse именуются по формату `{name}--{label}`:

```
system--development
system--production
summarization--development
summarization--production
```

Двойной дефис (`--`) разделяет имя промпта и label окружения. Обеспечивает полную изоляцию dev/prod: каждое окружение имеет собственную историю версий. Подробнее — [prompt-management.md](prompt-management.md).

## Logging Conventions

### Семантика уровней

- **DEBUG** — детали для расследования (в production выключены по умолчанию): тела запросов/ответов, промежуточное состояние графа, содержимое конфигов.
- **INFO** — значимые бизнес/операционные события: старт/остановка приложения, агент вызван/завершил, LLM call (факт + длительность), чат создан.
- **WARNING** — система справилась, но что-то было не так: fallback сработал, retry, деградация.
- **ERROR** — операция провалилась, пользователь пострадал: необработанное исключение, сервис недоступен.

### Стиль

- structlog keyword-args: `logger.info("event", key=value)`, не printf-style
- Event name — lowercase, краткое описание действия: `"agent invoked"`, `"llm call"`, `"chat created"`
- `exc_info=True` при логировании исключений (structlog передаёт в stdlib)

### Антипаттерны

- INFO на входе/выходе каждой функции — шум, INFO только для бизнес-событий
- WARNING для ожидаемого поведения ("пользователь не создал проект" — нормальный flow)
- ERROR для клиентских ошибок (невалидный JSON → 422, не error в логах)
