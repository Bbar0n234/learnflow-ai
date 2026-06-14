# feat-003-db: отчёт о тестировании

Прогон на живом стенде worktree (main PG :5532, siem PG :5534, Redis :6479; alembic head на обеих БД).
Дата прогона: 2026-06-12. Сервисы поднимались на альтернативных портах (backend :8100, siem-service :8101
c `SIEM_ALERT_OPEN_WINDOW_SECONDS=30`, `SIEM_POLL_INTERVAL_SECONDS=5`, `SIEM_JWT_SECRET=$JWT_SECRET`), потому что
8000/8001 были заняты процессами параллельного worktree.

Отступления от плана стенда (зафиксированы как допустимая замена):

- **B1/B2**: строки `user_mcp_servers` / `project_mcp_servers` созданы прямым SQL INSERT — REST-создание MCP-сервера
  (`guard_and_persist`) требует живой MCP-endpoint и LLM-guard, которых на стенде нет. Toggle/delete/list — через REST.
- **C1**: скриптом через `ThreadViewRepository` (LLM-потока на стенде нет) — как и предусмотрено тест-кейсами.
- **E7/E10**: admin-JWT для SIEM API сминчен вручную (HS256, `is_admin: true`) под секрет, переданный сервису.

## Результаты

| ID | Статус | Детали / вывод |
|----|--------|----------------|
| A1 | **FAIL** (частично) | register → login → refresh: 200, новая пара токенов; повторный refresh старым токеном: 401 `Token reuse detected, all sessions revoked`. **Но токены пользователя фактически НЕ отозваны**: после replay в БД 2 активных токена (`revoked_at IS NULL`), и refresh новейшим токеном вернул 200. Причина: `AuthService.refresh` вызывает `revoke_all_for_user` и бросает `ReplayDetectedError`; route превращает её в `HTTPException` → `get_db_session` (`backend/app/api/deps.py:40-49`) ловит исключение и делает `rollback()`, откатывая revoke-all. Ревокация теряется вместе с транзакцией. |
| A2 | PASS | Прямой INSERT дубля hash → `ERROR: duplicate key value violates unique constraint "uq_refresh_tokens_token_hash"`. |
| A3 | PASS | Вставлены протухший (`expires_at` − 1 day) и валидный токены; после login протухшая строка удалена, валидная (`tc_hash_valid_a3`) и свежесозданная остались. |
| A4 | PASS | `\d refresh_tokens`: `ix_refresh_tokens_user_id` btree(user_id); `uq_refresh_tokens_token_hash` UNIQUE. |
| B1 | PASS | Проект + тред + user-server + project-server; disables user-server'а на project- и thread-scope; после DELETE проекта (204): `mcp_server_disables` пуста (0 строк), user-server жив, project-server удалён каскадом, треды удалены. |
| B2 | PASS | DELETE user-server с активным disable (204) → его строки в `mcp_server_disables` удалены. |
| B3 | PASS | Toggle disable → `is_disabled: true` в списке inherited (project и thread scope); toggle enable → строка удалена из БД, `is_disabled: false`; повторный disable снова отражается. |
| C1 | PASS | Скрипт через `ThreadViewRepository`: после `touch()` `updated_at` увеличился (19:04:11.51 → 19:04:12.73), `title`, `created_at`, `security_blocked` не изменились. |
| D1 | PASS | Обе БД: единственная колонка `character varying` — `alembic_version.version_num` (служебная таблица Alembic, не приложения). Все колонки приложения — `text`. |
| D2 | PASS | Обе БД: все constraints/индексы таблиц приложения соответствуют convention (`pk_*`, `fk_*`, `uq_*`, `ck_*`, `ix_*`). Вне convention в main DB — только таблицы LangGraph (`checkpoints*`, `store*`), создаваемые библиотекой `langgraph-checkpoint-postgres` при старте backend, — third-party DDL, вне scope. |
| D3 | PASS | `alembic revision --autogenerate` поверх head на обеих БД → пустые `upgrade()`/`downgrade()` (`pass`). Drift-файлы удалены. |
| E1 | PASS | XADD в `security.events` (поля `event_id` + `data` JSON) → 1 строка в `siem_events`; повторный XADD с тем же `event_id` → по-прежнему 1 строка (ON CONFLICT идемпотентность). |
| E2 | PASS | 4 посеянных события: точный `event_type` → total 3; `severity=critical` + `from`/`to` → total 1 (нужный тип); узкое окно `from`/`to` → total 2; `limit=2/offset=0` → 2 items, `offset=2` → 1 item, `total=3` стабилен. Фильтр времени — по `event_timestamp`. |
| E3 | PASS | tc_rule_e3 (threshold: pattern `rate_limit.refresh.exceeded`, threshold 3, window 120s, group_key `ip`); 3 события с ip 203.0.113.77 → алерт `status=new`, `group_key=203.0.113.77`, `matched_events_count=2` (≥1). |
| E4 | PASS | Ещё 2 события той же группы → тот же алерт, `matched_events_count` 2→5, `latest_event_id` обновился, вторая строка не появилась (1 строка на группу). |
| E5 | PASS | INSERT второго `new`-алерта с тем же `(rule_id, group_key)` → `duplicate key ... "uq_siem_alerts_open_alert"`; пара INSERT'ов с `group_key=NULL`: первый прошёл, второй → та же unique violation (`(rule_id, group_key)=(5, null)`) — `NULLS NOT DISTINCT` работает. |
| E6 | PASS | C окном 30s: алерт id=1 (created 19:07:11) переведён движком в `expired`; продолжающиеся срабатывания создали свежий `new`-алерт id=7 с тем же `(rule_id, group_key)` (created 19:07:41). |
| E7 | PASS | PATCH `acknowledged` → 200, `acknowledged_at`/`acknowledged_by=tc_admin` проставлены; PATCH `resolved` → 200, `resolved_at`/`resolved_by` проставлены; PATCH `bogus` → 400. |
| E8 | PASS | Все три прямых INSERT отклонены: `ck_siem_events_severity`, `ck_correlation_rules_rule_type`, `ck_siem_alerts_status`. |
| E9 | PASS | Индексы `siem_events`: `ix_siem_events_event_type`, `ix_siem_events_event_timestamp`, `ix_siem_events_ingested_at`, `ix_siem_events_identifiers_gin`, `pk_*`, `uq_*_event_id`. Индекса по severity (`idx_siem_events_severity`) нет. |
| E10 | PASS | POST /rules → 201; PATCH → 200, `updated_at` обновился автоматически (19:08:44.95 → 19:08:46.19 при неизменном `created_at`); DELETE → 204, последующий GET → 404. |
| F1 | **FAIL** | Свежие БД (`learnflow_f1`, `siem_f1`) → `upgrade head` падает на **обеих** БД на миграциях переименования: backend `faab892b94fb` — `ALTER TABLE artifacts RENAME CONSTRAINT "artifacts_pkey" TO "pk_artifacts"` → `UndefinedObject: constraint "artifacts_pkey" ... does not exist`; siem `0917133ea9b5` — аналогично с `correlation_rules_pkey`. Причина: Alembic пробрасывает `naming_convention` из `target_metadata` в runtime `op.create_table`, поэтому на свежей БД ранние миграции сразу создают constraints с convention-именами (`pk_artifacts` и т.д.) — rename-миграции, рассчитанные на дефолтные имена, ломаются. На инкрементально мигрированных БД (как стендовые) head накатывается нормально. Renames нужны условные (по факту существования старого имени). Тестовые БД дропнуты. |
| F2 | PASS | backend: `downgrade add_is_admin_to_users` (через `13f18167a945` и `faab892b94fb`) → `upgrade head` — чисто, current = `13f18167a945 (head)`. siem: `downgrade 004` → `upgrade head` — чисто, current = `d944c66cc700 (head)`. Повторный D3 после наката: обе автогенерации снова пустые. |
| G1 | PASS | `make check`: ruff check — All checks passed; ruff format --check — 153 files already formatted; mypy — Success, 150 source files. `# type: ignore[assignment]` в `siem_service/` отсутствует (grep пуст). |
| G2 | PASS | `make test`: collected 0 items, exit 5 — Makefile-цель явно трактует «no tests collected» как успех (см. комментарий цели `test`); `backend/tests/` пуст по дизайну. EXIT=0. |

