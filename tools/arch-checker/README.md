# arch-checker

Детерминированный слой архитектурных проверок LearnFlow AI (feat-008). Ловит
инварианты, которые не выражаются ruff'ом: слоевые зависимости, framework-ordering
обработки ошибок, зеркальность `problem.py`, module-level синглтоны.

Полный реестр инвариантов и распределение по механизмам — `doc/tech/arch-checker.md`.

## Что входит

| Механизм | Что проверяет | Где конфиг |
|----------|---------------|------------|
| **import-linter** | Слоевые зависимости backend/siem, изоляция `packages/` | `pyproject.toml [tool.importlinter]` (корень репо) |
| **AST-ассерты** (`arch_checker`) | (a) порядок middleware, (b) зеркала `problem.py`/`AppError`, (c) module-level синглтоны | этот пакет |

## Запуск

Обе проверки входят в `make check`:

```sh
# import-linter (PYTHONPATH нужен Grimp'у — backend/siem не установлены как пакеты)
PYTHONPATH=backend:services/siem-service uv run lint-imports

# AST-ассерты
uv run python -m arch_checker
```

Exit-код ≠ 0 при любом нарушении; AST-ассерты печатают список нарушений в stderr.

## Структура

- `arch_checker/middleware_order.py` — generic-`Exception` middleware зарегистрирован
  раньше `CORSMiddleware`; нет `add_exception_handler(Exception, ...)`.
- `arch_checker/problem_mirrors.py` — handler'ы двух `problem.py` и базовые
  `AppError`/`NotFoundError`/`ConflictError` структурно совпадают (docstring'и
  и источник импорта нормализуются).
- `arch_checker/module_singletons.py` — узкий чек на `_x = None` + `global _x`.
