# Summary: feat-001 / трек T1 — Backend: контракт SSE v2, след работы агента

## TL;DR

Трек закрывает четыре фазы. **T1.1** подтвердила: reasoning доезжает до сохранённого в
чекпоинт `AIMessage` на реальном streaming-пути, без правок `graph.py`. **T1.2** ввела
транспортный каркас SSE v2: `stream_started` до setup, `HeartbeatPacer` (heartbeat 5 с +
отзывчивая отмена во время долгого tool-вызова), терминальный `cancelled {}`, generic
`security_block {}`, устранена утечка `_cancel_events`. **T1.3** переработала token-канал —
`TokenChunkMapper` (per-run) разбирает чанк на `reasoning_chunk` / `text_chunk` / ранние
`tool_call_started` + `tool_call_args`; guard-проверки остались только на `text_chunk`;
изолирован стрим суммаризатора от пользовательского канала. **T1.4** привела updates-канал
(`StreamEventMapper`, тоже сделан per-run) к контракту: `tool_start`/`tool_end` удалены;
`tool_result` — из `ToolMessage` (status/content/truncated); `artifact_created` — по атрибуту
`ToolMessage.artifact`, не по whitelist имён; `tool_call_cancelled` — при срезе
`guard_tool_call_args`, через bookkeeping «анонсировано token-каналом, не разрешилось».

`make check` зелёный на всех фазах. `make test`: стабильно **526 passed, 1 failed, 228
errors** с T1.2 — падения инфраструктурные (testcontainers/Docker) и один предсуществующий
внешний прайсинг-дрейф, ни одна фаза не добавила красного. Ручная проверка reasoning на живой
модели (T1.1) не выполнена — нет сети в среде агента.

## Реализовано в фазе T1.1

- `backend/tests/agent/test_reasoning_checkpoint.py` (новый) — регрессионный тест-проба
  `test_reasoning_survives_streaming_accumulation_to_checkpoint`. Строит реальный граф
  (`build_graph`/`compile_graph` через фикстуру `build_compiled_graph`) с фейковой моделью,
  стримящей `additional_kwargs["reasoning"]`-дельты по чанку, прогоняет
  `graph.astream({"messages": [HumanMessage(...)]}, config, stream_mode=["messages"],
  context=...)` до конца (тот же режим стрима, что использует `runner.py`, только без
  `"updates"` — он для этой пробы не нужен), затем читает
  `checkpointer.aget_tuple(config).checkpoint["channel_values"]["messages"]` — то же место,
  что читает `CheckpointHistory.raw_messages`. Ассерты: последний `AIMessage` несёт и
  `content`, и полностью собранный (конкатенированный из дельт) `additional_kwargs["reasoning"]`.
- `backend/tests/agent/conftest.py` — новый фейк `StreamingReasoningFakeChatModel` +
  фабрика `reasoning_streaming_fake`, по образцу уже существующего в этом же файле
  `StreamingToolCallFakeChatModel`/`streaming_tool_fake` (тот решает ту же проблему для
  `tool_call_chunks`: стоковый `GenericFakeChatModel` стримит только `content`, поэтому
  программируемое `additional_kwargs` без переопределения `_astream` теряется при
  реконструкции чанков). Новый фейк разбивает программируемый `reasoning`-текст на
  несколько чанков, каждый со своей дельтой в `additional_kwargs["reasoning"]` (реальные
  reasoning-провайдеры шлют дельты по чанку, не всю строку целиком) и отдаёт их **перед**
  чанками содержимого — воспроизводит порядок «сначала reasoning, потом ответ» у реальных
  провайдеров/`ReasoningChatOpenAI._convert_chunk_to_generation_chunk`.
- Никаких изменений `backend/app/agent/graph.py` — дособор не потребовался (см. TL;DR).

**Проверки:**
- `make check` — зелёный (ruff lint + format, mypy `backend/` + `services/siem-service/` +
  `tools/*`, import-linter 9/9 контрактов, arch-checker). Первый прогон mypy на новом тесте
  дал два замечания (лишний `# type: ignore[call-overload]`, скопированный по аналогии из
  `runner.py`, и нетипизированный `dict[str, Any]` вместо `RunnableConfig` для `config`,
  переданного в типизированный `checkpointer: InMemorySaver`) — оба устранены точечно, без
  подавлений.
- `make test` — 753 passed, 1 failed. Упавший тест —
  `backend/tests/agent/test_pricing_external.py::test_active_model_prices_within_drift_tolerance`
  (маркер `@pytest.mark.external`, живой прайсинг `z-ai/glm-5.2` с OpenRouter разошёлся с
  `pricing.yaml` на 12.9% при допуске 10%). Проверено на чистом коммите до правок этой фазы
  (`git stash` + прогон того же теста) — падает так же (12.6% дрейфа), не связано с T1.1.
  Новый тест и фейк из этой фазы зелёные; ни один из существующих 753 тестов не задет.

## Реализовано в фазе T1.2

- `backend/app/agent/heartbeat.py` (новый) — коллаборатор `HeartbeatPacer`. `pace(source,
  cancel_event)` оборачивает произвольный `AsyncGenerator[StreamEvent, None]`: на каждой
  итерации гонит `source.__anext__()` как фоновую задачу против таймера
  (`asyncio.wait({pending}, timeout=interval)`); если источник успел — ретранслирует его
  событие; если истёк таймаут — проверяет `cancel_event` (и при установленном отдаёт терминальный
  `cancelled {}` и завершается) либо отдаёт `heartbeat {}` и продолжает ждать тот же `pending`.
  Интервал — конструкторный параметр с бизнес-константой по умолчанию
  (`HEARTBEAT_INTERVAL_SECONDS = 5.0`), не env.
- `backend/app/agent/text_limits.py` (новый) — `truncate(text, limit=TRUNCATION_LIMIT)` →
  `(text, truncated)`, `TRUNCATION_LIMIT = 2000` (бизнес-константа). Общий для SSE и API,
  задел под T1.3/T1.4/T1.7 — в этой фазе не вызывается ни из одного места продакшн-кода
  (проверено `grep`), только определён.
