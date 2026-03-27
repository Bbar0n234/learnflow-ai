# Post-Implementation Summary: feat-001 Logging

## Результат

Реализовано управляемое логирование на backend и frontend. Все критерии приёмки из tasklist выполнены. `make check` + `make lint-fe` проходят.

## Отклонения от плана

### 1. Makefile: `make format` расширен

**Что:** `make format` теперь запускает `ruff check --fix` перед `ruff format`.

**Почему:** при реализации обнаружилось, что `ruff format` не исправляет isort (правило `I001`). Типовой сценарий (добавить import → `make format` → `make check`) не работал — требовался ручной `ruff check --fix`. Решение согласовано с архитектором.

### 2. `status` в "agent completed" log event

**Что:** добавлено поле `status="error"|"ok"` в лог-запись `"agent completed"` (runner.py).

**Почему:** по ревью архитектора — event логируется в `finally` блоке и при ошибке, и при успехе. Поле `status` делает запись самодостаточной для фильтрации/алертинга.

**Не было в плане:** план описывал `logger.info("agent completed", thread_id=..., duration_ms=...)` без `status`.

### 3. CLAUDE.md: сокращён logging section

**Что:** вместо полного дублирования уровней и антипаттернов — краткие do/don't правила + ссылка на conventions.md.

**Почему:** при ревью документации выявлено нарушение Single Source of Truth (AIDD) — одна и та же информация в CLAUDE.md и conventions.md. Решение: CLAUDE.md = оперативные правила для агента, conventions.md = source of truth для деталей.

### 4. backend.md: убран код-пример

**Что:** секция "Использование" в backend.md заменена ссылкой на conventions.md вместо дублирования кода-примера.

**Почему:** тот же принцип Single Source of Truth.

## Нюансы реализации

- **`usage_metadata`** в graph.py: `response.usage_metadata` может быть `None` или `UsageMetadata` (TypedDict). Использован тернарный `usage.get(...) if usage else None` для защиты.
- **`bound_model.model_name`**: атрибут может не существовать в некоторых реализациях `BaseChatModel`. Защита через `getattr(bound_model, "model_name", "unknown")`.
- **`ThreadView.thread_id`** vs `ThreadView.id`: при добавлении `logger.info("chat created", thread_id=...)` первоначально использовался `.id` (не существует). Исправлено на `.thread_id` при mypy-проверке.
