# Harvest proposals: feat-011 — Продуктовые субагенты v1

Кандидаты в backlog / конвенции на апрув архитектора (pre-commit gate). Финальную консолидацию делает harvester на фазе HARVEST; до неё сюда дописывает anytime-кандидатов только оркестратор.

## Anytime-кандидаты (оркестратор, по ходу итерации)

- **[backlog / tech debt]** Вынести транзакционный multi-session harness (`outer_conn`/`_bound_session`/`tool_session_factory`/`seed_session`) в `packages/testing/db.py`. Источник: находка test-reviewer **R1 minor [infra]** (`tracks/T1/test-cases.md` § «Находки ревью»): harness скопирован дословно из `backend/tests/image_generation/conftest.py` в `backend/tests/subagents/conftest.py` — обычный `transactional_session` из `packages/testing` не покрывает случай нескольких sibling-сессий на одном соединении (tool открывает свою сессию). Два scope'а с дублем разъедутся; правка замороженной тест-инфры посреди итерации отклонена оркестратором как несоразмерная minor-severity.