- `backend/app/agent/runner.py` — `stream()` переработан вокруг новой структуры:
  - Всё прежнее тело метода (резолв модели/MCP/графа, guard USER_INPUT, цикл `graph.astream`,
    end-of-stream security-проверки) вынесено во вложенную функцию `_run_turn()`
    (`AsyncGenerator[StreamEvent, None]`), без изменения внутренней логики, кроме точек,
    перечисленных ниже.
  - `stream()` теперь: `yield stream_started {}` → запускает `_run_turn()` под
    `self._heartbeat_pacer.pace(...)` внутри `contextlib.aclosing(...)` → ретранслирует все
    события пейсера. Снаружи — один `try/finally`, чистящий `_cancel_events`/`_pending_cancels`
    безусловно при любом завершении генератора (успех, исключение, `GeneratorExit`).
  - Отмена по установленному `cancel_event` внутри цикла `graph.astream` теперь отдаёт
    `StreamEvent(type="cancelled", data={})` вместо прежнего `error {detail: "Request was
    cancelled."}` (последний путь через `normalize_error_message(CancelledError(), ...)`
    в `error_mapper.py` больше из `runner.py` не вызывается).
  - `security_block` во всех четырёх точках эмиссии (USER_INPUT, mid-stream, final-output,
    post-stream in-graph) отдаёт `data={}` — `reason` больше на провод не идёт (остаётся в
    Langfuse/SIEM через `span.finalize_blocked`/`record_mid_stream_hit`, не тронуты).
  - Лог `"agent completed"` получил четвёртый статус `"cancelled"` (был: `client_disconnected`
    / `error` / `ok`) — отличает пользовательскую отмену от настоящего обрыва клиента, для
    которого `except (asyncio.CancelledError, GeneratorExit)` теперь определяет
    `client_disconnected = not cancel_event.is_set()` вместо безусловного `True`.
- `backend/app/services/chat.py` — `had_error` переименован в `stream_ended_without_done`;
  условие расширено с `("error", "security_block")` до `("error", "security_block",
  "cancelled")` — все три остаются терминальными и взаимоисключающими с `done` (пропуск
  post-hoc резолва `message_id`/линковки артефактов и синтеза `done`).
- `backend/app/api/routes/messages.py` — **не тронут**. Сверка транспортного fallback
  `error {"Stream failed"}` с `configs/error_messages.yaml` подтверждает неточность №4 аудита:
  строка литеральная, ни один ключ файла (`generic`/`timeout`/`cancelled`/`auth`/`upstream`) её
  не содержит. План допускает оба варианта закрытия («правка либо в коде, либо фиксация факта
  при переписывании `streaming.md` в T1.9») — решение этой фазы: зафиксировать факт, правку
  отложить до T1.9 (см. «Решения и обоснования» ниже).
- Тесты — списком с обоснованием (правило A6: полноценный набор — за `test-author`, здесь —
  приведение существующих тестов к новому словарю событий, предусмотренное планом):
  - `backend/tests/agent/test_runner.py` — переименованы/переприведены под новый словарь:
    `test_precancelled_thread_emits_cancelled_error_and_no_text` →
    `..._cancelled_event_and_no_text` (ассертит `cancelled {}` вместо `error {detail}`);
    `test_client_disconnect_logs_client_disconnected_status` получил один лишний `anext` —
    теперь первое событие потока безусловно `stream_started`, второе — первый `text_chunk`;
    три теста на `security_block` (`mid_stream`/`final_output`/`in_graph_redaction`) больше не
    проверяют `block.data["reason"]`, только `block.data == {}`.
  - `backend/tests/chat/conftest.py` — вокабуляр `RUNNER_FORWARDED_TYPES` и билдеры событий
    приведены к контракту v2: добавлены `stream_started_event()`/`heartbeat_event()`/
    `cancelled_event()`, `security_block_event()` больше не принимает `reason`. Комментарий
    про drift `streaming.md` (`reason` vs `{checkpoint, detection_layer}`) снят — фаза T1.2
    закрыла его: на проводе теперь нет ни того, ни другого.
  - `backend/tests/chat/test_chat_service.py` — параметризованный тест терминалов
    (`test_send_message_terminal_failure_skips_done` → `..._terminal_event_skips_done`) получил
    третий кейс `cancelled_event()`; тест полноты словаря (`test_runner_emits_only_the_agreed_
    wire_vocabulary`) сверяет литералы уже по трём модулям (`runner`, `stream_events`,
    `heartbeat`); тест форвардинга получил `stream_started`/`heartbeat` в проверяемую
    последовательность.
  - `backend/tests/chat/test_message_stream.py` — `security_block_event()` без `reason`;
    ассерт на payload сузился до `{"type": "security_block"}` (раньше проверял `reason`).
  - `backend/tests/agent/conftest.py`, `backend/tests/agent/test_reasoning_checkpoint.py` — из
    фазы T1.1, этой фазой не тронуты (не в её файловом скоупе).

## Реализовано в фазе T1.3

- `backend/app/agent/stream_events.py` — новый класс `TokenChunkMapper` рядом с существующим
  `StreamEventMapper` (тот остаётся владельцем канала `updates`; новый — канала `messages`).
  `map_chunk(chunk: AIMessageChunk) -> list[StreamEvent]` разбирает один сырой чанк на три
  ветки: `additional_kwargs["reasoning"]` → `reasoning_chunk {content}`; строковый непустой
  `content` → `text_chunk {content}` (как раньше); каждый элемент `tool_call_chunks` →
  `_map_tool_call_chunk`, которая ведёт per-instance состояние сборки (`call_id` по `index` —
  на случай, если id есть только в первом фрагменте вызова; накопленные args по `call_id`;
  множества уже анонсированных `call_id` и уже отданных `args`) и эмитит `tool_call_started
  {call_id, tool}` один раз на первое появление `call_id` (имя уже известно в этот момент —
  входной факт плана №3) и `tool_call_args {call_id, args, truncated}` один раз, когда
  накопленная строка args успешно парсится `json.loads` (полный валидный JSON = аргументы
  дописаны, до исполнения), с усечением через `text_limits.truncate` — первый производственный
  вызов этого хелпера (в T1.2 он был заведён, но не вызывался).
