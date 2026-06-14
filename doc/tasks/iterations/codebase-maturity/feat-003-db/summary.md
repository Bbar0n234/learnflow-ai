# feat-003 DB Slice — Post-Implementation Summary

Итерация выполнена полностью, DoD закрыт. DB slice фазы Codebase Maturity: аудит схемы и query-паттернов обеих БД (main app + siem-service) через skill `postgresql`, точечные правки по решениям архитектора, DB-конвенции. Приёмка: findings разобраны с архитектором в диалоге (развилки решены им), тест-кейсы согласованы до правок и прогнаны на живом стенде; код-ревью — за архитектором при merge PR в develop.

## Что сделано

**Целостность и индексы (main app):**
- `refresh_tokens.user_id` — индекс на FK (фильтр `revoke_all_for_user`, проверки каскада при удалении пользователя).
- `refresh_tokens.token_hash` — unique constraint вместо обычного индекса (семантически уникален — SHA-256 токена).
- `mcp_server_disables`: чистка осиротевших строк при удалении проекта (project-scope, thread-scope его тредов, ссылки на его серверы) — FK на полиморфную таблицу невозможен, чистит сервисный слой. `cleanup_disables_for_server` — одним `DELETE` вместо цикла.
- Оппортунистическая чистка протухших refresh-токенов при логине.

**SIEM:**
- Модели переведены на SQLAlchemy 2.0 (`Mapped`/`mapped_column`) — сняты все `# type: ignore[assignment]` по siem-коду; `datetime.now(UTC)` вместо deprecated naive `utcnow()`; `onupdate=func.now()` для `updated_at`.
- Дедупликация алертов — атомарный `INSERT ... ON CONFLICT DO UPDATE` поверх частичного уникального индекса `uq_siem_alerts_open_alert (rule_id, group_key) WHERE status='new'` (NULLS NOT DISTINCT, PG15+). Гонка корреляционного движка при нескольких репликах исключена на уровне БД (раньше — SELECT-then-INSERT + хрупкий `scalar_one_or_none`).
- Жизненный цикл алерта: новый статус `expired` — движок перед оценкой правил авто-закрывает открытые алерты старше `SIEM_ALERT_OPEN_WINDOW_SECONDS` (решение А2: «застоявшееся перевсплывает» свежим алертом, инвариант unique-индекса остаётся честным).
- CHECK constraints на code-bound наборы: `severity`, `status`, `rule_type`.
- Дроп `idx_siem_events_severity` (низкая кардинальность, insert-heavy таблица); `event_type`-индекс оставлен (точный фильтр REST).

**Инфраструктура соединений:**
- `pool_pre_ping=True` на всех трёх движках (main app `infra/db.py`, siem `infra/db.py` уже имел, siem subscriber-движок в `main.py`) — единая линия против выдачи мёртвых соединений после рестарта БД / сетевых блипов.

**Кросс-резрезное:**
- `String(n)` → `Text` во всех таблицах обоих сервисов (лимиты длины — на Pydantic-границе API).
- Naming convention (`pk_/fk_/uq_/ck_/ix_`) в обоих `Base.metadata` + выравнивающие миграции имён существующих constraints (условные renames — bootstrap свежей БД работает).
- `ThreadView.touch()` — явный `UPDATE ... SET updated_at=func.now()` вместо хака «присвоить title самому себе».
- Заголовки `# Manual migration:` добавлены в data-миграции siem 003/004.

## Решения архитектора (развилки итерации)

Разобраны в диалоге, зафиксированы здесь как контекст для будущих итераций:

- **`Text` вместо `String(n)`** — включая существующие колонки (varchar(n) в Postgres не даёт ни места, ни скорости; лимит зашивается в DDL).
- **Дедуп алертов — вариант А2** (авто-закрытие протухших в `expired` + partial unique index + атомарный upsert), не А1 (убрать окно, вечный append). Сохраняет замысел «застоявшееся перевсплывает» и даёт честный lifecycle.
- **CHECK на enum-наборы** — да: `severity`/`status`/`rule_type` зашиты в код (стратегии, lifecycle), расширение набора едет миграцией в одном PR с кодом. Postgres-`ENUM`-тип не вводим (дороже в эволюции).
- **`pool_pre_ping`** — включить везде, единообразно (включая siem, хотя siem частично пересекается с feat-004 — feat-004 подстраивается под этот slice).
- **commit-before-raise** — расширить существующую конвенцию (§ «DB-сессии и commit»), а не плодить новую: эффект, который должен пережить исключение, коммитится до `raise`. Полноценная error-handling философия — feat-007.
- **Hard delete + CASCADE** оставляем; soft delete не вводим и в conventions **не выносим** (явное решение: не фиксировать как конвенцию).
- **`users.name` case-sensitive** — осознанно оставлено.
- **Отложено в backlog § «Оптимизация под будущие нагрузки»**: SQL-агрегаты в стратегиях (сейчас Python поверх выборки окна), uuidv7 вместо uuid4 PK, индексы на `siem_alerts.*_event_id` (обязательны перед retention событий), retention `siem_alerts` (`expired`/`resolved` копятся бессрочно — осознанно, алерты как аудит-след), политика хранения refresh-токенов неактивных пользователей.
- **Squash миграций** — не делаем (условные no-op renames на свежей БД приняты осознанно).
- **Автотесты** — в slice не добавляем (ручной прогон зелёный и задокументирован); системная тестовая рамка — feat-009.

## Отклонения и находки (вне исходного скоупа)

- **Replay-защита refresh-токенов не работала** (security, найдено тест-кейсом A1): `revoke_all_for_user` при детекте replay откатывался вместе с `ReplayDetectedError` (rollback в `get_db_session`) — украденный токен получал 401, но остальные сессии жертвы оставались живыми. Фикс: commit ревокации до `raise`. Перепроверено на живом backend.
- **`script.py.mako` siem-алембика был нерабочим** (`${rev}` вместо `${up_revision}`) — `alembic revision` для siem не запускался никогда, оттого 001/002 и писались руками. Выровнен по backend-шаблону (разблокирует регенерацию миграций в feat-004).
- **Дрейф `siem-service.md`**: таблица корреляции описывала «SQL-механику» (GROUP BY/self-join), которой нет в коде — исправлено на фактическую (Python поверх выборки окна); диаграмма lifecycle утверждала append в `acknowledged`-алерты — код этого никогда не делал.
- **Граница с feat-004**: module-level синглтоны siem (`_engine`/`_async_session_maker`, `get_correlation_engine`), регенерация hand-written DDL 001/002, `SecurityEvent`-дубль, CORS, `MetaEmitter` — намеренно не тронуты, остаются за feat-004. siem-service пересекается в двух slice'ах; по решению архитектора feat-004 подстраивается под этот PR (мержится после).

## Миграции

| БД | Ревизия | Содержимое |
|----|---------|-----------|
| main | `faab892b94fb` | renames constraints под convention (manual, условные) |
| main | `13f18167a945` | varchar→text, индексы refresh_tokens (autogenerate) |
| siem | `0917133ea9b5` | renames + CHECK constraints (manual, условные) |
| siem | `d944c66cc700` | varchar→text, `uq_siem_alerts_open_alert`, дроп severity-индекса (autogenerate) |

Проверено: drift-check пуст для обеих БД; downgrade/upgrade round-trip чистый; bootstrap свежей БД даёт схему, идентичную мигрированной (diff имён constraints/индексов пуст).

## Документация

- `conventions.md` — новый раздел «Схема БД» (Text, timestamptz/aware datetime, naming convention, FK-индексы, CHECK для code-bound enums, индексы по путям доступа, чистка полиморфных ссылок, инварианты в БД); § «DB-сессии и commit» расширен правилом commit-before-raise.
- `siem-service.md` — дедуп через атомарный upsert, lifecycle с `expired`, persistence-таблица.
- `backlog.md` — новая секция «Оптимизация под будущие нагрузки».

## Тестирование

- [test-cases.md](test-cases.md) — 24 кейса (A–G), согласованы до правок.
- [test-report.md](test-report.md) — прогон агентом-тестировщиком на живом стенде (порты 5532/5534/6479): 22 PASS, 2 FAIL (A1 replay, F1 fresh bootstrap); оба фикса перепроверены — итог **24/24 PASS**. `make check` / `make test` зелёные.
