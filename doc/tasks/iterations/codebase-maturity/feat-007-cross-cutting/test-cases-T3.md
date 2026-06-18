# Тест-кейсы трека T3 — Agent error handling (feat-007)

Страховка целевого поведения трека T3. Покрывают три заботы плана (`plan-T3.md`): tool-отказы больше не ломают thread (`handle_tool_errors=callable`, D-ERR-5 финал), обе дороги деградации guard сведены к единому наблюдаемому сигналу `agent.guard.degraded` + `GRACEFUL_DEGRADATION` (D-ERR-6), главный стрим-барьер логирует с `exc_info`.

Базис решений: D-ERR-5/6, резолюции OQ-A (`handle_tool_errors` = callable), OQ-B («метрика» деградации = канал `security_event`, отдельный счётчик не вводим). Спека целевого состояния — `conventions.md` § «Обработка ошибок» → «Агентные tools» / «Восстановление: fail-safe», § Logging → «Security Event Logging». Эмпирика висячего tool_call — `empirical-reentry-toolnode.md`.

Слои: **Layer 0** — статический gate (`make check`); **Layer 1** — изолированные точечные автотесты (мини-граф + structlog-capture, без сети и LLM); **Layer 2** — наблюдаемость guard fail-open сквозь SIEM-pipeline (стенд, без LLM-ключа); **👤** — полный агентный SSE-smoke (нужен LLM-ключ).

Формат кейса: **{T3.N}** · Layer · Предусловие · Шаги · Ожидаемо · `👤` (если ручной).

Версии для автотестов (зафиксированы эмпирикой): langgraph 1.1.3, langgraph-prebuilt 1.0.8, langgraph-checkpoint 4.0.1. Callable-форма обработчика вызывается как `flag(exc)` (только исключение) и возвращает строку-content для `ToolMessage(status="error")`.

---

## Layer 0 — статический gate

**{T3.1}** · Layer 0
- **Предусловие.** Все фазы трека T3 применены (siem-contracts, `types.py`, `classifier.py`, `guard.py`, `graph.py`, `runner.py`).
- **Шаги.** `make check` (ruff + mypy) из корня.
- **Ожидаемо.** Зелёно. В частности mypy валидирует на call-site `guard.py`, что `event_type=AGENT_GUARD_DEGRADED` входит в `EventType` Literal (требование «event_type из Literal vocabulary, mypy-проверяемо»); ruff не ругается на module-level функцию-обработчик `_handle_tool_error` (это callback-процессор, не синглтон-состояние — допустимо по CLAUDE.md). Импортов внутри функций без `# lazy:`/`# circular:` нет (PLC0415).

**{T3.2}** · Layer 0
- **Предусловие.** Фаза 1 применена (vocabulary + `__init__`).
- **Шаги.** В REPL/тесте: `from siem_contracts import AGENT_GUARD_DEGRADED`.
- **Ожидаемо.** Импорт проходит; `AGENT_GUARD_DEGRADED == "agent.guard.degraded"`; строка присутствует в `EventType` Literal и в `__all__`. Существующие константы (`AGENT_GUARD_INPUT_CLASSIFIER_INJECTION` и т.д.) на месте — добавление аддитивно.

---

## Layer 1 — точечные автотесты (изолированно)

### Целостность thread: handle_tool_errors (D-ERR-5)

**{T3.3}** · Layer 1 · **критичный путь — целостность thread**
- **Предусловие.** Мини-`StateGraph` (`agent` → conditional → `tools` → `agent`) + `InMemorySaver`, в духе `empirical-reentry-toolnode.md`. `agent`-нода фейковая: на первом ходе возвращает `AIMessage` с одним `tool_call`, на последующих — `AIMessage` без tool_calls (терминал). Один tool, который безусловно бросает `RuntimeError("boom")`. `ToolNode(tools, handle_tool_errors=_handle_tool_error)` — целевая конфигурация.
- **Шаги.**
  1. RUN 1: `astream`/`ainvoke` с `HumanMessage` на `thread_id=T`, дать графу дойти до tools и завершиться.
  2. Прочитать state checkpoint'а thread T.
  3. RUN 2 (re-entry): тот же `thread_id=T`, новый `HumanMessage`; прогнать до терминала.
  4. Проверить историю строгой contig-проверкой (каждый `AIMessage(tool_calls)` имеет парный `ToolMessage` с тем же `tool_call_id`; уникальные id, не «по наличию»).
