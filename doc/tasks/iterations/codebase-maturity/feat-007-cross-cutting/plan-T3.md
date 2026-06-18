# План трека T3 — Agent error handling (feat-007)

Фрагмент плана итерации feat-007. Трек закрывает три заботы из аудита agent-runtime:

1. **Tool-level отказы больше не ломают thread** — `ToolNode(tools, handle_tool_errors=...)`: любое исключение в tool → `ToolMessage(status="error")`, ReAct-шаг закрывается, история валидна (D-ERR-5 финал, эмпирика `empirical-reentry-toolnode.md`). Core-зависимость store остаётся fail-fast в `agent_node` — **не трогаем**. Репарацию старых тредов **не делаем**.
2. **Обе дороги деградации guard в CLEAN наблюдаемы** (D-ERR-6): дорога 1 (LLM-исключение) уже наблюдаема, но размечена дефектно; дорога 2 (исчерпание ретраев классификатора) сейчас тихая. Сводим обе к единому каноническому `event_type` `agent.guard.degraded` + `DetectionLayer.GRACEFUL_DEGRADATION`.
3. **Инфра-класс tool-ошибок и главный стрим-барьер наблюдаемы** (F-AGT-01): барьер `runner.py` логирует с `exc_info`, уровень `error`; обработчик tool-ошибок логирует `exc_info`.

Базис: D-ERR-5, D-ERR-6 (`decisions.md`); спека — `conventions.md` § «Обработка ошибок» → «Агентные tools», «Восстановление: fail-safe», § Logging → «Security Event Logging». Конвенции уже описывают целевое состояние (`agent.guard.degraded`, `handle_tool_errors`, fail-fast store) — этот план приводит код в соответствие.

API LangGraph проверен по установленному пакету (langgraph-prebuilt 1.0.8): `handle_tool_errors: bool | str | Callable[..., str] | type[Exception] | tuple[...]`. Callable вызывается как `flag(e)` (только исключение, без имени tool) и возвращает строку-content для `ToolMessage(status="error")`. Это штатный механизм фреймворка под ReAct.

---

## Фаза 1 — Канонический event_type деградации в siem-contracts ⚠️ пересечение с T4

**Цель.** Завести отдельный канонический `event_type` для деградации guard (не переиспускать injection-событие). По `conventions.md:330` имя зафиксировано: `agent.guard.degraded`. Направление (INPUT/OUTPUT) НЕ зашивается в имя — для деградации тип один, направление и checkpoint уходят в `metadata`.

**Изменения по файлам.**
- `packages/siem-contracts/siem_contracts/vocabulary.py`:
  - константа `AGENT_GUARD_DEGRADED = "agent.guard.degraded"` (в блоке `# Agent security guard events`);
  - добавить `"agent.guard.degraded"` в `EventType` Literal.
- `packages/siem-contracts/siem_contracts/__init__.py`: импорт `AGENT_GUARD_DEGRADED` из vocabulary + строка в `__all__`.

**Verification.** `make check` (mypy валидирует Literal на call-site в guard.py фазы 3). Точечно: `from siem_contracts import AGENT_GUARD_DEGRADED` импортируется.

**Пересечение.** `vocabulary.py` и `__init__.py` — shared package `siem-contracts`, тот же файл правит T4. Координировать порядок мерджа: добавление новой константы аддитивно (не ломает существующие), но оба трека трогают `EventType` Literal и `__all__` → вероятен конфликт слияния. Разрешается тривиально (обе стороны только добавляют строки).

---

## Фаза 2 — Сигнал деградации в ClassifierResult (дорога 2)

**Цель.** Дать `LLMClassifier.classify` способ сообщить вызывающему, что CLEAN — результат исчерпания ретраев (деградация), а не настоящий вердикт. Сейчас оба случая возвращают одинаковый `ClassifierResult(verdict=CLEAN)` → guard.py не может их различить (корень F-AGT-04).

**Изменения по файлам.**
- `backend/app/agent/security/types.py`: в `ClassifierResult` добавить поле `degraded: bool = False`.
- `backend/app/agent/security/classifier.py:130-134`: ветка исчерпания ретраев возвращает `ClassifierResult(verdict=CLEAN, reasoning=None, retries=max_retries, degraded=True)`. Существующий `logger.warning("classifier retries exhausted...")` оставить (это внутренний WARNING ретраев; наблюдаемый security-event эмитит guard в фазе 3, чтобы вся разметка деградации была в одном месте).

