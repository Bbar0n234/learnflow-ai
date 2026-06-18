# Code review — T3 Agent error handling (домен: agent runtime + siem-contracts)

Reviewer: code-reviewer (AIDD). Diff: `develop...HEAD -- backend/app/agent packages/siem-contracts doc/tech/security-events.md`.

## Summary

Трек T3 реализован в полном соответствии с D-ERR-5 (финал), D-ERR-6 и резолюциями OQ-A/OQ-B. Семантических дефектов корректности нет — **blocker'ов 0**. Найдены 1 nice-to-have (несогласованность уровня лога между двумя дорогами деградации) и 2 nit (доковый дрейф в conventions.md §335; sub-cause деградации не попадает в SIEM-metadata).

Проверено по существу:

- **`handle_tool_errors` (OQ-A callable).** `_handle_tool_error(exc: Exception) -> str` логирует `logger.error(..., exc_info=exc)` и возвращает константу `_TOOL_ERROR_MESSAGE` — НЕ `repr(exc)`/DSN/стек. Контракт фреймворка верифицирован по установленному `langgraph.prebuilt.tool_node`: callable вызывается как `flag(e)` (один аргумент), а `_infer_handled_types` по аннотации `Exception` ловит ВСЕ `Exception` (но не `BaseException` → `CancelledError`/`KeyboardInterrupt` корректно пробрасываются). Сигнатура и аннотация совпадают. Утечки в контекст LLM нет.
- **Thread остаётся валидным.** Любое `Exception` в tool → `ToolMessage(status="error")`, ReAct-шаг закрывается. Висячего `AIMessage(tool_calls)` не остаётся (эмпирика `empirical-reentry-toolnode.md` закрыта).
- **Core-store fail-fast СОХРАНЁН.** `graph.py:245-246` (`runtime.store is None → RuntimeError`) на месте; это `agent_node`, не tool, поэтому `handle_tool_errors` его не глотает — fail-fast пробрасывается до барьера `runner.py`. Семантика «агент не работает без памяти» цела.
- **Обе дороги guard-деградации наблюдаемы и эмитят `agent.guard.degraded` + `direction`.** Дорога 1 (LLM-исключение, guard.py:149-173) и дорога 2 (исчерпание ретраев, guard.py:177-200) дают `security_event=True`, `event_type=AGENT_GUARD_DEGRADED`, `severity="critical"`, `detection_layer=graceful_degradation`, `metadata.direction=direction.value`. Дефект F-AGT-03 (INPUT-событие на OUTBOUND + `event_type=...INJECTION` при `verdict=clean`) устранён.
- **`ClassifierResult.degraded` различает корректно.** Валидный вердикт → `degraded` по умолчанию `False`; только ветка исчерпания ретраев возвращает `degraded=True` (classifier.py:130-135). Guard ветвится по этому полю до блока эмита injection.
- **Injection-путь guard не сломан.** Детерминированные слои (loop, short-circuit), skip-classifier и classifier-INJECTION эмит (`AGENT_GUARD_*_CLASSIFIER_INJECTION` с выбором по direction) не тронуты. Новый degraded-early-return стоит до injection-блока, но при `verdict=CLEAN` injection-блок и так не сработал бы — порядок ветвления корректен. Подтверждено регрессионным тестом T3.9.
- **Direction (INBOUND/OUTBOUND).** `direction_of(checkpoint)` через `_DIRECTION_MAP` (TOOL_CALL_ARG/FINAL_OUTPUT → OUTBOUND, остальное INBOUND); пишется в metadata обеих дорог. Тесты T3.5/T3.6 проверяют оба направления.
- **Барьер стрима runner.** `runner.py:228` поднят `warning`→`error` + `error_type` + `exc_info=e`; трансляция клиенту (`normalize_error_message`) не тронута — внутренности только в лог.
- **`event_type` в Literal vocabulary.** `AGENT_GUARD_DEGRADED = "agent.guard.degraded"` добавлен в `vocabulary.py` (константа + `EventType` Literal) и реэкспортирован в `__init__.py` (`__all__`). Import-smoke и присутствие в Literal проверены тестом T3.2.
- **Проглоченных исключений нет; structlog keyword-args везде.** Doc-каталог `security-events.md` дополнен строкой `agent.guard.degraded` с идентификаторами, консистентными с прочими `agent.guard`-строками.

## Findings

| # | Severity | Файл / место | Замечание |
|---|----------|--------------|-----------|
| 1 | nice-to-have | `backend/app/agent/security/guard.py:151` vs `:179` | Две дороги одной и той же деградации логируются на РАЗНЫХ уровнях: дорога 1 — `logger.error`, дорога 2 — `logger.warning`. SIEM-сигнал идентичен (`security_event=True`, `severity="critical"` ловится на обоих уровнях), поэтому «одинаково наблюдаемы» по D-ERR-6 формально выполнено. Но в человеко-логе разнобой: одно и то же событие `agent.guard.degraded` всплывает то как ERROR, то как WARNING. Различие защитимо (дорога 1 несёт реальное исключение → `error`+`exc_info`; дорога 2 исключения не имеет), но стоит либо сознательно зафиксировать это правило, либо выровнять уровень. Не blocker. |
| 2 | nit | `doc/tech/conventions.md:335` | Доковый дрейф: §«Агентные tools» буквально предписывает `ToolNode(tools, handle_tool_errors=True)`, тогда как OQ-A финально выбрал callable именно потому, что `=True` глушит исключение молча. Та же строка требует «логируется (`exc_info` + метрика)» — `=True` это требование не удовлетворяет, т.е. текст противоречит сам себе и реализации. Plan-T3 фаза 6 синхронизировала только `security-events.md`. Кандидат на правку дрейфа: заменить `=True` на callable-форму (или формулировку, не привязанную к булеву флагу). |
| 3 | nit | `backend/app/agent/security/guard.py:156-161, 184-189` | Sub-cause деградации (`llm_failure` vs `retries_exhausted`) попадает только в `GuardResult.details`, но не в SIEM-`metadata` (там обе дороги дают идентичный набор). Это by-design по D-ERR-6 («один сигнал»), однако добавление `"reason"` в metadata дало бы SIEM-триажу различать инфра-сбой LLM и деградацию качества ответа без обращения к Langfuse. Опционально. |

## Blocker без прецедента

Нет. Blocker'ов не выявлено.