- `backend/app/agent/runner.py`:
  - Конструктор получил `token_mapper_factory: Callable[[], TokenChunkMapper] | None` (по
    умолчанию — сам класс `TokenChunkMapper`); `_run_turn()` создаёт `token_mapper =
    self._token_mapper_factory()` один раз в начале каждого вызова `stream()` — то есть новый
    экземпляр на каждый ран, а не на конструктор раннера (шов для тестов + защита от смешивания
    состояния параллельных пользовательских стримов).
  - Ветка `mode == "messages"` переписана: фильтр сузился до `isinstance(msg_chunk,
    AIMessageChunk)` (раньше дополнительно требовал непустой строковый `content` — теперь это
    решает `TokenChunkMapper` для каждой из трёх веток отдельно); `last_message_id` обновляется
    на любом чанке с `id`, а не только на текстовом — раньше генерация без текстового чанка (в
    новых ветках это в принципе возможно: reasoning-only или tool_call-only чанк) оставляла
    `last_message_id` устаревшим для последующей нацеленной редакции
    (`RuntimeSecurityEnforcer._redact_final_output`, `id=last_message_id`); дальше — цикл по
    `token_mapper.map_chunk(msg_chunk)`, где guard-проверки (усечение хвоста, canary,
    `check_mid_stream`) выполняются **только** для событий `text_chunk` (как и раньше — вход в
    `full_response`/`chunks_processed` тоже только оттуда); блокировка выражена флагом
    `blocked` + `break`/`return` вместо прежнего прямого `return` — механически то же поведение
    (текст, вызвавший блок, не долетает до клиента), просто перенесённое во вложенный цикл.
- `backend/app/agent/graph.py` — `_reduce_context`'s `summarization_model.ainvoke(...)` теперь
  получает изолирующий `RunnableConfig` (`callbacks: []`, `tags=["context_summarization"]`,
  `run_name="context-summarization"`), по образцу `security/classifier.py:93-99`. Закрывает
  попутную находку №1 аудита: без явного `callbacks: []` вызов наследует callback-цепочку
  родительского `ainvoke`, и `stream_mode=["messages", ...]` увидел бы токены компакции как
  обычные чанки `text_chunk` пользовательского ответа.
- Тесты — списком с обоснованием (правило A6):
  - `backend/tests/chat/conftest.py` — `RUNNER_FORWARDED_TYPES` пополнен тремя новыми
    литералами (`reasoning_chunk`, `tool_call_started`, `tool_call_args`) — их порождает
    `TokenChunkMapper`, и AST-сканирующий страж словаря (`test_runner_emits_only_the_agreed_
    wire_vocabulary` в `test_chat_service.py`) иначе покраснел бы на новый emission site.
    Добавлены билдеры `reasoning_chunk_event()`/`tool_call_started_event()`/
    `tool_call_args_event()` тем же паттерном, что и существующие (`text_chunk_event` и т.д.).
  - `backend/tests/chat/test_chat_service.py` —
    `test_chat_service_forwards_each_runner_type_and_consumes_trace_id` (пример «по одному
    событию каждого форвардящегося типа») дополнен по одному экземпляру трёх новых типов;
    ожидаемая последовательность `forwarded` и финальная сверка множества с
    `RUNNER_FORWARDED_TYPES` обновлены соответственно. Это приведение существующего теста к
    новому словарю (предусмотрено планом), не новый тест-кейс.
  - Файлы, которые я **не** тронул, хотя план называл их в контексте фазы: `test_runner.py`
    (существующий `test_tool_call_emits_tool_start_and_tool_end_via_astream` не проверяет
    исчерпывающий список событий — новые `tool_call_started`/`tool_call_args` появляются в
    потоке рядом с `tool_start`/`tool_end`, не ломая имеющиеся ассерты) и
    `subagents/test_stream_isolation.py` (упомянут в верификации плана как «обновлённый», но его
    фикстуры не программируют `tool_call_chunks` — новые события там не возникают, а
    существующее поведение фильтра по `SUBAGENT_TAG` не менялось; прогнан и зелёный без единой
    правки — см. «Решения и обоснования»).

## Реализовано в фазе T1.4

- `backend/app/agent/stream_events.py` — `StreamEventMapper` переработан под контракт v2:
  - `tool_start`/`tool_end` удалены целиком (эмиссия старта вызова уже принадлежит
    token-каналу с T1.3 — updates-канал её больше не дублирует).
  - `tool_result {call_id, tool, status, content, truncated}` — из `ToolMessage` узла
    `tools`: `status` берётся прямо из `ToolMessage.status` (`"success"`/`"error"`, выставляет
    либо инструмент через `response_format="content_and_artifact"`, либо
    `ToolNode(handle_tool_errors=...)` на исключении — проверено по
    `langgraph/prebuilt/tool_node.py`, оба пути дают `status="error"`), `content` усечён общим
    хелпером `text_limits.truncate` (первый вызов этого хелпера из T1.2 в updates-канале).
  - `artifact_created` эмитится по `msg.artifact is not None` — захардкоженный whitelist
    `{"create_artifact", "generate_image"}` снят; событие следует за `tool_result` того же
    вызова, как и раньше.
  - `tool_call_cancelled {call_id}` — новый метод `note_call_announced(call_id)` плюс
    внутренний `_pending_call_ids: list[str]` (per-run bookkeeping, не dict/set — порядок
    объявления сохраняется для детерминированной эмиссии, если guard срежет несколько
    параллельных вызовов одного хода разом). `updates()` эмитит `tool_call_cancelled` для
    каждого ещё не разрешённого `call_id`, обнаружив в данных узла `agent` признак среза:
    `isinstance(msg, AIMessage) and not msg.tool_calls and
    msg.additional_kwargs.get("security_redacted")` — именно `AIMessage`, не `ToolMessage`
    (тот же флаг ставит `guard_tool_results` на `ToolMessage` при независимой
    TOOL_RESULT-редакции — сравнение типа сообщения обязательно, `original_detection_layer`
    в условие не входит вообще, как и предупреждал оркестратор). Разрешённые вызовы (получили
    `tool_result`) вычищаются из `_pending_call_ids` до какой-либо проверки на срез.
  - `StreamEventMapper` стал **per-run коллаборатором** (docstring класса объясняет почему):
    без bookkeeping в отдельном инстансе `tool_call_cancelled` физически не собрать — к
    моменту, когда редактированный `AIMessage` доезжает до `updates()`, `tool_calls` уже
    пусты (`guard_tool_call_args` их обнулил), и в payload узла `agent` не остаётся ни одного
    исходного `call_id`.