**Verification.** `make check`. Точечный автотест в фазе 7 (исчерпание ретраев → `degraded=True`).

---

## Фаза 3 — Guard: обе дороги деградации под единый наблюдаемый сигнал

**Цель.** Свести дорогу 1 (LLM-исключение) и дорогу 2 (исчерпание ретраев) к ОДНОМУ наблюдаемому сигналу: `security_event=True` + `event_type=AGENT_GUARD_DEGRADED` + `severity="critical"` + `DetectionLayer.GRACEFUL_DEGRADATION` + `metadata` с `checkpoint`/`direction`. Исправить дефект разметки дороги 1 (F-AGT-03) и сделать дорогу 2 наблюдаемой (F-AGT-04).

**Изменения по файлам** (`backend/app/agent/security/guard.py`):
- Импорт: добавить `AGENT_GUARD_DEGRADED` из `siem_contracts`.
- **Дорога 1** (`except Exception`, строки 148-171): заменить зашитый `event_type=AGENT_GUARD_INPUT_CLASSIFIER_INJECTION` на `AGENT_GUARD_DEGRADED`. Это снимает оба дефекта F-AGT-03: (а) INPUT-событие на OUTPUT-checkpoint'ах, (б) семантический конфликт `event_type=...INJECTION` при `verdict="clean"`. В `metadata` добавить `"direction": direction.value` (checkpoint уже есть). `details={"reason": "llm_failure"}` оставить.
- **Дорога 2** (после успешного `classify`, строки 173-185): если `classifier_result.degraded` — построить `GuardResult` с `detection_layer=GRACEFUL_DEGRADATION`, `verdict=CLEAN`, `details={"reason": "retries_exhausted"}` И эмитить `logger.warning("guard classifier degraded, ...", security_event=True, event_type=AGENT_GUARD_DEGRADED, severity="critical", metadata={checkpoint, direction, detection_layer=graceful_degradation, verdict="clean"})`. Иначе — текущая ветка `detection_layer=LLM_CLASSIFIER`. Блок эмита injection-события (строки 187-207) при degraded не срабатывает (verdict=CLEAN) — порядок ветвления сохранить.

**Замечание по «метрике».** Конвенция требует «security_event + метрика». В проекте нет отдельной metrics-инфраструктуры (Prometheus/StatsD); единственный счётчик — in-memory dict в `security_pipeline/transport.py`. Дорога 1 уже сейчас реализует «метрику» именно через `security_event` (SIEM-pipeline агрегирует события по `event_type` — это и есть источник метрики для дашбордов, см. `observability.md`). Дорога 2 приводится к тому же паттерну. Отдельный счётчик не вводим (см. Open Questions).

**Verification.** `make check`. Точечные автотесты в фазе 7 (обе дороги → правильный event_type/layer/direction).

---

## Фаза 4 — ToolNode: наблюдаемый handle_tool_errors

**Цель.** Закрыть корректностный баг висячего tool_call (D-ERR-5): любое исключение в tool → `ToolMessage(status="error")`, thread валиден. Одновременно сохранить наблюдаемость инфра-класса tool-ошибок (`exc_info` — F-AGT-01): при `handle_tool_errors=True` (bool) фреймворк гасит исключение в `ToolMessage` **молча**, без лога. Поэтому используем callable-форму обработчика — это документированный штатный вариант, который и закрывает thread, и логирует.

**Изменения по файлам** (`backend/app/agent/graph.py`):
- Модульная функция-обработчик (pure callback вне request-scope — module-level state не нарушает: это не синглтон-состояние, а функция-обработчик; CLAUDE.md явно допускает callbacks/processors):
  ```
  def _handle_tool_error(exc: Exception) -> str:
      logger.error("tool execution failed", error_type=type(exc).__name__, exc_info=exc)
      return <generic non-leaking message>
  ```
  Возвращаемая строка идёт в `ToolMessage(status="error")` → её увидит агент (LLM), не напрямую клиент. Не возвращать `repr(exc)` (дефолтный шаблон LangGraph), чтобы внутренности не утекали в контекст модели; вернуть нейтральное «Tool execution failed; ...». Конкретная формулировка — деталь реализации (константа в коде, не env: это сообщение для агента, не операционная настройка).
