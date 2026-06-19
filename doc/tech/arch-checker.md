# Arch-checker: реестр инвариантов и детерминированные проверки

Документ отвечает на один вопрос: какие архитектурные нормы проекта проверяются
машинно, каким механизмом, и что остаётся на ревьюера. Это карта, а не точечный
набор хаков — каждая нормативная формулировка из `conventions.md` и Layers-диаграмм
(`backend.md`, `siem-service.md`, `frontend.md`) проходит через решение
«детерминированно проверяемо?» и получает механизм либо пометку `→ LLM-reviewer`.

## Слои защиты

Детерминированные проверки распределены по четырём механизмам; пятый — ревьюер —
ловит то, что требует понимания смысла, а не структуры.

| Механизм | Где живёт | Что проверяет |
|----------|-----------|---------------|
| **ruff** | `ruff.toml` | Стиль, мёртвый код, top-level импорты (`PLC0415`), вызовы в дефолтах (`B008`) |
| **import-linter** | `pyproject.toml [tool.importlinter]` | Слоевые зависимости backend/siem, изоляция `packages/`, транспорт в домене |
| **AST-ассерты** | `tools/arch-checker/arch_checker/` | Порядок middleware, зеркала `problem.py`, module-level синглтоны |
| **eslint-plugin-boundaries** | `frontend/eslint.config.mjs` | FSD-границы фронтенда: направление импортов, публичные API слайсов |
| **LLM-reviewer** | ревью итерации | Семантические инварианты, не выразимые структурно |

Все четыре машинных механизма входят в gate: `make check` (ruff + mypy +
import-linter + AST-ассерты), `make check-fe` (tsc + eslint-boundaries + prettier),
а также pre-commit (`import-linter`, `arch-checker-ast`) и CI (через `make check` /
`make check-fe`).

## Запуск

```sh
make check        # backend gate целиком (включая arch-check)
make check-fe     # frontend gate целиком (включая boundaries)
make arch-check   # только import-linter + AST-ассерты

# по отдельности:
PYTHONPATH=backend:services/siem-service uv run lint-imports
uv run python -m arch_checker
```

import-linter требует `PYTHONPATH=backend:services/siem-service`: Grimp находит
пакеты через module finder, а `app` и `siem_service` не устанавливаются как
дистрибутивы (у `backend` нет build-backend, siem собирается, но в граф его
исходники подаются тем же путём). `siem_contracts` ставится editable из workspace.

## Реестр инвариантов

Покрытие на текущем коде: «✅ покрыто» — проверка реализована и в gate; «кандидат» —
детерминируемо, но механизм пока не подключён (нарушений в коде нет, поэтому проверка
не блокирует — её можно добавить без разгребания долга); «→ LLM-reviewer» — структурно
не выразимо. Колонка «нарушения» — состояние на момент написания.

### Слоевые зависимости и границы

| Инвариант | Директории | Механизм | Покрыто | Нарушения |
|-----------|-----------|----------|---------|-----------|
| `api > services > repositories > models`, без импортов вверх | `backend/app/{api,services,repositories,models}` | import-linter (layers) | ✅ | нет (кроме allow-listed `services/mcp_server → api/schemas`) |
| `api/routes ↛ repositories`, `api/routes ↛ agent` (только через service) | `backend/app/api/routes` | import-linter (forbidden, `allow_indirect_imports`) | ✅ | 3 роута в allowlist (R1, см. ниже) |
| `models ↛ infra` | `backend/app/models` | import-linter (forbidden) | ✅ | нет |
| Транспорт не течёт в домен (`fastapi`/`HTTPException` в service/repo/agent/model) | `backend/app/{services,repositories,agent,models}` | import-linter (forbidden external) | ✅ | нет |
| siem: `api > services\|pipeline\|correlation > domain`, `infra/domain` не вверх | `services/siem-service/siem_service/*` | import-linter (forbidden ×3) | ✅ | нет |
| siem: транспорт не течёт в домен | `siem_service/{services,repositories,pipeline,correlation,domain}` | import-linter (forbidden external) | ✅ | нет |
| `packages/siem-contracts ↛ app.* / siem_service.*` (leaf-библиотека) | `packages/siem-contracts` | import-linter (forbidden) | ✅ | нет |
| FSD: импорт строго вниз `app→pages→features→shared`, `stores` cross-cutting | `frontend/src/*` | eslint-boundaries (`dependencies`) | ✅ | нет |
| FSD: нет cross-slice внутри слоя (`pages↛pages`, `features↛features`) | `frontend/src/{pages,features}` | eslint-boundaries (same-slice internal, cross-slice disallow) | ✅ | нет |
| FSD: `pages`/`features` импортируются только через `index.ts` (`shared` — нет) | `frontend/src/{pages,features}` | eslint-boundaries (`internalPath`) | ✅ | нет |

### Качество кода и стиль

| Инвариант | Директории | Механизм | Покрыто | Нарушения |
|-----------|-----------|----------|---------|-----------|
| Импорты на верхнем уровне (`# lazy:`/`# circular:` — исключения) | весь Python | ruff `PLC0415` | ✅ (в ruff) | нет |
| Нет вызовов в дефолтах параметров (Annotated-стиль) | весь Python | ruff `B008` | ✅ (в ruff) | нет |
| Нет module-level синглтонов (`_x: T\|None=None` + `global _x`) | `backend/app`, `siem_service` | AST (`module_singletons`) | ✅ | нет |
| `logging.getLogger` для логов приложения запрещён (только structlog) | весь Python | grep — но даёт ложное срабатывание на подавлении сторонних логгеров (`logging.getLogger("opentelemetry.context").setLevel(...)` в `infra/langfuse.py`) | → LLM-reviewer | 1 благонадёжный match |
| Нет `console.*` на фронте (только `@/shared/lib/logger`) | `frontend/src` | eslint `no-console` | кандидат | нет |