- `backend/app/agent/runner.py` — `event_mapper: StreamEventMapper | None` в конструкторе
  заменён на `event_mapper_factory: Callable[[], StreamEventMapper] | None` (default —
  `StreamEventMapper`), по прямой аналогии с `token_mapper_factory` из T1.3: `_run_turn()`
  создаёт `event_mapper = self._event_mapper_factory()` один раз в начале рана, рядом с
  `token_mapper`. В цикле по `token_mapper.map_chunk(...)`, на каждом событии типа
  `tool_call_started`, раннер вызывает `event_mapper.note_call_announced(call_id)` — это и
  есть связка «то же per-run состояние, что у T1.3», которую требовал план: раннер знает про
  оба канала одновременно и переносит факт анонса из token-канала в updates-канал.
- `backend/app/main.py` — `event_mapper=StreamEventMapper()` (единственный shared-инстанс на
  весь процесс) заменён на `event_mapper_factory=StreamEventMapper` — необходимое следствие
  переименования конструкторского параметра, но и самостоятельно важное исправление: до этой
  правки один и тот же `StreamEventMapper` обслуживал бы все одновременные пользовательские
  раны, и с добавлением per-run bookkeeping (`_pending_call_ids`) стал бы местом утечки
  состояния между параллельными стримами — тем самым нарушением «никакого
  module-level/shared состояния», которого T1.3 уже избежала для `TokenChunkMapper`.
- Тесты — списком с обоснованием (правило A6: приведение существующих тестов к новому
  словарю событий, не новые кейсы — полноценный набор пишет `test-author`):
  - `backend/tests/agent/test_stream_events.py` — переименованы/переприведены к новому
    словарю: `test_agent_tool_calls_emit_tool_start_events` →
    `test_agent_tool_calls_emit_nothing` (агент-узел с `tool_calls` теперь не эмитит ничего —
    старт уже был отдан token-каналу в T1.3); `test_tool_message_emits_tool_end_event` →
    `test_tool_message_emits_tool_result_event` (payload расширен под
    `status`/`content`/`truncated`); `test_create_artifact_emits_artifact_created_with_
    remapped_type` и `test_create_artifact_without_artifact_payload_only_emits_tool_end` →
    список типов событий обновлён (`tool_end` → `tool_result`), логика теста не изменилась.
    Не добавлены: отдельные кейсы на `status="error"`, на усечение `content`, на произвольное
    (не whitelist) имя инструмента с артефактом, на сам `tool_call_cancelled` — это новое
    покрытие, а не приведение существующего, значит вне scope фазы (первая черновая версия
    файла у меня их содержала; вычистил после сверки с правилом A6/планом).
  - `backend/tests/image_generation/test_stream_events_generate_image.py` — тот же паттерн:
    `tool_end` → `tool_result` в списках типов и в комментарии, тестовая логика не менялась.
  - `backend/tests/agent/test_runner.py` —
    `test_tool_call_emits_tool_start_and_tool_end_via_astream` →
    `test_tool_call_emits_started_args_and_result_via_astream`: тест уже проверял
    сквозной `astream`-путь реального графа, план явно требует «событий `tool_start`/`tool_end`
    в потоке больше нет» — с их удалением из мапперов исходный тест стал бы падать
    (`tool_start`/`tool_end` больше никогда не появляются), поэтому он не мог остаться
    нетронутым, хотя явно не назван в списке «Изменения» фазы. Ассерты переведены на
    `tool_call_started`/`tool_result` с уже известными по контракту payload'ами.
  - `backend/tests/subagents/test_stream_isolation.py` — по той же причине (реальный
    `astream`-путь через раннер, который план явно требует очистить от `tool_start`/`tool_end`):
    `test_tool_start_and_end_still_flow_while_tokens_are_filtered` →
    `test_tool_result_still_flows_while_tokens_are_filtered`, фикстура упрощена (убран
    начальный `updates` с `AIMessage.tool_calls` — он больше ничего не эмитит и не нужен
    тесту), ассерт `"tool_result" in types` вместо пары `tool_start`/`tool_end`. Модульный
    докстринг и докстринг `StreamingToolCallFakeChatModel` (`tests/agent/conftest.py`) поправлены
    той же правкой — упоминали устаревшие имена событий в прозе.

## Решения и обоснования

