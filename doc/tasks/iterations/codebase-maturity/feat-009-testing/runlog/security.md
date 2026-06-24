# Ф3 · S2 — Agent guard / prompt-injection · run-log

Скоуп S2 (критпуть, максимальная глубина). Автор тестов независим от автора
кода (A6). Только `backend/tests/security/` тронут; харнес `packages/testing`,
общие conftest, прод-код, Makefile/pyproject — не трогались.

## Возобновление

Предыдущий прогон S2 упал из-за перезагрузки, оставив 11 тест-файлов (108
зелёных тестов) + локальный conftest. Решение: достроить, не переписывать.
Существующие тесты признаны корректными по стилю (sociable, поведение через
публичный интерфейс, дубли по правилу, StubGuard/classifier-фейки из харнеса).
Доведено до 140 зелёных.

## Что было (108 тестов, зелено, но не валидировано mypy/ruff)

- `test_canary_token`, `test_classifier`, `test_corpus`, `test_detectors`,
  `test_event_processor`, `test_event_transport`, `test_guard`, `test_observer`,
  `test_runtime_security`, `test_security_context`, `test_types` + `conftest.py`
  (`make_guard`/`make_classifier`/`StubPromptProvider`/`RecordingGraph`/
  `FakeCheckpointer`).

## Достроено (+32 теста → 140)

Закрыты осмысленные пробелы покрытия, выявленные branch-coverage'ом:

- **`test_history_formatter.py` (новый, 6 тестов).** `format_for_classifier` был
  в скоупе, но без теста (12% покрытия). Чистая функция: XML-обёртка, role-
  префиксы USER/ASSISTANT/SYSTEM/TOOL:name, фолбэк `TOOL:unknown`, current_content
  последней строкой, коэрсия не-str content. → 100%.
- **`test_observer.py` (+6).** Был покрыт только fail-safe путь (None-handle).
  Добавлены spy-объекты в `ObservationHandle` напрямую: `finalize` ставит уровень
  guard-обсервации по `VERDICT_TO_LEVEL` (DEFAULT/WARNING/ERROR), помечает
  root-трейс `blocked=True` строго на INJECTION, прокидывает detection_layer/
  details в metadata. Проверяется payload, который строит наш код, а не Langfuse-
  wire. → 69%.
- **`test_event_transport.py` (+4).** `publisher_loop`: публикует из очереди и
  чисто останавливается на cancel; считает `producer_publish_errors` и
  продолжает работу при сбое `xadd`. `graceful_shutdown`: счётчик ошибок при
  падении redis. → 90%.
- **`test_runtime_security.py` (+4).** Симметрия guard-off для `check_mid_stream`
  / `check_final_output` (был только `check_user_input`). Graceful degradation:
  при падении `aupdate_state` (чекпойнтер) — INJECTION всё равно репортится
  блокировкой, verdict возвращается, без краха. → 89%.
- **`test_classifier.py` (+2).** История прокидывается через
  `format_for_classifier` в промпт (capturing prompt-provider). Reasoning из
  `additional_kwargs` попадает в `ClassifierResult.reasoning`. → 98%.
- **`test_event_processor.py` (+4).** UUID-passthrough event_id, парсинг ISO-
  timestamp, коэрсия не-dict metadata в `{}`, устойчивость к падению транспорта
  (логирование не рушится). → 97%.
- **`test_types.py` (+4).** `LLMExtraBody.as_dict`: пустой по умолчанию, флаг
  include_reasoning, reasoning-опции с exclude_none, дроп пустых опций. → 100%.
- **`test_security_context.py` (+2).** Все 7 полей биндятся; пустой вызов не
  биндит ничего. → 100%.

## Покрытые поведения / критпути

- **Слой действий гейтится строго по INJECTION** (`runtime_security`): на
  INJECTION — персист блока + редакция через чекпойнтер; SUSPICIOUS — лог-warning,
  проходит БЕЗ редакции; CLEAN — тихо проходит. Проверено для USER_INPUT,
  FINAL_OUTPUT (end-of-stream), mid-stream tail (skip_classifier), inspect_in_graph.
- **`VERDICT_TO_LEVEL` — отдельный observability-слой** (observer.finalize), не
  путается со слоем действий: уровень обсервации ≠ block/redact. Покрыто отдельно.
- **Classifier**: парсинг каждого вердикта, нормализация case/whitespace, ретрай-
  петля с подсчётом retries, деградация в CLEAN (`degraded=True`) на исчерпании
  ретраев и на исключении модели (через `garbage_/raising_classifier_model`).
- **Canary-token, detectors** (canary/fragment/paired/unicode/normalize), corpus
  (tool registry + fragment corpus), observer fail-safe, transport (очередь/
  overflow/drain/publisher_loop), processor (event_dict → SecurityEvent → транспорт),
  security context (contextvars round-trip), types (direction_of/VERDICT_TO_LEVEL/
  LLMExtraBody).
- Везде проверяется **реакция кода на вердикт**, не качество вердикта (eval).

## Тесты + результат

- `make test-scope P=backend/tests/security` → **140 passed** (было 108).
- `ruff check` + `ruff format --check` tests/security → чисто.
- `mypy tests/security` → Success, 13 files.

## Баги для Ф5

Нет. Прод-код не правился. Поведение покрывалось как есть; обходных правок под
тест не вносилось.

## Непокрытое и почему (осознанно)

- **`runtime_security` 291-307** (`_mark_blocked` через `ThreadViewRepository`):
  реальная запись в БД — относится к repository/integration-контуру (как и
  сказано в docstring тест-файла), не к unit-ветвлению. Конструирует
  `ThreadViewRepository(session)` инлайн — инъекции нет, фейк репозитория тут
  тестировал бы заглушку.
- **`observer` 165-214** (langfuse-enabled `observe()`): открытие top-level/
  nested обсерваций через контекст-менеджеры Langfuse SDK. Fail-safe-обёртка
  вокруг внешнего эффекта; тест требует мокать ленивый импорт `langfuse` —
  хрупко, тестирует wire внешней либы. Логика ветвления (top_level vs nested,
  фильтрация metadata) — кандидат на eval/integration, не unit.
- **`corpus` 22,27,29-37**: защитные ветки разбора формы `args_schema` (None /
  dict / pydantic model_fields) под разные версии LangChain. Контрить фейк-tool
  с нужной формой schema = тестировать деталь реализации, а не поведение.
- **`transport` 21** (`EventTransport.publish` NotImplementedError, абстрактная
  база), **120-125** (timeout-ветка `graceful_shutdown` — timing-зависима).
- **`classifier` 104->107**: ветка reasoning когда `additional_kwargs` не dict
  (труднодостижимо детерминированно, малоценно).
- **`fragment` 47,50-52**: остаток в детекторе fragment (88%).

## Блокеры

Нет. Замороженную инфру (`packages/testing`, общий conftest) не трогал.
