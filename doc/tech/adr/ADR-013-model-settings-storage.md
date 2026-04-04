# ADR-013: Per-Scope Settings Storage — typed tables

## Статус

Принято

## Контекст

feat-003 вводит per-scope конфигурацию на трёх уровнях иерархии: user → project → thread. Первый тип settings — model overrides (model_name, extra_body). Каскад наследования: thread → project → user → global default. NULL на любом уровне означает "наследовать от уровня выше".

Иерархия сущностей фиксирована (users → projects → thread_views), расширение новыми уровнями не планируется. Таблицы settings расширяемы — новые scalar preferences (не только model) добавляются как колонки, не как новые таблицы.

Текущая схема БД: таблицы users, projects, thread_views — без settings/preferences полей.

## Рассмотренные варианты

### A: JSONB `settings` на parent tables

Добавить колонку `settings JSONB DEFAULT '{}'` на каждую из трёх существующих таблиц.

- **За:** одна миграция, минимум нового кода, не нужны новые таблицы.
- **Против:** PostgreSQL query planner не ведёт статистику по значениям JSONB-полей; unmarshaling на каждое чтение (hot path — каждое сообщение); settings "размазаны" по бизнес-таблицам, нарушая separation of concerns; schema evolution только через код, не через миграции; нет column-level constraints и type safety.

### B: Одна polymorphic таблица

`entity_settings(scope_type VARCHAR, scope_id UUID)` — одна таблица для всех трёх уровней.

- **За:** один repo, одна модель, одна таблица.
- **Против:** нет FK constraints — при CASCADE DELETE parent-записи остаются orphaned rows; referential integrity обеспечивается только на уровне приложения; polymorphic FK — антипаттерн при фиксированном числе entity types (у нас ровно 3).

### C: Три typed таблицы с FK

`user_settings`, `project_settings`, `thread_settings` — каждая с proper FK на parent-таблицу.

- **За:** FK CASCADE — referential integrity на уровне БД, orphaned rows невозможны; typed колонки с индексами; каждая таблица может эволюционировать независимо; extensible — новые scalar settings добавляются как колонки.
- **Против:** три таблицы вместо одной.

## Решение

Вариант C — три typed таблицы с FK.

## Обоснование

- Число entity types фиксировано (3), не будет расти — polymorphic single table не оправдан.
- Referential integrity на уровне БД — базовое требование. Application-level cleanup ненадёжен и создаёт класс багов, которые FK CASCADE исключает полностью.
- GitLab Cascading Settings Framework использует аналогичный подход — отдельные typed таблицы на каждый уровень иерархии с NULL = "наследовать от родителя".
- Code duplication минимизируется: SQLAlchemy mixin для общих колонок (`model_name`, `extra_body`, `created_at`, `updated_at`) + один generic repository с методами `get_for_user()`, `get_for_project()`, `get_for_thread()`.
- Extensible: таблицы начинаются с model config (model_name, extra_body) и расширяются будущими scalar preferences (тема, язык, другие per-scope настройки) без создания новых таблиц.

## Следствия

- Одна Alembic-миграция создаёт три таблицы.
- Cascade resolve выполняется в application layer (ModelConfigResolver), не в БД — три SELECT по indexed PK, затем merge в коде.
- Паттерн "typed tables per scope" повторяется для 1:N коллекций (MCP servers — см. ADR-016), но каждое решение принимается отдельно, т.к. у коллекций другая кардинальность и lifecycle.