- `graph.py:339`: `tool_node = ToolNode(tools, handle_tool_errors=_handle_tool_error)`.

**Замечание по «метрике» tool-ошибок.** Как и в фазе 3, отдельного metrics-backend нет. Обработчик даёт `logger.error(exc_info=...)` (queryable в лог-агрегации). Выделенный счётчик tool-ошибок — Open Question (нет инфраструктуры; callable получает только исключение, без имени tool, что ограничивает лейблирование).

**Альтернатива (отклонена).** `handle_tool_errors=True` буквально из текста D-ERR-5 — даёт thread-валидность, но НЕ даёт лог `exc_info` (исключение гасится молча и больше не доходит до барьера runner). Противоречит требованию D-ERR-5 «лог exc_info + метрика». Callable — единственная форма, удовлетворяющая обоим условиям. Вынесено в Open Questions для явного подтверждения архитектором.

**Verification.** `make check`. Точечный автотест в фазе 7 (tool бросает → `ToolMessage(status="error")`, нет висячего tool_call, повторный вход на thread валиден; обработчик залогировал). Подход — мини-`StateGraph` + `InMemorySaver` в духе `empirical-reentry-toolnode.md`.

---

## Фаза 5 — Главный стрим-барьер runner (F-AGT-01)

**Цель.** Барьер `except Exception` в стриме руннера сейчас логирует `logger.warning(... error=str(e))` — оператор не видит ни stack trace, ни типа, а это last-resort для всех неожиданных ошибок контура. Поднять до `error` + `exc_info`.

**Изменения по файлам** (`backend/app/agent/runner.py:226-234`):
- `logger.warning("agent stream error", thread_id=..., error=str(e))` → `logger.error("agent stream error", thread_id=..., error_type=type(e).__name__, exc_info=e)`.
- Трансляцию клиенту (`normalize_error_message`) НЕ трогать — она корректна (F-AGT-06): клиент по-прежнему получает безопасный текст, внутренности уходят только в лог.

**Замечание.** После фазы 4 tool-исключения до этого барьера больше не долетают (гасятся в `ToolMessage`). Барьер остаётся для прочих неожиданных сбоев стрима — его наблюдаемость по-прежнему нужна.

**Verification.** `make check`. Автотест на барьер затратен (нужен полный стрим) — отнести к ручному/интеграционному (фаза 7).

---

## Фаза 6 — Дрейф документации

**Цель.** Документация описывает текущее состояние; после введения `agent.guard.degraded` каталог security-событий обязан его содержать.

**Изменения по файлам.**
- `doc/tech/security-events.md`: добавить строку в каталог `agent.guard` — `agent.guard.degraded` | `critical` | «LLM-guard деградировал в CLEAN (исключение LLM или исчерпание ретраев классификатора)» | identifiers `request_id, thread_id, user_id`. При необходимости — упоминание в обзоре домена `agent.guard`.
- Сверить (без правок, если уже консистентно): `conventions.md:330` (`agent.guard.degraded` — уже есть), `observability.md:121` (`graceful_degradation` в перечне `detection_layer` — уже есть). Правки только при обнаружении расхождения.

**Verification.** Визуальная сверка; `make check` (md не покрывает, но запустить общий gate в финале трека).

---

## Фаза 7 — Verification и тест-кейсы (отдельная фаза)

Per `conventions.md` § Тестирование: основная страховка — ручные тест-кейсы (отдельный артефакт, прогон агентом-тестировщиком). Точечные автотесты пишутся по ходу и архивируются в артефакты итерации (не оседают в `backend/tests/`); feat-009 решит, что влить.

**Общий gate.** `make check` (ruff + mypy) — обязателен после каждой фазы и в финале трека. `make test` — если в репо есть релевантные существующие тесты.

