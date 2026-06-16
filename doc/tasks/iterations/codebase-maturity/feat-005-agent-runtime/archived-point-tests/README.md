# Архив точечных автотестов feat-005

Автотесты написаны по ходу slice feat-005 (Agent Runtime) и **перенесены сюда
из `backend/tests/`** по конвенции фазы (см. tasklist § «Принципы…»): живую
тестовую инфраструктуру проектирует с нуля feat-009 (Testing), поэтому до неё
точечные тесты не держатся в живой инфраструктуре, а сохраняются как
артефакт-бэкап. Аналогично архиву feat-004.

Они отработали своё: **46 PASS** на момент завершения slice; в процессе поймали
латентный циклический импорт `app.infra.llm ↔ app.agent` (фикс остался в коде —
аннотационные импорты под `TYPE_CHECKING` в `backend/app/infra/llm.py`).

## Состав

Файлы переименованы без префикса `test_` (`*_tests.py`), чтобы pytest не подбирал
их из `doc/` — это архив, не запускаемый набор.

- `llm_factories_tests.py` — безусловный `ReasoningChatOpenAI`, дедуп фабрик, удаление 2 мёртвых функций.
- `model_config_resolver_tests.py` — публичный `default()`.
- `user_memory_tools_tests.py` — `ToolRuntime` + `RuntimeError` (контракт-чейндж с error-строки).
- `stream_event_mapper_tests.py` — updates → SSE (tool_start/tool_end/artifact_created).
- `agent_run_tracer_tests.py` — enabled через DI (закрытие module-global), no-op/degrade, mid-stream observation.
- `checkpoint_history_tests.py` — чтение/маппинг checkpointer, граница скана redaction.
- `runtime_security_enforcer_tests.py` — 4 security-чекпоинта, payload редакции, block_reason (критичный путь).
- `langfuse_init_tests.py` — `init_langfuse() -> bool` (нет ключей / auth fail / success).
- `conftest_tests.py` — очистка proxy-env перед конструированием `ChatOpenAI` (специфика sandbox-окружения; в реальной инфре может не понадобиться).

## Для feat-009

Сырьё, не готовая рамка. Async-тесты написаны через `asyncio.run()` внутри
синхронных функций (без `pytest-asyncio`). При переносе в живую инфраструктуру:
вернуть префикс `test_`, решить про `pytest`/`pytest-asyncio` в dev-deps,
унифицировать фикстуры/фейки (`_FakeGuard`/`_FakeGraph`/`_FakeCheckpointer`
дублируются между файлами). Критичный путь (RuntimeSecurityEnforcer) — кандидат
в обязательное покрытие.