- **Вывод фазы: reasoning в чекпоинте есть, дособор не понадобился.** Планом было заложено
  условное ветвление («только если проверка отрицательная» — правка `graph.py`). Проверка
  оказалась положительной на первом прогоне: библиотечная механика (входные факты плана
  #1–#2 — `_should_stream` включает streaming-путь при наличии `StreamMessagesHandler`,
  `AIMessageChunk`-merge конкатенирует строковые `additional_kwargs`, `message_chunk_to_message`
  копирует `additional_kwargs` на итоговый `AIMessage`) воспроизвелась и на пути проекта:
  `agent_node`'s `bound_model.ainvoke(...)` (обычный `ainvoke`, не явный `astream`) реально
  идёт по streaming-коду, потому что родительский `graph.astream(..., stream_mode=["messages"])`
  инжектирует `StreamMessagesHandler`. Значимо для T1.7: часть `reasoning` в typed parts
  может читать `additional_kwargs["reasoning"]` финального `AIMessage` напрямую, без
  дополнительной логики сборки в `graph.py`.
- **Тест — `@pytest.mark.unit`, не `integration`.** По testing.md таблице «что и чем
  тестируем»: «Agent-node / граф / роутинг → unit → `GenericFakeChatModel`, `InMemorySaver`».
  Тест не поднимает Postgres (маркер `integration` в этом проекте означает «требует реальный
  Postgres через testcontainers» — см. `pyproject.toml` markers), только in-memory
  checkpointer — соответствует критерию unit, а не integration, несмотря на то что в
  соседнем `test_runner.py` структурно похожий тест (`test_tool_call_emits_tool_start_and_tool_end_via_astream`,
  тоже реальный `astream` + in-memory коллабораторы) промаркирован `integration`. Это
  расхождение — в существующем файле вне scope T1.1, не исправляется здесь (не моя фаза,
  не мой файл; вне scope-правила фазы — не «улучшать соседний код»).
- **Фейк размещён в `tests/agent/conftest.py`, а не локально в новом test-файле.** План
  описывает пробу как «остаётся в репозитории как регрессионный тест» и явно указывает
  на стиль `ReasoningChatOpenAI._convert_chunk_to_generation_chunk` — тот же уровень
  переиспользуемости, что и у `StreamingToolCallFakeChatModel`, уже живущего в conftest и
  используемого несколькими тестовыми файлами. T1.7 (typed parts из чекпоинтера, тесты пишет
  `test-author`) почти наверняка тоже понадобится модель, стримящая reasoning, — фейк
  заведён там, где его уже ожидают найти по аналогии с существующим паттерном файла.
  conventions/testing.md относит общие тест-утилиты к `packages/testing` только для
  *кросс-пакетных* дублей; внутрискоуповые фейки уже и так живут в локальном `conftest.py`
  пакета (прецедент — сам `StreamingToolCallFakeChatModel`), поэтому новый фейк туда же, не
  в отдельный пакет.
- **Дельты reasoning эмитятся отдельными чанками до чанков content, а не одним чанком
  вперемешку с текстом.** Реальные reasoning-модели (OpenRouter-совместимые провайдеры,
  для которых написан `ReasoningChatOpenAI`) стримят `delta.reasoning` и `delta.content` в
  разных SSE-чанках, причём reasoning обычно предшествует ответу. Раздельные чанки к тому же
  единственный способ реально проверить merge-конкатенацию `additional_kwargs["reasoning"]`
  между несколькими чанками (single-chunk reasoning доказал бы только перенос ключа, не
  накопление).
- **Ручная проверка на живой reasoning-модели не выполнена.** Инструкции фазы прямо
  предупреждают: bash-команды идут в sandbox с `--unshare-net`, `make dev` и живая
  reasoning-модель требуют сети наружу и БД, которых нет в среде агента. Не имитировалась и
  не выдавалась библиотечная/тестовая проверка за неё — честно отмечена как невыполненная
  автоматически. Это ожидаемый исход фазы, эскалируется оркестратором как ручной кейс
  архитектору (см. финальный отчёт).

- **`HeartbeatPacer` — отдельный коллаборатор, не метод `runner.py`.** Прямое следствие
  conventions/agent.md § Agent Runtime («новая сквозная забота в runtime → отдельный
  коллаборатор за портом, а не ещё один метод в runner») и явного указания плана: heartbeat —
  забота, ортогональная и к маппингу событий (`StreamEventMapper`), и к оркестрации рана
  (`LangGraphAgentRunner`), при этом сама по себе она ничего не знает о графе, guard'ах или
  Langfuse — только гонит произвольный `AsyncGenerator[StreamEvent, None]` против таймера.
  Инжектируется через конструктор (`heartbeat_pacer: HeartbeatPacer | None = None`) по тому же
  паттерну, что и остальные коллабораторы раннера — тестируем и подменяем независимо.
- **Устройство `pace()`: одна фоновая задача на `__anext__()`, один таймер на heartbeat и
  cancel.** `asyncio.wait({pending}, timeout=interval)` — единственный примитив, который
  одновременно (а) не блокирует таймер, пока источник ничего не отдаёт (в отличие от
  `asyncio.wait_for` на каждый `__anext__` — тот бы просто исключением рвал ожидание вместо
  того чтобы дать шанс отдать `heartbeat` и продолжить ждать тот же вызов), и (б) не создаёт
  новую задачу на источник при каждом холостом тике — `pending` живёт между итерациями `while`,
  пересоздаётся только когда реально потребляется. Это и даёт «heartbeat не крадёт события
  источника»: тот же `pending`, что не успел за 5 с, доживает до следующего тика без потери
  результата.
  Проверено smoke-скриптом (см. ниже): активный источник (события чаще интервала) не порождает
  ни одного `heartbeat`; молчащий источник даёт `heartbeat` на каждом полном интервале.