- **Ожидаемо.**
  - После RUN 1 в state есть `ToolMessage(status="error")`, парный к `AIMessage(tool_calls)` — висячего tool_call нет; `next` не залип на `('tools',)`.
  - RUN 2 проходит без падения; история остаётся валидной для OpenAI-совместимого формата (нет последовательности `…AI(tool_calls), Human…` без ответа на tool_call) — баг из эмпирики не воспроизводится.
  - Контраст с дефолтом: при `ToolNode(tools)` (без обработчика) RUN 1 пробросил бы `RuntimeError`, а RUN 2 дал бы невалидную историю — фиксируем как негативную базу (опционально отдельным под-тестом).

**{T3.4}** · Layer 1 · **критичный путь — наблюдаемость + не-утечка**
- **Предусловие.** Тот же мини-граф, что в T3.3; structlog в режиме capture (`structlog.testing.capture_logs` или каплог через ProcessorFormatter).
- **Шаги.** Прогнать RUN 1 (tool бросает `RuntimeError` с «говорящим» текстом, напр. `RuntimeError("DSN=postgres://secret@host")`). Снять лог-записи и content получившегося `ToolMessage`.
- **Ожидаемо.**
  - Обработчик залогировал ровно одну запись уровня `error` (не warning) с `exc_info` (есть тип/стек) и `error_type="RuntimeError"`.
  - `ToolMessage.content` — нейтральное сообщение («Tool execution failed…»); НЕ содержит `repr(exc)`, текста исключения, DSN/секрета, имени модуля, стека. Внутренности уходят только в лог, в контекст модели — безопасная строка.

### Guard: обе дороги деградации → единый наблюдаемый сигнал (D-ERR-6)

**{T3.5}** · Layer 1 · **критичный путь — guard fail-open, дорога 1 (LLM-исключение)**
- **Предусловие.** `SecurityGuard` с подменённым `classifier.classify` — coroutine, бросающая `RuntimeError`. Чекпоинт INBOUND (`USER_INPUT`). Вызов `check(..., observe=False)`. structlog в capture.
- **Шаги.** `await guard.check(content, Checkpoint.USER_INPUT, observe=False)`. Снять `GuardResult` и лог.
- **Ожидаемо.**
  - `GuardResult.verdict == CLEAN`, `detection_layer == DetectionLayer.GRACEFUL_DEGRADATION`, `details == {"reason": "llm_failure"}`, `direction == INBOUND`.
  - Лог-запись: `security_event=True`, `event_type == "agent.guard.degraded"` (НЕ `…classifier_injection`), `severity == "critical"`, `exc_info` присутствует; `metadata` содержит `checkpoint="user_input"`, `direction="inbound"`, `detection_layer="graceful_degradation"`, `verdict="clean"`.

**{T3.6}** · Layer 1 · **критичный путь — direction по checkpoint (фикс F-AGT-03)**
- **Предусловие.** Как T3.5, но чекпоинт OUTBOUND — `FINAL_OUTPUT`.
- **Шаги.** `await guard.check(content, Checkpoint.FINAL_OUTPUT, observe=False)` при `classify`, бросающем исключение.
- **Ожидаемо.** Тот же `event_type == "agent.guard.degraded"`, но `metadata.direction == "outbound"`, `metadata.checkpoint == "final_output"`. Подтверждает, что на OUTBOUND-сбое в SIEM больше НЕ прилетает INPUT-injection-событие (снят дефект «INPUT-событие на OUTPUT-checkpoint» и семантический конфликт `event_type=…INJECTION` при `verdict="clean"`).

