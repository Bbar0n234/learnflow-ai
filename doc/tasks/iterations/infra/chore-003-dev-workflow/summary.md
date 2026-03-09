# chore-003: Makefile + Dev Workflow — Summary

## Что сделано

1. **Makefile** — единая точка входа для dev-команд:
   - `docker-up/down/build` — управление контейнерами
   - `lint`, `format`, `type-check`, `check` — backend quality gates
   - `lint-fe`, `format-fe` — frontend quality gates
   - `test` — запуск pytest
   - `dev`, `dev-fe` — заглушки для Phase D

2. **pytest** — добавлен в dev-зависимости (`pytest>=9.0`), конфигурация в `backend/pyproject.toml` (`[tool.pytest.ini_options]`), создана директория `backend/tests/`.

3. **README** — переписан: Prerequisites, Quick Start, таблица make-команд, два режима окружения.

4. **Документация** — обновлены `conventions.md` (добавлены `lint-fe`, `format-fe`), `tasklist-infra.md` (статус → Done).

## Изменённые файлы

| Файл | Действие |
|------|----------|
| `pyproject.toml` | Edit — добавлен `pytest>=9.0` в dev deps |
| `backend/pyproject.toml` | Edit — добавлена `[tool.pytest.ini_options]` |
| `backend/tests/__init__.py` | Create — пустой файл |
| `Makefile` | Create — 12 таргетов |
| `README.md` | Rewrite — полная инструкция |
| `uv.lock` | Auto-update via `uv sync` |
| `doc/tech/conventions.md` | Edit — lint-fe, format-fe в секцию Makefile |
| `doc/tasks/tasklist-infra.md` | Edit — статус → Done, артефакты |
| `doc/tasks/iterations/infra/chore-003-dev-workflow/summary.md` | Create |

## Известные ограничения

- `make type-check` / `make check` — mypy вернёт ошибку "no .py files" до появления Python-кода в backend/. Решится при старте Phase D.
- `make test` — pytest вернёт exit code 5 (no tests collected). Ожидаемо — тесты появятся позже.

## Phase C — Complete

Итерация chore-003 завершает скоуп Infrastructure Setup. Все три итерации закрыты:
- chore-001: Monorepo + Docker + env ✅
- chore-002: Code quality tooling ✅
- chore-003: Makefile + dev workflow ✅