**Кандидаты в точечные автотесты:**
- **Guard дорога 1 (LLM-исключение).** Подменить `classifier.classify` на coroutine, бросающую `RuntimeError`; вызвать `guard.check(..., observe=False)` на OUTBOUND-checkpoint (напр. `FINAL_OUTPUT`). Ожидание: `GuardResult.verdict=CLEAN`, `detection_layer=GRACEFUL_DEGRADATION`; в логах security-event с `event_type="agent.guard.degraded"` (НЕ injection) и `metadata.direction="outbound"`. Захват лога — через structlog capture / `caplog`. (Развивает feat-006 test-case на fault-injection probe.)
- **Guard дорога 2 (исчерпание ретраев).** Подменить guard-LLM так, чтобы `ainvoke` всегда возвращал невалидный вердикт → `classify` исчерпывает `max_retries`. Ожидание: `ClassifierResult.degraded=True`; `GuardResult.detection_layer=GRACEFUL_DEGRADATION`, `verdict=CLEAN`, `details.reason="retries_exhausted"`; security-event `event_type="agent.guard.degraded"`.
- **ClassifierResult сигнал.** Юнит: исчерпание ретраев → `degraded=True`, валидный ответ → `degraded=False`.
- **handle_tool_errors закрывает thread.** Мини-`StateGraph` (agent→tools→agent) + `InMemorySaver`, tool бросает `RuntimeError`. Ожидание: после прогона в state есть `ToolMessage(status="error")` парный к `AIMessage(tool_calls)` (нет висячего tool_call); повторный вход с новым `HumanMessage` на тот же thread даёт валидную историю; обработчик залогировал `error`+`exc_info`.
- **handle_tool_errors не течёт.** Возвращаемый content не содержит `repr(exc)` / внутренностей.

**Ручной smoke (👤 — нужен LLM-ключ):**
- 👤 End-to-end: tool в реальном чате бросает исключение → клиент получает корректный ответ/восстановление, thread остаётся рабочим при следующем сообщении (проверка боевого re-entry, не только мини-графа).
- 👤 Guard под реальным классификатором: деградация (например, заведомо недоступная guard-модель) → запрос проходит (fail-open), в SIEM/логах виден `agent.guard.degraded`.
- 👤 Стрим-барьер: спровоцировать неожиданный сбой стрима → лог уровня `error` с `exc_info`, клиент получает безопасный `detail`.

---

## Файлы трека

Изменяемые:
- `packages/siem-contracts/siem_contracts/vocabulary.py` ⚠️ T4
- `packages/siem-contracts/siem_contracts/__init__.py` ⚠️ T4
- `backend/app/agent/security/types.py`
- `backend/app/agent/security/classifier.py`
- `backend/app/agent/security/guard.py`
- `backend/app/agent/graph.py`
- `backend/app/agent/runner.py`
- `doc/tech/security-events.md`

Только сверка (правка при дрейфе):
- `doc/tech/conventions.md` (§ 330 — `agent.guard.degraded`)
- `doc/tech/observability.md` (§ 121 — `detection_layer`)

Не трогаем (явно вне scope T3):
- `backend/app/agent/graph.py:225-226` — fail-fast store в `agent_node` (семантика сохраняется).
- `runner.py` / `CheckpointHistory` репарация висячих тредов — D-ERR-5: не делаем.
- `tools/*` — `store is None` отдельной проверкой не выделяем (станет error-`ToolMessage` как любое исключение, D-ERR-5 финал).

---

## Open Questions

1. **«Метрика» без metrics-инфраструктуры.** Конвенция требует «security_event + метрика» (guard) и «лог exc_info + метрика» (tool-ошибки), но в проекте нет metrics-backend (только in-memory dict в `security_pipeline/transport.py`). План реализует «метрику» через security_event (для guard — SIEM агрегирует по event_type) и через `logger.error` (для tool-ошибок — queryable в логах). Подтвердить, что выделенный счётчик (Prometheus/StatsD) НЕ вводим в feat-007 (введение — архитектурное решение).
2. **`handle_tool_errors`: callable vs `True`.** D-ERR-5 буквально пишет `ToolNode(tools, handle_tool_errors=True)`, но та же D-ERR-5 требует «лог exc_info + метрика» для tool-ошибок. `True` (bool) гасит исключение молча, без лога. План использует callable-обработчик — единственную форму, удовлетворяющую обоим условиям (и thread-валидность, и наблюдаемость). Подтвердить выбор callable.