**{T3.7}** · Layer 1 · **критичный путь — guard fail-open, дорога 2 (исчерпание ретраев)**
- **Предусловие.** `SecurityGuard` с реальным `LLMClassifier`, у которого guard-LLM (`ainvoke`) всегда возвращает невалидный вердикт (например `"MAYBE"`) → `classify` исчерпывает `max_retries` и возвращает `ClassifierResult(verdict=CLEAN, degraded=True, retries=max_retries)`. structlog в capture. Проверить на обоих направлениях (`USER_INPUT` и `FINAL_OUTPUT`).
- **Шаги.** `await guard.check(content, checkpoint, observe=False)`.
- **Ожидаемо.**
  - `GuardResult.verdict == CLEAN`, `detection_layer == DetectionLayer.GRACEFUL_DEGRADATION`, `details == {"reason": "retries_exhausted"}`.
  - Лог: `security_event=True`, `event_type == "agent.guard.degraded"`, `severity == "critical"`, `metadata` с `checkpoint`, `direction` (по checkpoint), `detection_layer="graceful_degradation"`, `verdict="clean"`. Раньше эта дорога была тихой (без `security_event`) — теперь наблюдаема (закрыт F-AGT-04 / нарушение D1).
  - Блок эмита injection-события НЕ срабатывает (verdict=CLEAN) — порядок ветвления сохранён.

**{T3.8}** · Layer 1 · юнит
- **Предусловие.** `LLMClassifier` с подменённым guard-LLM.
- **Шаги.** (а) LLM всегда отдаёт невалидный вердикт → `classify` до исчерпания `max_retries`; (б) LLM с первого раза отдаёт `"CLEAN"`.
- **Ожидаемо.** (а) `ClassifierResult.degraded is True`, `retries == max_retries`, `verdict == CLEAN`; (б) `degraded is False`, `verdict == CLEAN`. Подтверждает, что guard.py может различать «честный CLEAN» и «CLEAN-из-деградации» (корень F-AGT-04).

### Регрессии (целевое поведение не должно сломать смежное)

**{T3.9}** · Layer 1 · регрессия — injection-путь не задет ветвлением degraded
- **Предусловие.** `SecurityGuard`, `classifier.classify` отдаёт `ClassifierResult(verdict=INJECTION, degraded=False)`. structlog capture. Проверить INBOUND (`USER_INPUT`) и OUTBOUND (`FINAL_OUTPUT`).
- **Шаги.** `await guard.check(content, checkpoint, observe=False)`.
- **Ожидаемо.** `GuardResult.verdict == INJECTION`, `detection_layer == LLM_CLASSIFIER` (НЕ graceful). Лог: `event_type == AGENT_GUARD_INPUT_CLASSIFIER_INJECTION` для INBOUND и `…OUTPUT_CLASSIFIER_INJECTION` для OUTBOUND (выбор по direction сохранён). Ветка degraded не перехватила нормальный injection-вердикт.

**{T3.10}** · Layer 1 · регрессия — core-store fail-fast в `agent_node` остаётся (вне scope изменения, проверяем сохранность)
- **Предусловие.** Граф/`agent_node` с `runtime.store is None` (или мини-репро того же контракта).
- **Шаги.** Вызвать `agent_node` при `store is None`.
- **Ожидаемо.** `RuntimeError("Agent graph requires a Store…")` бросается ДО генерации tool_calls (`graph.py:225-226`) — сироты-`AIMessage(tool_calls)` не возникает, история валидна. Это «настоящий» fail-fast core-зависимости; `handle_tool_errors` к нему не применяется и его НЕ маскирует. Подтверждает разведение двух забот D-ERR-5 (core fail-fast vs tool-level degrade).

---

## Layer 2 — наблюдаемость guard fail-open сквозь SIEM (стенд, без LLM-ключа)

**{T3.11}** · Layer 2
- **Предусловие.** Стенд с включённым SIEM-pipeline (`SecurityEventProcessor` → Redis Stream → siem-ingestion). LLM-ключ НЕ нужен: guard-классификатор подменяется/конфигурируется на гарантированный сбой (недоступная guard-модель или fault-inject в `classify`). Можно поднять только нужные сервисы (Redis + siem).
- **Шаги.** Спровоцировать вызов guard на любом активном чекпоинте так, чтобы сработала деградация (LLM-исключение или исчерпание ретраев). Проверить, что событие дошло до SIEM (по логам ingestion / по хранилищу SIEM-событий).
- **Ожидаемо.** В SIEM наблюдается событие `event_type == "agent.guard.degraded"`, `severity == "critical"`; identifiers (`request_id`, `thread_id`, `user_id`) подтянуты из contextvars автоматически; в `metadata` — `checkpoint`/`direction`. Это и есть «метрика» деградации по OQ-B: отдельного счётчика нет, источник для дашбордов/алертов — агрегация SIEM по `event_type`. Молчаливой деградации не остаётся ни по одной дороге.