- **Очистка `_cancel_events`/`_pending_cancels` вынесена на уровень `stream()`, а не оставлена
  внутри `_run_turn()`.** До фазы `finally` с этой очисткой был прикреплён к `try/except` вокруг
  `graph.astream` — то есть выполнялся только если исполнение вообще дошло до этой точки. Два
  пути обходили его стороной: ранний `return` при заблокированном USER_INPUT (случается до
  создания `try`) и исключение в setup-фазе (резолв модели/MCP/сборка графа — тоже до `try`,
  и структурно ещё выше по коду, вне `with self._tracer.run(...)`). Перенос очистки в `finally`
  внешнего `try` в `stream()`, оборачивающего весь ран целиком (включая `yield stream_started`
  и потребление пейсера), закрывает оба пути: `finally` в Python выполняется независимо от того,
  как блок завершился — нормальным `return` из `_run_turn()` (StopAsyncIteration всплывает
  через `pace()` как штатное завершение) или необработанным исключением из setup-фазы (оно
  всплывает через `pending.result()` в `pace()`, `pace()` его не глотает, оно продолжает
  распространяться через `contextlib.aclosing` и `try` в `stream()` до `finally`, а затем — до
  вызывающего `ChatService`/`messages.py`, чей собственный `try/except Exception` вокруг
  итерации потока превращает его в транспортный `error {"Stream failed"}` — этот путь не
  менялся). Прослежено по коду, а не только продекларировано: для обоих путей действительно
  нет промежуточного `except`, который бы поглотил исключение до внешнего `finally`.
- **Отзывчивая отмена — два независимых чекпоинта, не один.** Проверка `cancel_event.is_set()`
  внутри цикла `graph.astream` (как и раньше) ловит отмену между итерациями графа — быстрее
  heartbeat-интервала, но бесполезна, пока граф застрял внутри одной итерации (долгий
  tool-вызов, `run_subagent`). Проверка на таймере `HeartbeatPacer` не зависит от того, отдал
  ли граф что-то за это время — она **гонит `_run_turn().__anext__()` как отдельную задачу и
  проверяет `cancel_event` по истечении интервала независимо от результата этой задачи**, поэтому
  ловит отмену и во время долгого исполнения инструмента (design-brief прямо требует этого;
  event-map.md попутная находка №3). Оба чекпоинта пишут разные типы событий на проводе только
  формально одинаковые (`cancelled {}`), но триггерятся из разных мест: цикл `astream` — сам
  внутри `_run_turn()`, пейсер — снаружи, через `GeneratorExit`/`CancelledError` в
  `_run_turn()` при отмене фоновой задачи (см. ниже про teardown) либо напрямую выходом из
  `pace()`, если `_run_turn()` ничего не успел отдать вовсе.
- **`security_block` — generic-payload, `reason` не удалён из кода, а перестал попадать на
  провод.** `RuntimeSecurityEnforcer.block_reason`, `span.finalize_blocked`,
  `span.record_mid_stream_hit` не тронуты — `reason`/`detection_layer`/`checkpoint` по-прежнему
  считаются и уходят в Langfuse/SIEM, просто больше не копируются в `StreamEvent.data`. Прямое
  следствие design-брифа (детали блокировки — потенциальная утечка сигнала атакующему, остаются
  только во внутренней телеметрии).
- **Транспортный fallback `error {"Stream failed"}` (`messages.py:43`) — оставлен как есть,
  правка отложена до T1.9.** План даёт этой фазе выбор между правкой в коде и фиксацией факта
  при переписывании `streaming.md`; `messages.py` — файловый скоуп T1 (входит в партицию трека),
  но конкретно эта правка логически привязана к документации контракта ошибок, которую T1.9 и
  переписывает, поэтому естественнее закрыть её одним диффом вместе с `streaming.md`, а не
  редактировать `messages.py` дважды за трек. Верифицировано (не только продекларировано): в
  `configs/error_messages.yaml` нет ключа/значения `"Stream failed"` — неточность №4 аудита
  подтверждена, не исправлена, эскалации не требует (в рамках полномочий плана).
  Побочное наблюдение, не требующее действия в этой фазе: `error_mapper.normalize_error_message`
  по-прежнему маппит `asyncio.CancelledError` → `error_messages.yaml: cancelled` (строка
  «Request was cancelled.»), но `runner.py` больше не вызывает эту функцию с `CancelledError` —
  единственный вызывавший её путь заменён на `cancelled {}`. Ветка не удалена (не в файловом
  скоупе `error_mapper.py` для этой фазы, и снятие может задеть другие вызовы
  `normalize_error_message`, если они появятся позже) — фиксирую как наблюдение для code review.
- **Проверка teardown `pace()`'s `finally` — эмпирический результат: утечки нет ни на одном из
  трёх путей.** Прогнан разовый smoke-скрипт (`heartbeat_smoke.py`, не коммитится — инструмент
  проверки, полноценные тесты пишет `test-author`) с источником-генератором, чей `finally`
  печатает маркер, по всем трём путям выхода:
  - **отмена по таймеру** (`cancel_event` установлен между тиками пейсера, источник ни разу не
    успел отдать событие) — маркер источника печатается;
  - **закрытие потребителем** (`agen.aclose()` на пейсере, эквивалент `GeneratorExit` от
    `ChatService`/`contextlib.aclosing` в `stream()`) — маркер печатается;
  - **исключение из источника** (источник бросает после первого `yield`) — маркер печатается.

  Настораживающая на чтении кода асимметрия (`pending is not None and not pending.done()` →
  `pending.cancel()` + `await pending`, **без** `agen.aclose()`; `aclose()` вызывается только в
  `else`) на практике не течёт — причина в том, *как* `asyncio.Task.cancel()` работает поверх
  `agen.__anext__()`. `__anext__()` — обычная корутина, которая на момент отмены приостановлена
  ровно там же, где приостановлен сам генератор источника (внутри его тела, на каком-то
  `await`). Отмена задачи, оборачивающей эту корутину, инжектирует `CancelledError` в точку
  приостановки — то есть непосредственно в тело генератора источника, а не в обёртку `__anext__`
  снаружи. Разворачивание этого исключения проходит через `finally`-блоки генератора точно так
  же, как и при явном `aclose()` (который под капотом делает то же самое — бросает
  `GeneratorExit`/`CancelledError` в точку приостановки). После разворота генератор источника
  естественным образом переходит в закрытое состояние сам, поэтому последующий `aclose()` (если
  бы он был вызван) был бы безопасным no-op — а поскольку код в этой ветке `aclose()` и не
  вызывает, лишнего вызова просто не происходит. Итог: асимметрия в коде реальна, но не
  является дефектом — оба пути (`pending.cancel()` и `agen.aclose()`) приводят к одному и тому
  же результату для закрытия источника разными механическими путями, и это фактически
  подтверждённое, а не предполагаемое поведение. Открытый вопрос, вне scope этой фазы: если бы
  источник сам подавлял `CancelledError` в своём `finally` (не давал ему распространиться) —
  такой источник не закрылся бы корректно ни в одной из веток; это было бы багом источника
  (нарушение протокола async-генераторов), а не `HeartbeatPacer`.