## Резюме

**24 кейса: 22 PASS, 2 FAIL, 0 BLOCKED.**

Найденные дефекты:

1. **A1 — ревокация сессий при replay refresh-токена откатывается транзакцией.** API честно отвечает 401
   `Token reuse detected, all sessions revoked`, но `revoke_all_for_user` выполняется в той же сессии, которую
   `get_db_session` откатывает при `HTTPException` из route. Остальные сессии пользователя остаются рабочими —
   защитный механизм replay-детекции фактически не срабатывает. Нужен commit ревокации до проброса ошибки
   (отдельная транзакция или commit внутри сервиса перед raise).
2. **F1 — цепочка миграций не воспроизводится на свежей БД (обе БД).** Rename-миграции
   (`faab892b94fb` backend, `0917133ea9b5` siem) предполагают дефолтные имена constraints, но на чистой БД ранние
   миграции уже создают convention-имена (Alembic применяет `naming_convention` из `target_metadata` к runtime-операциям).
   Bootstrap нового окружения через `alembic upgrade head` невозможен, пока renames не станут условными.

Состояние стенда после прогона: docker-контейнеры работают, обе БД на head, baseline-правила корреляции
(brute_force_auth, injection_spike, targeted_user_attack, mass_suspicious) не тронуты и включены; tc-правила и их
алерты удалены; временные БД `*_f1` дропнуты; drift-файлы автогенерации удалены; поднятые для теста uvicorn-процессы
(8100/8101) остановлены. В данных остались помеченные `tc_`-артефакты: пользователь `tc_user_a1` с refresh-токенами
в main DB и tc-события в `siem_events` (metadata `{"tc": ...}`).

## Повторный прогон после фиксов (основной агент)

Оба FAIL устранены и перепроверены:

| ID | Статус | Фикс и проверка |
|----|--------|-----------------|
| A1 | PASS | `AuthService.refresh`: commit ревокации до `raise ReplayDetectedError` (иначе `get_db_session` откатывал её вместе с HTTPException). Проверка против живого backend (порт 8002): replay → 401, **и** последующий refresh валидным токеном → 401 (вся сессия отозвана). |
| F1 | PASS | Rename-миграции (`faab892b94fb`, `0917133ea9b5`) переведены на условные переименования: на свежей БД naming convention действует уже в ранних миграциях, старых имён нет — rename пропускается; спец-случай `ck_mcp_server_disables_ck_scope_type` учтён. Проверка: bootstrap чистых БД `learnflow_f2`/`siem_f2` до head — успешен; список имён constraints/индексов свежей БД **идентичен** мигрированной (diff пуст); downgrade/upgrade round-trip на основных БД повторно чистый. Временные БД удалены. |