---

## 👤 Ручной агентный SSE-smoke (нужен LLM-ключ)

**{T3.12}** · 👤 · **боевой re-entry (главная ценность D-ERR-5)**
- **Предусловие.** `make docker-up` (или `docker-up-db` + `dev`), валидный LLM-ключ; tool, который в данном прогоне реально бросит исключение (например, спровоцировать падение на записи в KS/memory или временно недоступный MCP-tool).
- **Шаги.** 1) В реальном чате запрос, ведущий к вызову проблемного tool. 2) После ответа — следующее сообщение в тот же thread.
- **Ожидаемо.** Первый ход не рвёт стрим: агент получает error-`ToolMessage`, реагирует, клиент получает осмысленный ответ/восстановление (без сырого 500). Второй ход на том же thread проходит штатно — thread остался рабочим (боевой re-entry, не только мини-граф). В логах — `error` + `exc_info` обработчика tool-ошибки; клиенту внутренности не утекли.
- `👤`

**{T3.13}** · 👤 · guard fail-open под реальным классификатором
- **Предусловие.** Стенд с заведомо недоступной/битой guard-моделью (деградация дороги 1) либо моделью, стабильно дающей невалидный вердикт (дорога 2). Валидный основной LLM-ключ.
- **Шаги.** Отправить обычное сообщение в чат.
- **Ожидаемо.** Запрос проходит (fail-open, приоритет UX — D-ERR-9): пользователь получает ответ. В логах/SIEM виден `agent.guard.degraded` (`severity=critical`) с корректным `direction`/`checkpoint`. Подтверждает целевую fail-safe-семантику на боевом контуре.
- `👤`

**{T3.14}** · 👤 · стрим-барьер runner (F-AGT-01)
- **Предусловие.** Стенд + LLM-ключ; способ спровоцировать неожиданный сбой стрима, НЕ связанный с tool (после фазы 4 tool-исключения до барьера не долетают) — напр. транзиентный сбой checkpointer/нижележащего стрима.
- **Шаги.** Спровоцировать сбой в теле стрим-цикла руннера.
- **Ожидаемо.** Барьер логирует уровнем `error` с `error_type` и `exc_info` (не `warning` с голым `str(e)`). Клиент по-прежнему получает безопасный `detail` через `normalize_error_message` (трансляция не тронута, F-AGT-06). Оператор видит тип и стек.
- `👤`

---

## Gate и сводка

**Gate трека.** `make check` (ruff + mypy) — обязателен после каждой фазы и в финале (T3.1). `make test` — если в репо есть релевантные существующие тесты (на момент трека `backend/tests/` практически пуст; точечные автотесты этого трека НЕ оседают в живой `backend/tests/`, а архивируются в артефакты итерации — feat-009 решит, что влить, per `conventions.md` § Тестирование).

**👤-список (нужен LLM-ключ / стенд).** T3.12 (боевой re-entry tool-исключения), T3.13 (guard fail-open под реальным классификатором), T3.14 (стрим-барьер). T3.11 (Layer 2) ключа не требует, но требует стенд с SIEM.

**Предлагаемые точечные автотесты** (изолированно, без сети — пишутся по ходу трека, архивируются):
- T3.3 — handle_tool_errors закрывает thread + валидный re-entry (**критичный**, мини-`StateGraph` + `InMemorySaver`).
- T3.4 — обработчик логирует `error`+`exc_info` и content не течёт (**критичный**).
- T3.5 / T3.6 — guard дорога 1, INBOUND и OUTBOUND, `event_type=agent.guard.degraded` + `direction` по checkpoint (**критичные**, развивают feat-006 fault-injection probe).
- T3.7 — guard дорога 2 (исчерпание ретраев) наблюдаема (**критичный**).
- T3.8 — `ClassifierResult.degraded` сигнал (юнит).
- T3.9 — injection-путь не задет ветвлением degraded (регрессия).
- T3.10 — core-store fail-fast в `agent_node` сохранён (регрессия).
- T3.2 — import-smoke `AGENT_GUARD_DEGRADED` (тривиальный, можно как часть guard-тестов).