- **`TokenChunkMapper` — расширение `stream_events.py`, не отдельный модуль.** План допускал
  оба варианта («расширение `stream_events.py` или соседний модуль — по размеру»); файл был 54
  строки (порог size-чека — 500), и `TokenChunkMapper` там семантически на месте: тот же
  «graph payload → `StreamEvent`» контракт, только для другого `stream_mode`. Отдельный модуль
  потребовал бы завести ему отдельный импорт в AST-сканирующем страже словаря
  (`test_chat_service.py`: `runner_module`/`stream_events_module`/`heartbeat_module`) — лишнее
  движение без выгоды, раз существующий модуль уже сканируется.
- **Полнота JSON как признак «args дособраны» — `json.loads` на накопленной строке, не длина
  или наличие закрывающей скобки.** Провайдерский контракт (план, входной факт №3) гарантирует
  единственный валидный JSON-объект на вызов, собираемый по фрагментам `args`; попытка парсинга
  — единственный способ отличить «ещё пишется» от «дописано» без знания глубины вложенности
  объекта. Ложноположительное срабатывание теоретически возможно (фрагмент вида `{}` или число
  сам по себе валиден как JSON), но не как эффективная args-строка инструмента — по контракту
  args всегда JSON-объект, дособираемый монотонно слева направо, поэтому первый момент
  успешного парсинга и есть момент завершения. `_args_emitted_call_ids` подстраховывает от
  повторной эмиссии, если что-то придёт после уже-валидного состояния.
- **`_call_id_by_index` нужен, а не избыточен**, хотя входной факт плана №3 говорит «id известен
  с первого чанка»: гарантия относится к id **вызова**, а не к тому, что каждый физический
  ChatCompletion-чанк дублирует его — провайдеры (и наш `StreamingToolCallFakeChatModel`)
  переносят `id`/`name` только на первый фрагмент серии, дальнейшие фрагменты той же серии несут
  только `index` и очередной кусок `args`. Без карты по `index` эти последующие фрагменты
  оказались бы неатрибутируемыми (`resolved_call_id is None` → тихо отбрасываются).
- **`last_message_id` теперь обновляется на любом `AIMessageChunk` с `id`, не только на
  чанке с непустым текстом.** Раньше единственная точка обновления была внутри ветки, которая
  проверяла `content` — с добавлением reasoning/tool-call веток генерация без единого текстового
  чанка (например, ход, целиком состоящий из reasoning + вызова инструмента) оставляла
  `last_message_id` от предыдущего хода. Поскольку `id` стабилен для всех чанков одной
  генерации (объединяются в один `AIMessage` в чекпоинте), обновление на любом чанке — не новая
  семантика, а расширение существующей до полноты, которую раньше не требовалось покрывать,
  пока единственной веткой была текстовая. Ни один тест не был завязан на узкое поведение
  (проверено `grep` по `last_message_id` в `tests/`).
- **`test_stream_isolation.py` не тронут, хотя план называет его «обновлённым» в верификации
  T1.3.** Прочитал файл целиком перед принятием решения: обе его фикстуры (`_chunk` в
  `test_subagent_tagged_tokens_are_dropped_from_the_chat`,
  `test_tool_start_and_end_still_flow_while_tokens_are_filtered`) конструируют
  `AIMessageChunk(content=..., id=...)` без `tool_call_chunks` и без `additional_kwargs`, то
  есть маршрутизация через `TokenChunkMapper` для них не меняется вообще (одна ветка —
  `text_chunk`, как и раньше `map_chunk` эквивалентен старому инлайн-фильтру). План, видимо,
  предполагал, что рефакторинг фильтра тронет этот файл механически; по факту скоуп изоляции
  (тег `SUBAGENT_TAG`, фильтрация до входа в `token_mapper.map_chunk`) остался в `runner.py`
  нетронутым, а сам файл — валиден без правок. Прогнан явно, зелёный (см. отчёт фазы).
- **Мид-стрим security-block переписан через флаг `blocked` вместо прямого `return` внутри
  веток.** Раньше единственная проверяемая ветка (`text_chunk`) была самым внешним `if` в теле
  цикла `astream`, и `return` из неё выходил прямо из генератора. Теперь события чанка проходят
  через второй, вложенный цикл (`for token_event in token_mapper.map_chunk(...)`), а
  Python-генератор не может `return` из вложенного цикла и одновременно продолжить внешний —
  нужен явный сигнал наружу. Флаг + `break` + проверка после цикла — минимальная замена,
  сохраняющая точную семантику «текст, вызвавший блок, не долетает до клиента, `security_block`
  идёт вместо него» (тест `test_mid_stream_injection_emits_security_block_and_no_text` проходит
  без изменений).

- **`_pending_call_ids` — `list[str]`, не `set[str]`.** CPython не гарантирует порядок
  итерации по множеству строк; при срезе guard'ом хода с несколькими параллельными
  tool_calls (несколько `call_id` анонсированы, ни один не разрешён) порядок эмиссии
  `tool_call_cancelled` должен быть детерминированным для тестов и предсказуемым для фронта
  (лента активности рендерит действия в порядке появления). `list` с проверкой `not in` перед
  `append`/`remove` даёт тот же O(1)-по-факту результат при реалистичном числе одновременных
  вызовов (единицы) и сохраняет порядок объявления.
