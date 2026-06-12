# feat-003-db: итоги

DB slice фазы Codebase Maturity: аудит схемы и query-паттернов обеих БД (main app + siem-service) через skill `postgresql`, согласованные с архитектором правки, DB-конвенции.

## Что сделано

**Целостность и индексы (main app):**
- `refresh_tokens.user_id` — индекс на FK (фильтр `revoke_all_for_user`, проверки каскада).
- `refresh_tokens.token_hash` — unique constraint вместо обычного индекса.
- `mcp_server_disables`: чистка осиротевших строк при удалении проекта (project-scope, thread-scope его тредов, ссылки на его серверы) — FK на полиморфную таблицу невозможен, чистит сервисный слой. `cleanup_disables_for_server` — одним `DELETE` вместо цикла.
- Оппортунистическая чистка протухших refresh-токенов при логине.

**SIEM:**
- Модели переведены на SQLAlchemy 2.0 (`Mapped`/`mapped_column`) — сняты все `# type: ignore[assignment]` по siem-коду; `datetime.now(UTC)` вместо deprecated naive `utcnow()`; `onupdate=func.now()` для `updated_at`.
- Дедупликация алертов — атомарный `INSERT ... ON CONFLICT DO UPDATE` поверх частичного уникального индекса `uq_siem_alerts_open_alert (rule_id, group_key) WHERE status='new'` (NULLS NOT DISTINCT, PG15+). Гонка реплик корреляционного движка исключена на уровне БД.
- Жизненный цикл алерта: новый статус `expired` — движок перед оценкой правил авто-закрывает открытые алерты старше `SIEM_ALERT_OPEN_WINDOW_SECONDS` (решение А2: «застоявшееся перевсплывает» свежим алертом).
- CHECK constraints на code-bound наборы: `severity`, `status`, `rule_type`.
- Дроп `idx_siem_events_severity` (низкая кардинальность, insert-heavy таблица); `event_type`-индекс оставлен (точный фильтр REST).

**Кросс-резрезное:**
- `String(n)` → `Text` во всех таблицах обоих сервисов (лимиты длины — на Pydantic-границе).
- Naming convention (`pk_/fk_/uq_/ck_/ix_`) в обоих `Base.metadata` + выравнивающие миграции имён существующих constraints (условные renames — bootstrap свежей БД работает).
- `ThreadView.touch()` — явный `UPDATE ... SET updated_at=func.now()` вместо хака «присвоить title самому себе».
- Заголовки `# Manual migration:` добавлены в data-миграции siem 003/004.

**Найденные и закрытые по ходу баги (вне исходного скоупа):**
- **Replay-защита refresh-токенов не работала**: `revoke_all_for_user` откатывался вместе с `ReplayDetectedError` (rollback в `get_db_session`). Фикс: commit ревокации до raise. Найдено прогоном тест-кейса A1.
- Шаблон `services/siem-service/alembic/script.py.mako` был нерабочим (`${rev}` вместо `${up_revision}`) — `alembic revision` для siem никогда не работал; выровнен по backend-шаблону.
- Дрейф `doc/tech/siem-service.md`: таблица корреляции описывала «SQL-механику» (GROUP BY/self-join), которой нет в коде — исправлено на фактическую (Python поверх выборки окна); диаграмма lifecycle утверждала append в `acknowledged`-алерты — код этого никогда не делал.

## Миграции

| БД | Ревизия | Содержимое |
|----|---------|-----------|
| main | `faab892b94fb` | renames constraints под convention (manual, условные) |
| main | `13f18167a945` | varchar→text, индексы refresh_tokens (autogenerate) |
| siem | `0917133ea9b5` | renames + CHECK constraints (manual, условные) |
| siem | `d944c66cc700` | varchar→text, `uq_siem_alerts_open_alert`, дроп severity-индекса (autogenerate) |

Проверено: drift-check пуст для обеих БД; downgrade/upgrade round-trip чистый; bootstrap свежей БД даёт схему, идентичную мигрированной (diff имён пуст).

## Документация

- `conventions.md` — новый раздел «Схема БД» (Text, timestamptz/aware datetime, naming convention, FK-индексы, CHECK для code-bound enums, индексы по путям доступа, чистка полиморфных ссылок, инварианты в БД).
- `siem-service.md` — дедуп, lifecycle с `expired`, persistence-таблица.
- `backlog.md` — новая секция «Оптимизация под будущие нагрузки»: SQL-агрегаты в стратегиях, uuidv7, индексы на `siem_alerts.*_event_id` перед retention, политика хранения refresh-токенов неактивных пользователей.

## Тестирование

- [test-cases.md](test-cases.md) — 24 кейса (A–G), согласованы до правок.
- [test-report.md](test-report.md) — прогон агентом-тестировщиком на живом стенде (порты 5532/5534/6479): 22 PASS, 2 FAIL (A1, F1); оба фикса перепроверены — итог 24/24 PASS.

## Решения архитектора (для conventions-истории)

- `Text` вместо `String(n)` — включая существующие колонки.
- Дедуп алертов: вариант А2 (авто-закрытие + unique index), не А1 (вечный append).
- CHECK на enum-наборы — да, т.к. наборы зашиты в код и расширяются вместе с ним.
- `users.name` case-sensitive — осознанно оставлено.
- uuid4 PK, SQL-агрегаты — осознанно отложены (backlog «Оптимизация под будущие нагрузки»).
- Soft delete не вводится и в conventions не выносится (явное решение архитектора: остаёмся на существующем паттерне, конвенцию не фиксируем).