### Схема БД (модели)

| Инвариант | Директории | Механизм | Покрыто | Нарушения |
|-----------|-----------|----------|---------|-----------|
| Строки — `Text`, не `String(n)`/`VARCHAR(n)` | `backend/app/models`, `siem_service/domain` | AST/grep на `String(`/`VARCHAR` в `mapped_column` | кандидат | нет |
| `datetime.now(UTC)`, не `datetime.utcnow()` (naive, deprecated) | весь Python | ruff `DTZ` (flake8-datetimez) — не включён | кандидат | нет |
| Declarative `Mapped[...]`-стиль, не `Column()` | модели | AST/grep на `Column(` | кандидат | нет |
| `DateTime(timezone=True)`; FK с `index=True`; `server_default=func.now()`; CHECK для enum-строк | модели | частично AST, частично смысловое | → LLM-reviewer | — |

### Обработка ошибок

| Инвариант | Директории | Механизм | Покрыто | Нарушения |
|-----------|-----------|----------|---------|-----------|
| Доменные исключения, не транспорт (`raise HTTPException` в домене — антипаттерн) | service/repo/agent | import-linter (forbidden `fastapi`) — см. выше | ✅ | нет |
| Generic-`Exception` middleware зарегистрирован раньше `CORSMiddleware` (внутри CORS) | оба `main.py::create_app` | AST (`middleware_order`) | ✅ | нет |
| Нет `add_exception_handler(Exception, ...)` (он бы прошёл вне CORS) | оба `main.py` | AST (`middleware_order`) | ✅ | нет |
| `problem.py` backend ≡ siem: handler'ы структурно совпадают | `*/api/problem.py` | AST (`problem_mirrors`, нормализация docstring/импорта) | ✅ | нет |
| `AppError`/`NotFoundError`/`ConflictError` совпадают (siem — легитимное подмножество) | оба `exceptions.py` | AST (`problem_mirrors`, сравнение базовой тройки) | ✅ | нет |
| `except Exception` только на барьере; нет глушащих `except: pass` | весь Python | смысловое (контекст «есть ли решение») | → LLM-reviewer | — |
| Восстановление fail-fast/graceful/fail-safe; наблюдаемость деградаций | runtime | смысловое | → LLM-reviewer | — |

### Прочее (вне детерминированного слоя)

`Protocol` vs `ABC`; ось состояния (серверное в Query, клиентское в Zustand);
фабрика query keys; граница shadcn в `shared/ui`; выбор формы типа
(`Enum`/`BaseModel`/`dataclass`); секреты fail-fast в `Settings`/compose;
env-vs-константа; коммит до `raise`/`return` в DB-сессиях; ручные миграции с
заголовком `# Manual migration:` — все требуют понимания намерения, а не структуры,
и остаются на `→ LLM-reviewer`. Часть (нейминг snake_case, security-event
`event_type` из `Literal`-vocabulary) частично ловится ruff `N`-правилами и mypy на
call-site соответственно.

## Известные исключения (allowlist)

**Слой-нарушение по дизайну.** `services/mcp_server.py → api/schemas/mcp_servers.py` —
сервис импортирует свою request-схему против направления слоёв, без цикла
(`backend.md § Правила вызовов`). Закодировано как единственный разрешённый импорт
в `ignore_imports` контракта backend-layers.

**R1 — реальные нарушения API→Repository.** Три роута инстанцируют репозитории прямо
в хендлерах. Все три нетривиальны для механического переноса в сервисный слой,
поэтому занесены в `ignore_imports` контракта api-isolation и вынесены в backlog
(карточки — в отчёте итерации):

- `api/routes/settings.py → repositories/settings.py` — `SettingsService` не
  существует; `ModelConfigResolver.resolve(repo, …)` принимает репозиторий
  параметром. Перенос требует проектирования сервиса, не механической замены.
- `api/routes/mcp_servers.py → repositories/mcp_server.py` — `McpServerService`
  покрывает только write-flow (guard+persist/update); 18 read/list/toggle/delete
  хендлеров ходят в репозиторий напрямую. Перенос — добавление методов в сервис,
  то есть рефакторинг.
- `api/routes/feedback.py → repositories/trace_store.py` — `FeedbackService` не
  существует; в роуте инлайн-логика Langfuse + Redis-`TraceStore` + проверка
  владения. Перенос — выделение сервиса.

Удаление любой строки из этих allowlist'ов возвращает нарушение в gate — то есть
долг зафиксирован, а новые нарушения того же класса ловятся сразу.

## Структура `tools/arch-checker`

- `arch_checker/middleware_order.py` — проверка (a): порядок middleware + запрет
  `add_exception_handler(Exception)`.
- `arch_checker/problem_mirrors.py` — проверка (b): зеркальность `problem.py` и
  базовых исключений.
- `arch_checker/module_singletons.py` — проверка (c): узкий чек module-level
  синглтонов.
- `arch_checker/__main__.py` — прогон всех проверок, exit ≠ 0 при нарушении.
- `arch_checker/_common.py` — поиск корня репо, парсинг, нормализация AST.