- **Признание среза — только `isinstance(msg, AIMessage)`, без явного `not isinstance(msg,
  ToolMessage)`.** Проверено по факту (`ToolMessage.__mro__`): `ToolMessage` не наследует
  `AIMessage` в установленной версии `langchain_core`, поэтому `isinstance(msg, AIMessage)`
  уже исключает `ToolMessage`-сообщения с тем же `security_redacted`-флагом (их ставит
  `guard_tool_results` на независимой TOOL_RESULT-редакции) — второй explicit-check добавил
  бы код без изменения поведения. Дополнительно закрыто регрессионным сценарием на этапе
  черновика теста (redacted `ToolMessage` в данных узла `agent` не даёт `tool_call_cancelled`)
  — проверено вручную перед вычисткой черновых тестовых кейсов по правилу A6, в
  зафиксированном виде тест не остался (см. «Реализовано в фазе T1.4»), но инвариант держит
  сама структура кода (тип `AIMessage` в `isinstance`), а не тест.
- **Разрешённый вызов вычищается из `_pending_call_ids` безусловно, до какой-либо проверки на
  срез в той же `updates()`.** В рамках одного вызова `data["tools"]`/`data["agent"]` не
  встречаются одновременно (узлы LangGraph отдают апдейт по одному на шаг), поэтому порядок
  «сначала resolve, потом cut» внутри одного вызова `updates()` не наблюдаем на практике; тем
  не менее ветка `"tools" in data` обрабатывается второй (после `"agent" in data`) намеренно —
  если бы оба ключа когда-либо оказались в одном payload'е, разрешённый в этом же вызове
  `call_id` не должен попасть в список отменённых (он уже получил `tool_result`, у него другой
  жизненный цикл). Порядок веток закрывает этот пограничный случай без дополнительного кода.
- **`StreamEventMapper.updates()` не проверяет двойную обработку `ToolMessage`, всплывающего
  повторно под узлом `agent`.** `guard_tool_results` (существующий код, не в scope этой фазы)
  возвращает обновлённый `ToolMessage` с `security_redacted=True` в `result_prefix`
  `agent_node`, то есть та же по `id` `ToolMessage` может второй раз появиться в апдейте узла
  `agent` — с уже отредактированным содержимым. Цикл по `data["agent"]["messages"]` фильтрует
  по `isinstance(msg, AIMessage)`, так что это повторное появление `ToolMessage` там просто
  игнорируется — не порождает второй `tool_result` с перезаписанным содержимым. Итог: живой
  стрим уже показал исходный (нередактированный) результат тула до того, как `agent_node`
  успел его отредактировать — тот же тайминговый зазор, что существовал в TOOL_RESULT guard'е
  до этой фазы (не новая проблема T1.4, не входит в её scope: «изменение guard-политик» —
  явная scope boundary брифа).

## Инфраструктурная находка фазы T1.2 (эскалация архитектору, не блокирует код)

`make test` в среде этой сессии не смог полностью отработать: 527 тестов, не требующих
Postgres, зелёные (весь новый/изменённый юнит-скоуп T1.1/T1.2 — `test_runner.py`,
`test_chat_service.py`, `test_reasoning_checkpoint.py`), но все ~228 тестов на реальном
Postgres (testcontainers), включая `chat/test_message_stream.py` из скоупа этой фазы, падают на
`ERROR at setup` с `sqlalchemy.exc.OperationalError: ... server closed the connection
unexpectedly`. Диагностика (не попытка починить — по конвенции параллельной разработки
инфраструктурные конфликты между агентами разруливает архитектор):

- Воспроизведено трижды подряд (полный `make test`, дважды; изолированный
  `make test-scope P=backend/tests/chat/test_message_stream.py`, дважды) — одинаковая картина,
  не флаки в духе «иногда проходит».
- `docker events`, снятый вокруг изолированного прогона, показывает: testcontainers создаёт
  свежий `postgres:16-alpine` (session-id одного Ryuk-контейнера), тот стартует и почти сразу
  (~7 с) получает `container kill ... signal=9` → `exitCode=137`. В тот же момент в потоке
  событий виден **другой**, посторонний `testcontainers-ryuk` контейнер (другой session-id),
  завершающийся по своему штатному 60-секундному таймауту простоя (`execDuration=60`) — то есть
  в среде параллельно существовал осиротевший Ryuk от какой-то более ранней (не этой) тестовой
  сессии.
  Похоже на межагентную конкуренцию за общий Docker-демон в параллельных worktree
  (`docker ps -a` в моменте показывал активные `t2-db-hostnet`/`t2-redis-hostnet` — контейнеры
  другого воркера) — не пытался её разруливать (не убивал чужие контейнеры, не чистил
  Ryuk/testcontainers-ресурсы), только диагностировал.
- Все 228 упавших тестов относятся к совершенно не связанным с этой фазой модулям
  (`projects/*`, `sphere/*`, `personalization/*`, `skill_context/*`, `subagents/*`, а также
  `chat/test_chat_routes.py`/`test_feedback.py`/`test_trace_store_redis.py`) — падение не
  специфично для файлов T1.2, оно системное для любого теста, которому нужен
  Postgres-фикстур. `make check` зелёный на неизменной кодовой базе.
- Из скоупа этой фазы не верифицирован интеграционный `chat/test_message_stream.py` (9 тестов).
  Ревью diff'а этого файла — только переприведение `security_block_event()`/данных под generic
  payload, изменений логики нет; риск того, что тест ловит реальную регрессию, а не инфру,
  низкий, но не нулевой — стоит перепрогнать при появлении стабильной БД.

## Follow-ups

- Перепрогнать `chat/test_message_stream.py` (и весь DB-интеграционный слой) в среде со
  стабильным Postgres-testcontainers — не удалось верифицировать в этой сессии (см.
  «Инфраструктурная находка фазы T1.2»).

## SOFA-посты (id / применил / результат)
