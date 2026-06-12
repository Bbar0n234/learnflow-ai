# feat-003-db: тест-кейсы

Ручные/скриптовые тест-кейсы на правки DB slice'а. Прогоняются на живом стенде worktree
(порты: main PG **5532**, siem PG **5534**, Redis **6479** — альтернативные, чтобы не
конфликтовать с параллельными агентами). Прогон — после реализации, агентом-тестировщиком;
результаты фиксируются в `test-report.md` рядом с этим файлом.

Покрытие: каждый кейс привязан к согласованной правке. Контракты API не менялись —
кейсы с пометкой *(регресс)* проверяют, что поведение не сломалось.

## Стенд

- `docker compose up -d db siem-db redis` (env уже настроен на альтернативные порты).
- Миграции: `make migrate` + `make migrate-siem`.
- siem-service: `uv run uvicorn siem_service.main:app --port 8001` из `services/siem-service`.
- backend: `make dev` (для REST-кейсов auth/projects). LLM-ключей на стенде нет — кейсы,
  требующие реального вызова модели, заменены скриптовыми проверками на уровне репозиториев.
- Прямой SQL: `psql -h localhost -p 5532 -U learnflow learnflow` / `-p 5534 -U siem siem`.

## A. Auth / refresh_tokens

| ID | Кейс | Ожидание |
|----|------|----------|
| A1 | *(регресс)* register → login → refresh → повторный refresh старым токеном | Первый refresh — 200, новая пара токенов; повторный — ошибка replay, все токены пользователя отозваны |
| A2 | Уникальность `token_hash`: прямой `INSERT` дубля существующего hash | `IntegrityError` / unique violation от БД |
| A3 | Оппортунистическая чистка: вставить пользователю токен с `expires_at` в прошлом + один валидный, выполнить login | Протухшая строка удалена, валидная и свежесозданная остались |
| A4 | Индекс на FK: `\d refresh_tokens` | Присутствует индекс по `user_id`; индекс по `token_hash` — unique |

## B. Удаление проекта / mcp_server_disables

| ID | Кейс | Ожидание |
|----|------|----------|
| B1 | Создать проект → тред → user-server + project-server → выставить disable user-server'а на project-scope и thread-scope → удалить проект | В `mcp_server_disables` нет строк со `scope_id` проекта и его тредов; user-server жив; project-server удалён каскадом |
| B2 | *(регресс)* Удалить user-server, у которого есть disables | Его disables удалены |
| B3 | *(регресс)* Toggle disable/enable сервера на project/thread scope через API | Список серверов отражает `disabled` корректно |

## C. ThreadView.touch

| ID | Кейс | Ожидание |
|----|------|----------|
| C1 | Скрипт: создать ThreadView, запомнить `updated_at`, вызвать `touch()` | `updated_at` увеличился, `title` и прочие поля не изменились |

## D. Типы и naming convention (обе БД)

| ID | Кейс | Ожидание |
|----|------|----------|
| D1 | `information_schema.columns`: колонки типа `character varying` в таблицах приложения | Ни одной — все стали `text` |
| D2 | `pg_constraint` / `pg_indexes`: имена constraints наших таблиц | Соответствуют convention: `pk_*`, `fk_*`, `uq_*`, `ck_*`, `ix_*` |
| D3 | **Drift-проверка**: `alembic revision --autogenerate` поверх head (обе БД) | Пустые `upgrade()`/`downgrade()` — модели и схема консистентны (файл удалить после проверки) |

## E. SIEM pipeline

| ID | Кейс | Ожидание |
|----|------|----------|
| E1 | *(регресс)* XADD события в стрим → подождать; повторный XADD с тем же `event_id` | Событие в `siem_events` ровно один раз (идемпотентность ON CONFLICT) |
| E2 | *(регресс)* `GET /events` с фильтрами: точный `event_type`, `severity`, `from`/`to`, `limit`/`offset` | Корректные выборки и `total` |
| E3 | Threshold-правило: N событий с одним `ip` за окно | Алерт создан: `status=new`, `group_key=ip`, `matched_events_count≥1` |
| E4 | Дедуп (атомарный upsert): продолжать слать события той же группы | `matched_events_count` растёт, второй строки алерта нет |
| E5 | Уникальный индекс открытого алерта: прямой `INSERT` второго `new`-алерта с тем же `(rule_id, group_key)`; затем то же с `group_key = NULL` дважды | Оба раза unique violation (включая NULL — `NULLS NOT DISTINCT`) |
| E6 | Авто-закрытие (А2): `SIEM_ALERT_OPEN_WINDOW_SECONDS=30`, создать алерт, подождать > окна + тик движка | Алерт переведён в `expired`; новое срабатывание создаёт свежий `new`-алерт с тем же ключом |
| E7 | *(регресс)* `PATCH /alerts/{id}`: `acknowledged`, затем `resolved`; затем недопустимый статус | 200/200 с проставленными `*_at`/`*_by`; недопустимый — 400 |
| E8 | CHECK constraints: прямой `INSERT` события с `severity='bogus'`; правила с `rule_type='bogus'`; алерта со `status='bogus'` | Все три — check violation |
| E9 | Индексы `siem_events`: `\di` | `idx_siem_events_severity` отсутствует; event_type/ingested_at/event_timestamp/GIN — на месте |
| E10 | *(регресс)* Rules CRUD через REST (create/update/delete) | Работает как раньше; `updated_at` обновляется автоматически |

## F. Миграции

| ID | Кейс | Ожидание |
|----|------|----------|
| F1 | Свежая БД (drop volume) → `upgrade head` (обе БД) | Проходит без ошибок |
| F2 | `downgrade` на все новые ревизии итерации → `upgrade head` (обе БД) | Откат и повторный накат чистые; D3 после повторного наката снова пустой |

## G. Статика

| ID | Кейс | Ожидание |
|----|------|----------|
| G1 | `make check` | ruff + mypy зелёные (в т.ч. ни одного `# type: ignore[assignment]` в siem-репозиториях) |
| G2 | `make test` | Зелёный |
