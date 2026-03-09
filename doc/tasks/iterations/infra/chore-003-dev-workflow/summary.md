# Summary: chore-003 — Makefile + Dev Workflow

## Результат

Единая точка входа для dev-команд через Makefile (12 таргетов). Инфраструктура для тестов подготовлена (pytest + директория). README переписан с полной инструкцией запуска.

Phase C (Infrastructure Setup) полностью завершена — все три итерации закрыты.

## Отклонения от плана

Нет. Реализация полностью соответствует плану.

**Ожидаемые ограничения (не отклонения):**
- `make type-check` / `make check` — mypy вернёт ошибку "no .py files" до появления Python-кода в backend/. Задокументировано в плане, решится при старте Phase D.
- `make test` — pytest вернёт exit code 5 (no tests collected). Ожидаемо — тесты появятся позже.

## Решения, принятые при реализации

Все решения были приняты на этапе планирования, дополнительных решений при реализации не потребовалось.

## Артефакты

| Файл | Действие |
|------|----------|
| `Makefile` | Created — 12 таргетов (docker, lint, format, check, test, dev) |
| `backend/tests/__init__.py` | Created — пустой файл |
| `README.md` | Rewritten — Prerequisites, Quick Start, Make Commands, Environment Modes |
| `pyproject.toml` | Edited — добавлен `pytest>=9.0` в dev deps |
| `backend/pyproject.toml` | Edited — добавлена `[tool.pytest.ini_options]` |
| `uv.lock` | Updated by `uv sync` |
| `doc/tech/conventions.md` | Edited — добавлены `lint-fe`, `format-fe` в секцию Makefile |
| `doc/tasks/tasklist-infra.md` | Edited — статус → Done, артефакты заполнены |

## Верификация

| Проверка | Результат |
|----------|-----------|
| `make check` (lint + format-check + type-check) | Passed — ruff check, ruff format --check, mypy — все ок |
| `make lint` | Passed |
| `make test` | Passed — pytest запускается, 0 тестов, exit 5 (ожидаемо) |
| `make -n` (все таргеты) | Passed — все 12 таргетов существуют |
| README содержит инструкцию запуска | Passed |
