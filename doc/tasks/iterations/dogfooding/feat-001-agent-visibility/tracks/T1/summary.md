# Summary: feat-001 / трек T1 — Backend: контракт SSE v2, след работы агента

## TL;DR

Трек закрывает девять фаз контракта SSE v2 и следа работы агента. **T1.1** подтвердила
reasoning в чекпоинте на streaming-пути. **T1.2** ввела каркас v2 (`stream_started`,
`HeartbeatPacer`, `cancelled {}`, generic `security_block {}`). **T1.3** переработала
token-канал (`reasoning_chunk`/`text_chunk`/ранние `tool_call_started`+`tool_call_args`) и
изолировала суммаризатор. **T1.4** — updates-канал: `tool_result`, `artifact_created` по
атрибуту, `tool_call_cancelled`. **T1.5** включила custom-канал `agent_event {kind, payload}`
для `sphere_write`/`memory_write`/`skill_context_write`/`compaction`. **T1.6** — вложенность
субагента: lifecycle-события его тулов с `parent_call_id`. **T1.7** перевела
`CheckpointHistory.history()` на группировку по ходам в typed `parts`, `MessageOut.parts` — в
API-схеме. **T1.8** выложила фикстур имён инструментов (`agent-tool-names.json`) из
`app.agent.tools.registry` — контракт для реестра подписей T2. **T1.9** переписала
`streaming.md` целиком под контракт v2 (закрыла четыре неточности аудита) и завела чек-лист
«добавляешь инструмент агенту» в `conventions/agent.md`, поправив попутный дрейф в
`agent-runtime.md`.

Поверх фаз пришла правка контракта истории: `ToolCallPart.truncated` расщеплён на
`args_truncated` и `result_truncated` — аргументы и результат усекаются независимо, и один
флаг на двоих врал потребителю (подробности в § «Решения и обоснования»).

По блокерам code-ревью проверка `TOOL_RESULT` переехала из узла модели в узел `tools` обоих
графов (`execute_tools_guarded`): выход этого узла читают и провод, и чекпоинтер, поэтому
непроверенный результат инструмента больше не доезжает до пользователя — ни в основном графе,
ни у субагента, где отчёт о результате перешёл с прокси инструмента на узел. Триггер auto-title
перевёрнут с denylist пролога на позитивный `_TITLE_GUARD_CLEARED_TYPES`. Оба решения выходят
за design-brief и развёрнуты в § «Решения и обоснования».

`make check` зелёный на всех фазах. `make test` — **922 passed / 1 failed**
(`test_pricing_external.py`, внешний дрейф цен). В сессии фазы T1.2 окружение не давало поднять
Postgres-контейнеры (527 passed / 228 errors) — инфраструктурная находка ниже, к коду отношения
не имеет.

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
  module-level/shared состояния», которого T1.3 уже избежала для `TokenChunkMapper`. **Это
  меняет публичную сигнатуру конструктора `LangGraphAgentRunner`**
  (`event_mapper: StreamEventMapper | None` → `event_mapper_factory: Callable[[],
  StreamEventMapper] | None`, тот же переход, что T1.3 уже сделала для `token_mapper_factory`)
  — предмет отдельного внимания на code review: единственный продакшн-вызывающий —
  `main.py` (правка внесена в этом же диффе), тестовые конструкторы раннера (`test_runner.py`,
  `test_stream_isolation.py`) параметр вообще не передавали (полагались на дефолт), поэтому
  их не потребовалось трогать под переименование.
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
    докстринг поправлен той же правкой — упоминал устаревшие имена событий в прозе.
  - `backend/tests/agent/conftest.py` — только докстринг `StreamingToolCallFakeChatModel`
    поправлен (упоминал «letting runner tests exercise `tool_start`/`tool_end`» — заменено на
    актуальные `tool_call_started`/`tool_call_args`/`tool_result`); сам фейк (`_astream`,
    сборка `tool_call_chunks`) не менялся — он и раньше отдавал корректные chunk'и, которые
    `TokenChunkMapper` (T1.3) уже умеет собирать.
  - `backend/tests/chat/conftest.py` — вокабуляр `RUNNER_FORWARDED_TYPES` пополнен
    `tool_call_cancelled`/`tool_result` взамен `tool_start`/`tool_end`; добавлены билдеры
    `tool_call_cancelled_event()`/`tool_result_event()` тем же паттерном, что и существующие
    (`tool_call_started_event()` и др.) — без них AST-страж словаря в `test_chat_service.py`
    не смог бы запрограммировать новые типы в тестах, а комментарий-таблица payload'ов над
    `RUNNER_FORWARDED_TYPES` дополнен строками по обоим новым типам.
  - `backend/tests/chat/test_chat_service.py` — `test_runner_emits_only_the_agreed_wire_
    vocabulary` и `test_chat_service_forwards_each_runner_type_and_consumes_trace_id`
    (сквозная сверка словаря + «по одному событию каждого форвардящегося типа») переприведены:
    инлайновые `StreamEvent(type="tool_start", ...)`/`StreamEvent(type="tool_end", ...)`
    заменены на `tool_call_cancelled_event("c2")`/`tool_result_event("c1", "search",
    content="ok")`, ожидаемая последовательность `forwarded` обновлена соответственно. Это
    приведение существующих тестов к новому словарю (тот же тест, тот же охват сценариев),
    не новый тест-кейс.

## Реализовано в фазе T1.5

- `backend/app/agent/agent_events.py` (новый) — хелпер `emit_agent_event(kind, payload)` и
  общий реестр `DOMAIN_AGENT_EVENT_KINDS = {"sphere_write", "memory_write",
  "skill_context_write", "compaction"}`. Резолвит writer в порядке приоритета: (1) явный
  writer из контекстной переменной `SUBAGENT_STREAM_WRITER` (пока никем не выставляется — это
  задел под T1.6: обёртка исполнения инструментов субагента будет делать `.set()`/
  `.reset(token)` вокруг вызова каждого инструмента; до T1.6 переменная всегда `None`, и
  хелпер безусловно проходит к пункту 2), (2) `get_stream_writer()`, (3) no-op-функция при
  `KeyError`/`RuntimeError` (вне графового рантайма). Строковые значения payload проходят
  `text_limits.truncate` перед уходом на wire.
- `backend/app/agent/runner.py` — `stream_mode` расширен до `["messages", "updates",
  "custom"]`; новая ветка `elif mode == "custom"`: конверт `{"type": ..., "payload"?: ...,
  "data"?: ..., "parent_call_id"?: ...}` от writer'а — если `type` есть в
  `DOMAIN_AGENT_EVENT_KINDS` (импортирован из `agent_events.py`, не продублирован), раннер
  оборачивает в `StreamEvent(type="agent_event", data={"kind", "payload", "parent_call_id"?})`;
  для любого другого известного (не `None`) `type` — пробрасывает как есть
  (`StreamEvent(type=custom_type, data=data.get("data", {}))`), не оборачивая, — это ветка,
  которой в T1.6 воспользуется субагентная обёртка для `tool_call_started`/`tool_call_args`/
  `tool_result` с `parent_call_id`, на проводе неотличимых от событий основного агента.
- `backend/app/agent/tools/knowledge_sphere.py` — `create_section`/`update_section`/
  `delete_section` эмитят `sphere_write {"section_id": section_id}` после
  `store.aput`/`store.adelete`; `get_section` (read-only) не эмитит.
- `backend/app/agent/tools/user_memory.py` — `save_user_memory`/`delete_user_memory` эмитят
  `memory_write {"key": key}`.
- `backend/app/agent/tools/skill_context.py` — `save_skill_context`/`delete_skill_context`
  эмитят `skill_context_write {"skill_name": skill_name, "key": key}`.
- `backend/app/agent/graph.py` — `_reduce_context` эмитит `compaction {}` сразу после сборки
  `ops_prefix` на успешном пути сжатия (не в `except`-ветке отказа суммаризации — там
  компакции фактически не произошло).
- Ручная сквозная проверка (не коммитится, аналог `heartbeat_smoke.py` из T1.2): временный
  pytest-тест гонял `LangGraphAgentRunner.stream()` через реальный `astream` с фейковой
  моделью, вызывающей `create_section`, — подтвердил, что `agent_event {"kind":
  "sphere_write", "payload": {"section_id": "s1"}}` действительно доезжает на wire между
  `tool_call_args` и `tool_result`, в правильном порядке; удалён после проверки.
- Тесты — списком с обоснованием (правило A6: приведение существующего словаря, не новые
  кейсы — их пишет `test-author`):
  - `backend/tests/chat/conftest.py` — `RUNNER_FORWARDED_TYPES` пополнен `agent_event`
    (иначе AST-страж словаря в `test_chat_service.py` покраснел бы на новый emission site в
    `runner.py`); добавлен билдер `agent_event_event(kind, payload, *, parent_call_id=None)`
    тем же паттерном, что и остальные (`tool_result_event()` и др.); комментарий-таблица
    payload'ов над `RUNNER_FORWARDED_TYPES` дополнен строкой по новому типу.
  - `backend/tests/chat/test_chat_service.py` — `test_runner_emits_only_the_agreed_wire_
    vocabulary` (сверка множества литералов) и `test_chat_service_forwards_each_runner_
    type_and_consumes_trace_id` («по одному событию каждого форвардящегося типа») дополнены
    одним `agent_event_event("sphere_write", {"section_id": "s1"})` каждый — без этого первый
    тест упал бы на новом emission site `StreamEvent(type="agent_event", ...)` в `runner.py`
    (сканируется по AST независимо от того, вызывается ли он в реальном ране), второй бы не
    покрывал новый forwarded-тип. Тот же тест, тот же охват сценариев — не новый кейс.
  - Файлы, которые я **не** тронул, хотя мог ожидать: unit-тесты инструментов
    (`tests/personalization/test_user_memory_tools.py`,
    `tests/skill_context/test_skill_context_tools.py`,
    `tests/sphere/test_knowledge_sphere_tools.py`) вызывают tools через `tool.ainvoke(...)`
    напрямую — это ровно путь, на котором `emit_agent_event` резолвится в no-op
    (`KeyError` от `get_stream_writer()`), поэтому все 39 тестов остались зелёными без единой
    правки; это и есть проверка «no-op вне графа», которую план требует от этой фазы, а не
    новый тест-кейс, который следовало бы писать.

## Реализовано в фазе T1.6

- `backend/app/agent/agent_events.py` — новая контекстная переменная `SUBAGENT_PARENT_CALL_ID:
  ContextVar[str | None]`, тот же lifetime и тот же `.set()`/`.reset(token)`-паттерн, что у
  `SUBAGENT_STREAM_WRITER` (T1.5). `emit_agent_event` читает её после сборки
  `truncated_payload` и, если значение не `None`, добавляет `"parent_call_id"` в
  верхний уровень эмитируемого словаря — та самая точка, которую план называл «хелпер из T1.5
  подхватывает parent_call_id»: домен-тулы (`sphere_write`/`memory_write`/
  `skill_context_write`) сами не знают, вызваны они из основного графа или из-под субагента,
  поэтому привязка к `parent_call_id` не может быть параметром вызова — только контекстом.
- `backend/app/agent/subagents/runner.py` — новый класс `_LifecycleEmittingTool(BaseTool)` и
  фабрика `_wrap_tools_for_lifecycle_events(tools, stream_writer, parent_call_id)`.
  `_LifecycleEmittingTool` — тонкий прокси: `name`/`description`/`args_schema` скопированы у
  оборачиваемого тула (чтобы `bind_tools`/`ToolNode`-lookup по имени видели тот же тул, что
  задан в спеке), а исполнение целиком делегировано `wrapped_tool.ainvoke(...)` — класс не
  трогает `_run`/`_arun`, поэтому `response_format`/артефакты/что угодно ещё у реального тула
  продолжает работать без изменений. Переопределённый `ainvoke`:
  1. эмитит `tool_call_started {call_id, tool, parent_call_id}` и следом сразу
     `tool_call_args {call_id, args, truncated, parent_call_id}` — у субагента, в отличие от
     основного агента, `args` приходят от `ToolNode` уже полностью распарсенным словарём (не
     фрагментами `tool_call_chunks`), поэтому оба события уходят одно за другим, без
     промежуточного накопления;
  2. вокруг `await wrapped_tool.ainvoke(...)` выставляет `SUBAGENT_STREAM_WRITER`/
     `SUBAGENT_PARENT_CALL_ID` (`.set()` → `.reset(token)` в `finally`) — это и есть мост к
     вложенному `emit_agent_event` домен-тула, если он есть внутри;
  3. эмитит `tool_result {call_id, tool, status, content, truncated, parent_call_id}` в
     `finally` — `status`/`content` берутся из `ToolMessage`, если исполнение успешно, либо из
     пойманного исключения (`status="error"`, `content=str(exc)`), после чего исключение
     передаётся выше (`raise`) нетронутым — так `ToolNode`'s `handle_tool_errors` продолжает
     формировать ту же error-`ToolMessage` для LLM субагента, что и без обёртки.
  `SubagentRunner.run` получил два новых keyword-only параметра, `stream_writer: StreamWriter
  | None = None` и `parent_call_id: str | None = None` (оба по умолчанию `None` — обратная
  совместимость с прямыми вызовами `run()` в `test_runner.py`, ни один не передаёт эти
  параметры и не подвергается обёртке). Обёртка применяется к `resolved_tools` только если оба
  переданы.
- `backend/app/agent/tools/subagents.py` — `run_subagent` передаёт
  `stream_writer=runtime.stream_writer, parent_call_id=runtime.tool_call_id` в `runner.run(...)`
  — оба берутся из `ToolRuntime`, инжектируемого в тул исполняющим его `ToolNode` основного
  графа (единственное место, где живой writer и `call_id` этого самого вызова доступны
  одновременно — design-brief § «Вложенность субагента»).
- Разовая сквозная проба (не коммитится, аналог `heartbeat_smoke.py`/T1.5-пробы): временный
  скрипт гонял `SubagentRunner.run()` через реальный `build_subagent_graph`/`ToolNode` со
  скриптованной моделью, вызывающей фейковый тул, который сам эмитит `sphere_write` изнутри
  (симулирует KS-инструмент), и собирал события в список через переданный `stream_writer`.
  Результат — ровно 4 события в порядке `tool_call_started → tool_call_args → sphere_write →
  tool_result`, все с `parent_call_id == "call-outer-1"` (включая `sphere_write`, дошедший
  через `SUBAGENT_PARENT_CALL_ID`, а не переданный явно). Второй прогон, с тулом, кидающим
  исключение: `tool_result` пришёл со `status="error"` и текстом исключения в `content`,
  исключение при этом действительно долетело до вызывающего (`pytest.raises`-эквивалент) —
  подтверждает, что обёртка не глотает ошибки молча. Оба скрипта удалены после проверки.
- Тесты — списком с обоснованием (правило A6: приведение существующего словаря к новым
  параметрам, не новые кейсы — их пишет `test-author`):
  - `backend/tests/subagents/test_run_subagent_tool.py` — `SpyRunner.run` получил два новых
    keyword-only параметра, `stream_writer: Any = None` и `parent_call_id: str | None = None`,
    записываемых в `self.calls` тем же паттерном, что и остальные аргументы. Без этого правки
    любой из существующих 7 integration-тестов файла упал бы с `TypeError` на новый keyword
    argument, который `make_run_subagent_tool`'s `run_subagent` теперь всегда передаёт в
    `runner.run(...)`. Существующие ассерты (`call["config"]`, `call["canary_token"]` и т. д.)
    не тронуты — не новый сценарий, только расширение сигнатуры под новый словарь вызова.
  - Файлы, которые я **не** тронул, хотя план мог предполагать правку: `test_runner.py` (все
    вызовы `runner.run(...)` не передают `stream_writer`/`parent_call_id` — новые параметры
    строго опциональны с дефолтом `None`, обёртка тулов не активируется, поведение и ассерты
    файла не меняются) и `test_stream_isolation.py` (план верификации фазы называет его
    «дополненным фактом ‘субагентные custom-события проходят’» — прочитан целиком: обе его
    фикстуры конструируют только текстовые `AIMessageChunk` на уровне `runner.py`'s
    `stream_mode="messages"`-фильтра, никак не пересекаются с обёрткой тулов внутри
    `SubagentRunner`, которую вводит эта фаза; факт «доезжают» подтверждён разовой пробой
    выше, а не новым тест-кейсом в этом файле — тот же прецедент, что и в T1.3 (см.
    «Решения и обоснования» этой фазы: план предполагал механическую правку файла, по факту
    скоуп не пересёкся).

## Реализовано в фазе T1.7

- `backend/app/services/agent_runner.py` — три новых frozen-dataclass типа рядом с `Message`
  (та же форма — «внутренний value-объект рантайма агента» из conventions.md § Типизация):
  `ReasoningPart {content}`, `TextPart {content}`, `ToolCallPart {call_id, tool, args, status,
  result_preview, truncated}`, каждый с полем-дискриминатором `type: Literal[...]`; тип-алиас
  `Part = ReasoningPart | TextPart | ToolCallPart`. `Message` получил `parts: list[Part] =
  field(default_factory=list)` — остальные поля (`id`, `role`, `content`, `created_at`,
  `redacted`) не тронуты (совместимость).
- `backend/app/agent/checkpoint_history.py` — `CheckpointHistory.history()` переписан с
  фильтрации на группировку по ходам:
  - находит индекс первого `HumanMessage`, отбрасывает всё до него (после компакции там
    лежит id-less `summary_msg` из `graph.py:_reduce_context` — служебная сводка, не ход);
  - далее идёт по сообщениям, накапливая сегмент между `HumanMessage`; на каждом
    `HumanMessage` — `flush_segment()` (сборка предыдущего сегмента в assistant-`Message`,
    если сегмент непуст) и добавление user-`Message` для самого `HumanMessage` (без `parts` —
    типизированные parts относятся только к ассистентской стороне хода, дизайн-бриф не
    описывает их для пользовательских сообщений);
  - новый метод `_build_turn_message(segment)` строит один assistant-`Message`: собирает
    `tool_call_id -> ToolMessage` по всему сегменту, затем идёт по `AIMessage`-сообщениям
    сегмента по порядку — с `tool_calls` эмитит `reasoning`(опц.) + один `tool_call`-part на
    каждый вызов (парный `ToolMessage` по `call_id`; если не нашёлся — `status="pending"`,
    `result_preview=""`, ход застал вызов незавершённым); без `tool_calls` — это финальное
    сообщение хода (`final_ai`): `reasoning`(опц.) + `text`, либо (если
    `security_redacted`) один `text`-part со стандартной redaction-заглушкой без reasoning
    (см. «Решения и обоснования»);
  - `id`/`created_at`/`redacted`/`content` итогового `Message` берутся у `final_ai`, если он
    есть, иначе у последнего `AIMessage` сегмента (ход, оборвавшийся на tool-вызове) — тот же
    якорь, на который сегодня резолвятся `trace_id`/`feedback_score`/`artifacts` в
    `routes/chats.py:86-95`, инвариант не менялся, только источник самого `id`/`created_at`
    расширен на «последний доступный», а не только «последний без tool_calls».
  - `args` каждого `tool_call`-part — `json.dumps(tc["args"], ensure_ascii=False)`, тот же
    вид данных, что и `tool_call_args.args` на проводе (JSON-строка, не dict) — общий
    `text_limits.truncate` применяется отдельно к `args` и к `result_preview`, `truncated`
    поднимается, если усечено хоть одно поле.
- `backend/app/api/schemas/chats.py` — `ReasoningPartOut`/`TextPartOut`/`ToolCallPartOut`
  (Pydantic `BaseModel`, по одному на форму данных, пересекающих HTTP-границу) + тип-алиас
  `MessagePartOut = Annotated[ReasoningPartOut | TextPartOut | ToolCallPartOut,
  Field(discriminator="type")]`; `MessageOut.parts: list[MessagePartOut] = []`.
- `backend/app/api/routes/chats.py` — приватный маппер `_part_out(part: Part) -> MessagePartOut`
  (`isinstance`-диспетчер по трём внутренним dataclass-типам в Pydantic-модели); `get_chat`
  прокидывает `parts=[_part_out(p) for p in m.parts]` в конструктор `MessageOut`. Импорт
  `Part`/`ReasoningPart`/`TextPart`/`ToolCallPart` из `app.services.agent_runner` — разрешён
  import-linter'ом (`api/routes` запрещено импортировать только `repositories`/`storage`/
  `agent` напрямую, `services` не входит в запрет).
- `alembic`/`app/models` не тронуты — источник один (чекпоинтер), новой персистентности нет.
- Тесты — списком с обоснованием (правило A6):
  - `backend/tests/agent/test_checkpoint_history.py` (существующий файл фазы feat-009, не
    T1.7) — приведён к новой модели, без новых тест-файлов:
    - `test_history_maps_human_and_assistant_and_excludes_tool_turns` переименован в
      `test_history_groups_a_tool_call_turn_into_one_assistant_message` и усилен: раньше
      проверял только `(role, content)`-пары (это осталось бы зелёным и без изменения кода —
      старое поведение «отфильтровать лишнее» и новое «сгруппировать в одно сообщение» дают
      одинаковый список пар на этой фикстуре), теперь дополнительно проверяет `len(result) ==
      2` и `assistant_message.parts == [ReasoningPart(...), ToolCallPart(...),
      TextPart(...)]` — иначе тест не доказывал бы группировку, которую вводит эта фаза, и
      прошёл бы одинаково что до, что после правки. Это и есть эмпирическое подтверждение
      правила «один ход = один `MessageOut`» (см. отчёт фазы).
    - `test_history_swaps_redacted_assistant_content` — фикстура была нежизнеспособна под
      новой моделью буквально (единственный `AIMessage` без предшествующего `HumanMessage` —
      после «сообщения до первого `HumanMessage` дропаются» такой список даёт `[]`, тест упал
      бы не на редакции, а на отсутствии человеческого сообщения). Добавлен предшествующий
      `HumanMessage(id="h1")` — минимальная правка прекондиции, сама проверка (redacted flag +
      content-заглушка) не изменилась; дополнена одной строкой `parts == [TextPart(stub)]`,
      подтверждающей, что redaction-политика согласована между `content` и `parts` (пункт 4
      верификации фазы).
    - Остальные 10 тестов файла (`raw_messages_*`, `created_at`, `last_ai_message_id_*`,
      `latest_redaction_*`) не тронуты — методы, которые они покрывают
      (`raw_messages`/`last_ai_message_id`/`latest_redaction`), эта фаза не меняла; прогнаны,
      зелёные.
- Разовая проба (не коммитится, тот же паттерн, что `heartbeat_smoke.py`/T1.5/T1.6): скрипт в
  скрэтчпаде строит ход из `HumanMessage` + `AIMessage(tool_calls=[c1, c2])` + `ToolMessage`
  только для `c1` (`c2` не резолвлен — ход «застыл» на исполнении инструмента) и гоняет через
  `CheckpointHistory.history()`. Результат: ровно один assistant-`Message` с `id="a1"` (id
  единственного, tool-calling `AIMessage` — финального без `tool_calls` в сегменте нет),
  `content=""`, `parts=[ToolCallPart(call_id="c1", status="success", result_preview="search
  result"), ToolCallPart(call_id="c2", status="pending", result_preview="")]`. Отдельно
  проверено, что `last_ai_message_id()` для того же треда возвращает `None` (сообщений без
  `tool_calls` нет вообще) — поведение не новое, тот же метод этой фазой не менялся; убеждён,
  что «ход без финального `AIMessage`» не ломает пост-хок резолв `done.message_id`, он просто
  честно не находит его, как и до этой фазы. Скрипт удалён после проверки.

## Реализовано в фазе T1.8

- `backend/app/agent/tools/registry.py` (новый) — единственный источник состава инструментов
  агента, четыре функции:
  - `internal_tool_names() -> list[str]` — имена всех internal-инструментов в любом окружении:
    `[t.name for t in ks_tools]` + `user_memory_tools` + `make_skill_context_tools(frozenset())`
    (реальные объекты, ноль I/O, `skill_names` не влияет на имена — только на замыкание
    валидации внутри `save_skill_context`) плюс литеральный кортеж `("load_skill",
    "create_artifact", "generate_image", "run_subagent")` для четырёх фабричных тулов. Эти
    четыре — не сконструированные инстансы: их фабрики требуют живой `session_factory`,
    провалидированный `Settings` (`jwt_secret` без дефолта — `Settings()` без окружения падает)
    и/или `SubagentRunner`, чего детерминированный, не трогающий сеть/БД генератор не должен
    требовать. Литералы безопасны ровно потому, что `.name` каждого тула фиксирован на этапе
    импорта — `@tool` берёт его из `__name__` обёрнутой функции, не из аргументов фабрики.
    `run_subagent` включён безусловно (та же логика, что и `builtin_mcp_tool_names` не
    фильтрует по `enabled`): `configs/agent.yaml`'s `subagents` — опциональная секция,
    подпись нужна независимо от того, включена ли она в конкретном окружении.
  - `assemble_internal_tools(*, skill_context_tools, load_skill, create_artifact,
    generate_image, run_subagent=None) -> list[BaseTool]` — сборка реального списка
    `internal_tools`, которым пользуется `app.main`; та же группировка (`ks_tools`,
    `user_memory_tools`, skill-context, четыре фабричных тула), что и в
    `internal_tool_names()`, поэтому фикстур физически не может разойтись с тем, что раннер
    получает при старте.
  - `builtin_mcp_tool_names(agent_config) -> list[str]` — `allowed_tools` каждого сервера из
    `agent_config.mcp_servers`, без фильтра по `enabled` (флаг переключается по окружениям —
    например отсутствием API-ключа, — подпись нужна для сервера, который просто объявлен).
  - `build_tool_name_fixture(agent_config) -> list[dict[str, str]]` — объединяет оба списка в
    `{"name", "origin"}`-записи (`origin` — `"internal"`/`"builtin_mcp"`), сортирует по `name`.
    Пользовательские MCP-инструменты сюда не попадают — они резолвятся в рантайме, design-brief
    отводит им сырое имя + пометку источника вместо записи в реестре.
- `backend/app/agent/tools/__init__.py` — короткий комментарий поясняет, почему `registry`
  не ре-экспортирован через `__all__` (его импортируют по полному пути `app.agent.tools.
  registry` — единственные три потребителя это уже делают, лишний слой реэкспорта не даёт
  эргономики).
- `backend/app/main.py` — сборка `internal_tools` идёт через `assemble_internal_tools` дважды
  (интерим-версия до `run_subagent`, финальная — после), обе замены строго механические
  (тот же порядок аргументов, что раньше был порядком `+`-конкатенации). Прямые импорты
  `ks_tools`/`user_memory_tools` из `main.py` убраны — `registry.py` теперь единственное место,
  которое их использует напрямую для сборки.
- `scripts/generate_tool_names_fixture.py` (новый) — тонкий CLI по образцу
  `scripts/langfuse_security_experiment.py`: `load_agent_config()` (файл, не БД/сеть) →
  `build_tool_name_fixture(...)` → пишет отсортированный JSON в
  `backend/contracts/agent-tool-names.json`. Импортирует `app.*`, поэтому запускается с
  `PYTHONPATH=backend` (тот же паттерн, что `make lint`'s `lint-imports`, у которого тоже
  явный `PYTHONPATH=backend:services/siem-service`) — команда зафиксирована в докстринге
  скрипта и в тексте ассерта drift-гейта.
- `backend/contracts/agent-tool-names.json` (новый) — сгенерированный фикстур, 18 записей: 13
  `internal` (4 KS + 2 user-memory + 3 skill-context + `load_skill`/`create_artifact`/
  `generate_image`/`run_subagent`) + 5 `builtin_mcp` (`firecrawl_extract`/`firecrawl_scrape`/
  `firecrawl_search`/`tavily_extract`/`tavily_search` — `tavily` объявлен, но
  `enabled: false`, и всё равно попал в фикстур).
- `backend/tests/agent/test_tool_names_fixture.py` (новый, предусмотрен планом как часть
  механизма, не покрытие поведения) — единственный тест-кейс, `@pytest.mark.unit`: читает
  закоммиченный JSON, сравнивает с `build_tool_name_fixture(load_agent_config())`, при
  расхождении печатает команду регенерации. По образцу
  `test_pricing_consistency.py` (тот же класс проверки — конфиг-дрейф, без сети/БД).

**Verification (план T1.8):**
- `make check`/`make test` — зелёные (см. отчёт фазы ниже).
- Детерминированность генератора подтверждена: два прогона подряд дают побайтово идентичный
  `agent-tool-names.json` (проверено `md5sum`/`diff`).
- Drift-гейт вручную проверен на срабатывание: временно добавлен `tavily_new_probe_tool` в
  `configs/agent.yaml`'s `mcp_servers.tavily.allowed_tools` без регенерации фикстура — тест
  покраснел с точным диффом (`tavily_search` != `tavily_new_probe_tool` на позиции 16,
  `update_section` лишний в правом списке); правка отменена (`git checkout`), тест снова
  зелёный.
- Фикстур сверен построчно с ожидаемым составом (см. выше) — совпадает.

## Реализовано в фазе T1.9

- `doc/tech/streaming.md` — переписан целиком под контракт v2: полная таблица событий с
  источником и терминальностью, отдельные разделы forward-compat / лимиты (heartbeat 5 с,
  усечение 2000 симв., таймаут клиента — 3 пропущенных heartbeat) / вложенность субагента
  (`parent_call_id`, механизм явного writer'а вместо `get_stream_writer()` внутри субагента) /
  изоляция токенов (два разных механизма — тег+фильтр для субагента, callback-detach для
  суммаризатора) / четыре security-чекпоинта + pre-stream 403-гейт `require_unblocked_thread` /
  история typed parts (таблица `Part`, границы хода, `status="pending"`, redaction-политика).
  Обновлены обе диаграммы: `Stream Lifecycle` (`sequenceDiagram`, все четыре точки эмиссии
  `security_block`, включая post-stream после `final_output_review_complete`) и `Cancellation`
  (два независимых чекпоинта — между итерациями `astream` и на таймере `HeartbeatPacer`). Обе
  сверены рендером через `mermaid` MCP на тёмной теме (`theme="dark"`) — при первом прогоне
  lifecycle-диаграмма не парсилась из-за `;` внутри текста `Note over R: ...` (mermaid трактует
  `;` как разделитель внутри реплики персонажа), заменено на скобки; после правки обе валидны.
  Раздел «Frontend: потребление стрима» сужен до протокольного контракта потребления
  (диспетчеризация по типу, forward-compat, отмена, таймаут от heartbeat, TanStack invalidation)
  — детали текущей реализации (`Zustand`-поля `activeTool` и т. п., компоненты `ThinkingIndicator`/
  `ToolIndicator`) не перенесены: они привязаны к словарю v1 (`tool_start`/`tool_end`), который
  контракт этой фазы убрал, и их полная перестройка — предмет T2, не этой фазы; описывать их как
  «текущее поведение» значило бы фиксировать в источнике правды состояние, которое сам этот
  документ делает некорректным с момента публикации. Решение задокументировано ниже.
- `doc/tech/conventions/agent.md` — таблица коллабораторов `Runner`'а (§ Agent Runtime)
  исправлена (была: `StreamEventMapper` → `tool_start`/`tool_end`/`artifact_created`; стало:
  `TokenChunkMapper` и `StreamEventMapper` раздельно, с актуальным словарём событий) и дополнена
  `HeartbeatPacer`. Новая подсекция «Добавляешь инструмент агенту» — чек-лист из четырёх пунктов
  design-brief § «Конвенции» (подпись фронта + машинная цепочка проверки полноты реестра;
  artifact по атрибуту; `agent_event` через `emit_agent_event`, не голый `get_stream_writer()`;
  raw-разворот без rich-рендера), с явной командой перегенерации фикстура.
- `doc/tech/agent-runtime.md` — правка дрейфа: строка `get_history` в таблице `AgentRunner`
  (была «HumanMessage + AIMessage без tool_calls», стало — typed parts со ссылкой на
  `streaming.md`); `stream_mode` в § «Agent Graph» — было два канала (`messages`/`updates`) с
  устаревшим списком событий (`tool_start`/`tool_end`), стало три канала с актуальным составом
  и ссылкой на `streaming.md`; абзац о субагенте в § «Субагенты» дополнен фактом, что его шаги
  видны в live-ленте через lifecycle-события с `parent_call_id` (раньше документ говорил только
  про фильтрацию токенов, создавая впечатление, что субагент — чёрный ящик до самого результата).
- `doc/tech/backend.md` — сверен построчно (flowchart «Сквозной поток: сообщение в чат», § API
  Layer, таблица эндпоинтов `Messages`): расхождений с кодом не найдено, документ на своём
  уровне абстракции («события графа» без перечисления конкретных типов) остаётся верным
  независимо от состава событий — правок не потребовалось.

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
- **Как `tool_call_cancelled` переиспользует per-run состояние T1.3, а не заводит своё
  параллельно.** План прямо требовал «того же per-run состояния, что и T1.3» — рассмотрел
  два способа этого добиться:
  1. *(отверг)* Передавать `pending_call_ids` как обычный `set`/`list` параметром в
     `updates(data, pending_call_ids)` на каждый вызов, а бухгалтерию (кто анонсирован, кто
     разрешён) вести целиком в `_run_turn()` раннера. Это оставило бы `StreamEventMapper`
     формально «чистым» (без своего состояния), но раздвоило бы одну заботу («какие call_id
     ещё не закрыты») между раннером и мапперои: раннер добавлял бы id при
     `tool_call_started`, а мапперу пришлось бы мутировать тот же объект по ссылке при
     `tool_result` — семантика мутации разделяемого изменяемого объекта между двумя
     компонентами хуже читается и тестируется, чем инкапсуляция в одном месте.
  2. *(выбрал)* Сделать `StreamEventMapper` per-run коллаборатором (как `TokenChunkMapper` уже
     стал в T1.3) с собственным `_pending_call_ids` и публичным методом
     `note_call_announced(call_id)`, который раннер дёргает при каждом `tool_call_started` из
     token-канала. Раннер остаётся точкой связи двух каналов (он один видит оба потока
     событий — `messages` и `updates` — в одном цикле `async for mode, data in
     graph.astream(...)`), но вся бухгалтерия «объявлен / разрешён / срезан» инкапсулирована
     в одном объекте с одним инвариантом, а не размазана по двум местам. Тот же принцип
     factory-инъекции (`event_mapper_factory`, конструктор раннера), что и у
     `token_mapper_factory` — согласованность двух коллабораторов одного слоя.
- **Дедупликация с token-каналом: `tool_start`/`tool_end` не оставлены «на всякий случай»
  рядом с новыми событиями, а вычищены целиком.** Альтернатива — оставить их эмитироваться
  параллельно с `tool_call_started`/`tool_result` для обратной совместимости — отвергнута:
  design-brief таблица контракта v2 прямо перечисляет `tool_start`/`tool_end` в строке
  «Удаляются», а не «форвардить оба». Двойной сигнал начала вызова (ранний
  `tool_call_started` из token-канала — раньше на чанк раньше, ещё до завершения узла `agent`
  — и `tool_start` из updates на завершении узла) создал бы на фронте два конкурирующих
  события с разным таймингом для одного и того же логического «вызов начался», что
  противоречит модели «одна строка ленты = одна последовательность typed-parts» из брифа.
  Оставлять фронту разрешать эту гонку самому — плодить сложность вместо архитектурного
  решения «одно событие, один источник правды на этап жизненного цикла вызова».
- **`artifact_created` — признак по атрибуту (`msg.artifact is not None`), не whitelist имён.**
  Прямое следствие design-brief контракта (строка `artifact_created`: «по наличию
  `ToolMessage.artifact` (замена захардкоженного whitelist имён)») и чек-листа конвенций п.2
  («Artifact-producing → `response_format="content_and_artifact"` → событие по атрибуту, не по
  имени»). Whitelist требовал ручной правки `stream_events.py` на каждый новый
  artifact-producing инструмент (пропущенная правка молча теряла бы событие); признак по
  атрибуту делает это автоматическим следствием контракта самого инструмента — если тул
  вернул `artifact`, лента об этом узнает независимо от того, как он называется.

- **`agent_events.py` — отдельный модуль, не метод/функция в `stream_events.py` или
  `runner.py`.** Прямое следствие conventions/agent.md § Agent Runtime («новая сквозная
  забота в runtime → отдельный коллаборатор, а не ещё один метод»), но здесь причина ещё и
  структурная: этот код вызывается не раннером и не мапперами, а *инструментами*
  (`knowledge_sphere.py`, `user_memory.py`, `skill_context.py`) и *графом* (`graph.py`) —
  модулями, которые физически не могут импортировать `runner.py` (не по кругу — `runner.py`
  сам импортирует `graph_factory`, который в конечном счёте собирает граф из тех же tools) и
  не должны обзаводиться знанием о `StreamEventMapper`/`TokenChunkMapper` (те заняты формой
  событий `messages`/`updates`, а не тем, что писать в `custom`). Отдельный модуль на уровне
  `app/agent/` — единственное место, от которого могут зависеть и тулы, и граф, и раннер, не
  создавая цикл.
- **Приоритет источников writer'а: контекстная переменная → `get_stream_writer()` → no-op —
  и не в другом порядке.** Если бы `get_stream_writer()` шёл первым, а контекстная переменная
  — вторым (или вообще не проверялась бы до T1.6), то в момент, когда T1.6 добавит обёртку
  субагента и её контекстную переменную, вызов KS/memory/skill-context тула *внутри*
  субагента продолжил бы резолвиться в `get_stream_writer()` того субагентского Pregel-рана
  (см. входной факт плана №5 — вложенный граф исполняется через `ainvoke`, значит его
  `custom`-стрим никем не потребляется) — событие тихо терялось бы, и ни один тест не
  показал бы красного (нет исключения, просто нет события на выходе). Обратный порядок не
  «тоже сработал бы, но менее элегантно» — он был бы молчаливым регрессом на T1.6, который
  проявился бы не в этой фазе, а в следующей, причём как отсутствие, а не как ошибка. Именно
  поэтому приоритет — часть контракта этой фазы, а не деталь реализации: T1.6 не должен
  трогать порядок проверки, только выставлять переменную.
- **`DOMAIN_AGENT_EVENT_KINDS` живёт в `agent_events.py`, импортируется в `runner.py`, не
  продублирован списком-литералом на стороне раннера.** Один и тот же набор строк решает две
  разные задачи на двух концах custom-канала: `emit_agent_event` использует его как
  allowlist для валидации `kind` на входе (не даёт эмитировать опечатку), `runner.py` — как
  условие маршрутизации «обернуть в `agent_event` или пробросить как есть» на выходе. Если бы
  каждая сторона держала свою копию множества, добавление нового доменного kind (например,
  в T1.6 или позже) потребовало бы синхронно править оба файла — разъехавшиеся копии дали бы
  либо непойманную опечатку в эмиттере, либо кind, который эмиттер считает валидным, а
  раннер — нет (и тогда он попал бы в ветку passthrough как «недоменный», ломая контракт
  `agent_event {kind, payload}` без единой ошибки).
- **`emit_agent_event` бросает `ValueError` на неизвестный `kind`, а не проглатывает молча.**
  Асимметрично с «безопасно вне графа»: там отсутствие рантайма — ожидаемая, штатная ситуация
  (тесты вызывают tools напрямую), а неизвестный `kind` — программная ошибка вызывающего
  (опечатка в строковом литерале внутри своего же тула). Проглотить её так же тихо, как
  отсутствие рантайма, означало бы, что и настоящую типографскую ошибку в коде проекта нельзя
  было бы отличить от штатного «нет графа» — а именно эту не-разделённость и предупреждал
  design-brief про «безопасный хелпер» (safety относится к *рантайм-контексту*, а не к
  *данным*, которые передаёт наш собственный код). `ValueError` здесь падает при разработке
  (юнит-тест инструмента или ручной прогон), не в проде на реальном трафике — там `kind`
  всегда один из четырёх литералов, зашитых в вызовах этой же фазы.
- **Ловятся именно `KeyError` и `RuntimeError`, не голый `except Exception`.** Это ровно два
  исключения, которые реально бросает `get_stream_writer()` в двух разных «вне графа»
  сценариях (проверено экспериментально, не только по формулировке плана): `KeyError
  ('__pregel_runtime')` — когда есть хоть какой-то runnable-контекст, но не полный
  Pregel-рантайм (ровно случай `tool.ainvoke(...)` в существующих тестах инструментов);
  `RuntimeError("Called get_config outside of a runnable context")` — когда вызов происходит
  вообще вне какого-либо runnable-контекста (ровно случай прямого вызова
  `_reduce_context(...)` в `test_graph.py`, минуя граф целиком). Широкий `except Exception`
  спрятал бы и настоящий баг где-то глубже в резолве раннер-контекста LangGraph — узкий
  перехват двух конкретных, проверенных типов оставляет любую другую ошибку падать, как ей
  положено.
- **Усечение payload'а — по строковому значению каждого поля через общий `text_limits.truncate`,
  без отдельного флага `truncated` на самом `agent_event`.** Design-brief таблица контракта
  перечисляет поля `agent_event` как ровно `{kind, payload, parent_call_id?}` — никакого
  `truncated` там нет (в отличие от `tool_call_args`/`tool_result`, где он есть явно). При
  этом design-brief прямо требует «усечение args/content/task в SSE и API — 2000 символов +
  флаг truncated» как общую политику лимитов — то, что для `agent_event` эта политика
  выражена без отдельного видимого флага, а просто как факт использования того же
  `truncate()`, — осознанное отражение того, что текущие четыре kind'а несут только
  короткие идентификаторы (`section_id`/`key`/`skill_name`), а не произвольный
  пользовательский текст: усечение здесь — defensive-мера на случай будущего роста полей, не
  ожидаемое поведение сегодня (ни один существующий вызов `emit_agent_event` в этой фазе
  передаёт строку длиннее лимита).
- **Минимальный payload на kind — только идентифицирующее поле(я), без поля-действия
  (`action`/`operation`).** План формулирует требование буквально: «минимальным payload (то,
  что нужно подписи на фронте: раздел/ключ/скилл)» — это `section_id` для `sphere_write`,
  `key` для `memory_write`, `skill_name`+`key` для `skill_context_write`, ничего для
  `compaction`. Рассматривался вариант добавить `action: "create"|"update"|"delete"` (или
  `"save"|"delete"`), чтобы отличать создание секции от её удаления в подписи фронта, — не
  добавлен: (1) буквальная формулировка плана называет только идентифицирующие поля, а
  добавление таксономии действий — решение о форме продукта, которое стоит взять у
  архитектора явно, а не выводить по аналогии; (2) для `sphere_write`/`skill_context_write`
  различение create/update/delete и так доступно на фронте через parallельные события
  `tool_call_started {tool: "create_section"|"update_section"|"delete_section"}` того же
  вызова — `agent_event` не единственный источник этого сигнала, так что минимальный вариант
  не теряет информацию, а лишь не дублирует её на двух каналах.

- **Обёртка тулов субагента — прокси-`BaseTool` вокруг списка `resolved_tools`, а не
  `ToolNode(..., awrap_tool_call=...)` на стороне `build_subagent_graph`.** LangGraph 1.1.3
  действительно даёт официальный extension point ровно под эту задачу
  (`ToolNode.__init__(wrap_tool_call=…, awrap_tool_call=…)`, вызывается с `ToolCallRequest` до
  исполнения и `execute()`-колбэком) — рассматривал его как альтернативу. Не выбран по двум
  причинам: (1) план прямо ограничивает файловый скоуп фазы `subagents/runner.py` +
  `tools/subagents.py` — `awrap_tool_call` потребовал бы новый параметр в
  `build_subagent_graph`/`ToolNode` внутри `subagents/graph.py`, файла вне списка изменений
  фазы; (2) прокси-обёртка на уровне списка тулов не требует вообще никакого изменения
  `graph.py` — `ToolNode`/`bind_tools` получают ровно то же количество объектов с теми же
  `name`/`args_schema`, что и раньше, просто других экземпляров. Обе формы эквивалентны по
  наблюдаемому поведению (`ToolCallRequest`/наш `input`-дикт несут один и тот же `{id, name,
  args}`); прокси — единственная, не раздвигающая границы фазы.
- **`_LifecycleEmittingTool` делегирует исполнение `wrapped_tool.ainvoke(...)` целиком, не
  переопределяет `_run`/`_arun`.** Тул-реестр субагента (`internal_tools + mcp_tools`,
  `main.py`) неоднороден: у части тулов `response_format="content_and_artifact"`
  (create_artifact, KS/memory/skill-context пишущие тулы), у части — обычные MCP-инструменты.
  Переопределение `_run`/`_arun` потребовало бы либо копировать вручную это разнообразие полей
  BaseTool (`response_format`, `handle_tool_error`, `return_direct`, …) на прокси, либо
  потерять его для конкретных тулов. Проксирование на уровне `ainvoke` (точка, которую
  `ToolNode` реально вызывает — `tool.ainvoke(call_args, config)`,
  `langgraph/prebuilt/tool_node.py`) обходит это: реальный тул сам решает, как из своего
  возврата собрать `ToolMessage`/артефакт, обёртка лишь читает уже готовый результат.
- **Оборачивание условно — только если оба, `stream_writer` и `parent_call_id`, переданы.**
  `SubagentRunner.run` вызывается и напрямую в `test_runner.py` (11 существующих тестов, ни
  один не передаёт эти параметры) — если бы обёртка включалась безусловно (например, по
  наличию хоть какого-то дефолтного writer'а), тем тестам потребовался бы дополнительный
  no-op-writer или правка сигнатур без всякой пользы для проверяемого поведения. Условие «оба
  или ни одного» — то же самое решение, что design-brief закладывает для самого механизма
  (`run_subagent` — единственное место, где оба значения совместно доступны), просто
  перенесённое на уровень интерфейса `run()`.
- **Ошибка исполнения тула: `tool_result` эмитится в `finally` и статус берётся из
  `except`-ветки, а исключение всё равно `raise`-ится дальше.** Альтернатива — проглотить
  исключение внутри обёртки и вернуть свой `ToolMessage(status="error")` — отклонена: это
  задвоило бы обработку ошибок с `ToolNode(handle_tool_errors=handle_tool_error)`
  (`subagents/graph.py`), которая уже конвертирует необработанное исключение из
  `tool.ainvoke(...)` в error-`ToolMessage` тем же самым текстом
  (`app.agent.tool_guards.handle_tool_error`). Обёртке нужно только *узнать* про исход
  (для `tool_result`), не *решать* его — `except ... raise` даёт это без дублирования логики,
  которая и так уже есть на уровень выше в `ToolNode._execute_tool_async`. Подтверждено
  разовой пробой (см. «Реализовано в фазе T1.6»): исключение действительно долетает до
  вызывающего `wrapped.ainvoke(...)`, `tool_result` при этом всё равно ушёл.
- **`SUBAGENT_PARENT_CALL_ID` — новая контекстная переменная в `agent_events.py`, файле вне
  списка изменений фазы в плане (там названы только `subagents/runner.py` и
  `tools/subagents.py`).** План описывает это явно текстом требования, не файлом: «хелпер из
  T1.5 её подхватывает» — единственное место, где домен-тул (`sphere_write`/`memory_write`/
  `skill_context_write`) вообще может узнать про `parent_call_id`, раз сам тул понятия не
  имеет, вызван ли он из-под субагента (`emit_agent_event(kind, payload)` не принимает такой
  параметр и не должен — иначе каждый из трёх тул-файлов пришлось бы трогать, чтобы прокинуть
  его через сигнатуру). `agent_events.py` — тот единственный слой, от которого зависят и тулы,
  и (теперь) обёртка субагента, не создавая цикл (тот же аргумент, что обосновывал вынос этого
  модуля отдельно в T1.5, — см. выше). Прочитано как «правка по месту, а не выход за скоуп»:
  T1.5 уже завела в этом модуле ровно такую же по форме контекстную переменную
  (`SUBAGENT_STREAM_WRITER`) с явной пометкой «задел под T1.6», просто для writer'а, а не для
  `parent_call_id`, — вторая переменная того же модуля, для той же обёртки, с тем же
  lifetime, естественно ложится туда же, а не в файл, который план перечисляет по имени.

- **`Part`-типы — три `frozen`-dataclass'а в `services/agent_runner.py`, не Pydantic-модели и
  не один дикт-конверт.** conventions.md § Типизация относит внутренние value-объекты
  рантайма агента к `@dataclass` (тот же ряд, что уже занимает `Message`/`StreamEvent`) — API
  границу (`MessageOut.parts`) пересекает отдельный, параллельный набор Pydantic-моделей в
  `api/schemas/chats.py`, что и требует import-linter'ов layering-контракт (`services` не
  может импортировать `api.schemas` — обратное направление). Альтернатива «эмитить сразу
  Pydantic-модели из `checkpoint_history.py`» была отклонена: `app.agent`/`app.services` не
  участник цепочки, которой разрешён импорт `app.api.*` (единственное разрешённое исключение —
  `services.mcp_server -> api.schemas.mcp_servers`, точечный allow-list, не прецедент для
  нового обратного импорта).
- **Дискриминатор `type` — литеральное поле дискриминированного варианта, не `isinstance` по
  форме полей.** И внутренний `Part`, и внешний `MessagePartOut` используют
  `type: Literal[...]` с дефолтным значением — тот же паттерн, каким design-brief описывает
  сам wire-контракт (`StreamEvent.type`), и то, что явно требует план («дискриминированный по
  `type` список»). `_part_out()` в `routes/chats.py` всё равно диспетчерит по `isinstance` на
  внутренней dataclass-стороне (три разных Python-типа, не один тип с полем-тегом) — это
  единственная граница, где `isinstance` неизбежен, потому что `Part` сам является
  `Union`, а не одним классом с полем.
- **Редактированное сообщение (`security_redacted` на финальном `AIMessage`) даёт только
  `TextPart(stub)`, без `reasoning`-part'а — даже если `additional_kwargs["reasoning"]`
  присутствует.** Не вытекает из плана буквально (план формулирует это как инвариант для
  описания, не как готовое решение: «redacted-сообщения отдают parts согласованно с
  существующей политикой редакции»). Разобрал оба источника редакции по коду:
  `RuntimeSecurityEnforcer._redact_final_output` (`runtime_security.py:185-209`) создаёт
  редактированный `AIMessage` с нуля, с собственным `additional_kwargs` — реального
  `reasoning` там физически нет, вопрос неактуален. Но `guard_tool_call_args`
  (`tool_guards.py:154-171`) редактирует иначе: `additional_kwargs={**response.additional_kwargs,
  "security_redacted": True, ...}` — **спред сохраняет исходный `reasoning`**, если модель его
  прислала вместе с заблокированным tool-call. Существующая политика (`content` до этой фазы)
  ничего не оставляет от исходного сообщения — полная замена на generic-заглушку, а не частичный
  показ. Решение: применить тот же принцип к `parts` — раз причина редакции именно в том, что
  сообщение сгенерировано под воздействием инъекции, показывать «безобидную» половину (reasoning)
  рядом с заглушкой вместо текста было бы более узкой политикой, чем действующая для `content`, и
  потенциально утечкой контекста инъекции доверенному наблюдателю пользователя. Проверено разовой
  пробой (см. «Реализовано в фазе T1.7», тест `test_history_swaps_redacted_assistant_content`).
- **`status="pending"` — третье значение, которого нет в дизайн-брифе (`success`/`error`
  только для wire-контракта `tool_result`), добавлено для незавершённого хода.** План прямо
  делегирует это решение фазе («ход, оборвавшийся на tool-вызове... обрабатывается отдельно —
  опиши в summary, как именно»), а не описывает готовую форму. Альтернативы: (1) не эмитить
  `tool_call`-part вовсе для незавершённых вызовов — отклонено, план явно требует «parts
  показывают, докуда агент дошёл», то есть именно факт начатого-но-незавершённого вызова должен
  быть виден; (2) `status: str | None` с `None` для «неизвестно» — отклонено в пользу explicit
  `Literal["success", "error", "pending"]`: третье именованное состояние читается прямо в типе,
  не требует `is None` проверки на стороне потребителя (фронта T2 или ревьюера), и не путается
  с «поле отсутствует из-за версии контракта». Подтверждено разовой пробой (см. выше).
- **Порядок parts — по позиции `AIMessage` в сегменте, `reasoning` и `tool_call`/`text`
  одного `AIMessage` считаются одним «событием» ленты, не переставляются относительно
  `ToolMessage`.** ``ToolMessage``ы сами не порождают частей — они только донор
  `status`/`result_preview` для уже эмитированного `tool_call`-part той же итерации, поэтому
  физическая позиция `ToolMessage` в списке (она всегда идёт сразу после своего `AIMessage`, до
  следующего) не может создать «дыру» в порядке parts. Совпадает с design-brief: «Порядок parts
  — порядок сообщений в треде».
- **`Message.parts` для пользовательских (`role="user"`) сообщений остаётся пустым списком, не
  `[TextPart(content)]`.** Design-brief таблица «Модель typed parts» и текст «одно сообщение
  ассистента = последовательность parts» относят parts исключительно к ассистентской стороне
  хода; user-сообщение и так полностью представлено плоским `content` (никогда не собирается из
  нескольких LangChain-сообщений — один `HumanMessage` = один `Message`, группировать нечего).
  Заполнение `parts` для роли user было бы данными, которых не просит ни бриф, ни план, без
  видимой пользы фронту (T2 всё равно рендерит user-бабл по `content`) — не добавлено.
- **Формат фикстура: плоский отсортированный по `name` массив `{"name", "origin"}`, не
  сгруппированный по `origin` объект.** Путь (`backend/contracts/agent-tool-names.json`) и
  необходимость пометки происхождения зафиксированы планом; конкретная JSON-форма — решение
  этой фазы, так как план говорит только «отсортированный массив имён + пометка
  происхождения». Альтернатива — `{"internal": [...], "builtin_mcp": [...]}` — отклонена: она
  вынуждала бы фронт-тест (T2, читает файл, не код бэкенда) знать заранее, под каким ключом
  искать конкретное имя, тогда как реальная задача теста — «для каждого имени в списке есть
  подпись в реестре», не «для каждой группы». Плоский список с полем `origin` на каждой
  записи даёт то же различение (T2 фильтрует по `origin`, если нужно) без вложенности.
  Сортировка — по `name` глобально, не «сначала все `internal`, потом `builtin_mcp`»: делает
  диффы читаемыми (`git diff` на добавление одного инструмента — одна строка, а не
  переупорядочивание целой группы) и не требует от читателя решать, в каком порядке идут сами
  группы.
- **Пользовательские MCP-инструменты не входят в `build_tool_name_fixture`, хотя технически
  видны раннеру.** Design-brief явно относит их к другому механизму отображения (сырое имя +
  пометка источника, не реестр), а `main.py` резолвит их в рантайме через
  `create_mcp_client`/`mcp_client.get_tools()` — сетевой вызов к конкретному пользовательскому
  серверу, несовместимый с «генератор детерминирован, без сети и БД». Их включение сделало бы
  фикстур недетерминированным (зависящим от того, какие MCP-серверы пользователь подключил на
  момент генерации) и противоречило бы контракту, который фронт-тест должен проверять
  стабильно в CI.
- **Четыре фабричных internal-тула (`load_skill`/`create_artifact`/`generate_image`/
  `run_subagent`) — литералы в `internal_tool_names()`, а не сконструированные инстансы.**
  Единственная альтернатива, дающая настоящие объекты без литералов — вызвать их фабрики с
  «пустыми» аргументами (`async_sessionmaker()` без `bind`, `Settings(jwt_secret="x", ...)` в
  обход `.env`, mock `SubagentRunner`). Отклонено: `Settings` требует явно заданных полей без
  дефолта (`jwt_secret`) — сборка одноразового валидного `Settings` только ради имени тула
  добавляет генератору знание о конфигурации приложения, которого у него по плану быть не
  должно («без сети и БД» — про изоляцию от рантайм-зависимостей вообще, не только от живых
  сетевых вызовов), и создаёт лишнюю точку поломки (следующее обязательное поле в `Settings` —
  и генератор ломается без всякой связи с составом инструментов). Литерал безопасен, потому
  что `.name` каждого из этих тулов — это `__name__` декорированной `@tool`-функции, а он не
  зависит от того, с какими аргументами вызвана фабрика; переименование функции обязано
  обновить оба места (`registry.py` и саму фабрику) синхронно, что ловится обычным ревью diff,
  а не скрытым рантайм-поведением.

- **Утверждения старого `streaming.md`, оказавшиеся неверными, и чем заменены** (материал для
  ревью — список, не всё как единая находка):
  1. *Wire-примеры и таблица событий несли `tool_start`/`tool_end`, без `stream_started`,
     `heartbeat`, `reasoning_chunk`, `tool_call_started`/`tool_call_args`, `tool_call_cancelled`,
     `agent_event`, `cancelled`.* Заменено полной таблицей v2: `tool_start`/`tool_end` удалены из
     документа (как и из кода — T1.4), добавлены все восемь новых типов с источником и
     терминальностью.
  2. *`security_block` документировался с payload `{checkpoint, detection_layer}`.* Код (T1.2)
     давно отдаёт `{}` — реальный payload проверен по `runner.py` построчно на всех четырёх
     точках эмиссии; заменено на явное «generic, `reason`/`checkpoint`/`detection_layer` остаются
     в Langfuse/SIEM».
  3. *Диаграмма `Stream Lifecycle` показывала одно ветвление (INJECTION на USER_INPUT / CLEAN),
     будто это единственная точка `security_block`.* На деле их четыре: pre-graph, mid-stream
     (детерминированный tail-чек на каждом `text_chunk`), end-of-stream classifier, post-stream
     in-graph inspection (`inspect_in_graph`) — причём четвёртая срабатывает **после**
     `final_output_review_complete`, а не вместо неё (аудит-находка №4, event-map.md). Новая
     диаграмма показывает все четыре точки и их порядок.
  4. *`final_output_review_started`/`_complete` описывались как эмитящиеся «как сейчас», без
     оговорки.* Код условен: `if not stream_error and not injection_emitted and full_response`
     (`runner.py:368`) — на чисто tool-ходе без единого текстового чанка пара не эмитится вовсе.
     Явно зафиксировано (вторая часть аудит-находки №4).
  5. *Отмена документировалась как `error ("Cancelled")` с единственной точкой проверки —
     между итерациями `astream`.* Заменено: терминальный `cancelled {}` (T1.2), плюс второй,
     независимый чекпоинт на таймере `HeartbeatPacer` — ловит отмену и во время долгого
     tool-вызова (аудит-находка №3), не только между шагами графа.
  6. *Ack/heartbeat в документе не существовали вообще* (раздел отсутствовал; event-map.md
     зафиксировал это как немую зону). Теперь центральная часть контракта: `stream_started` до
     setup-фазы, `heartbeat` каждые 5 с в любой тишине.
  7. *Pre-stream гейт `require_unblocked_thread` (HTTP 403) не упоминался нигде* (третья часть
     аудит-находки №4) — добавлен отдельным абзацем в § «Security-чекпоинты», как механизм,
     отдельный от SSE-контракта.
  8. *Транспортный fallback `error {"Stream failed"}` подразумевался идущим через
     `error_messages.yaml`, как и остальные `error`.* Проверено по `configs/error_messages.yaml`
     (нет такого ключа/значения) — задокументировано как единственное исключение из правила
     (четвёртая часть аудит-находки №4; код не тронут — см. решение фазы T1.2).
  9. *`get_history`/история не имела ни слова про typed parts* (в старом `streaming.md` не было
     раздела про историю вообще — `Message.content` был единственным источником текста). Добавлен
     раздел «История: typed parts» с таблицей `Part`, правилом группировки по ходам и
     `status="pending"` для оборвавшегося хода.
- **Frontend-раздел `streaming.md` сужен до протокольного контракта, детали `Zustand`-стора и
  конкретных компонентов (`activeTool`, `ThinkingIndicator`, `ToolIndicator`) не перенесены.**
  Не решение архитектуры фронта — решение о том, что именно фиксировать в документе, который
  T2 использует как источник правды по форме событий. Текущий фронтенд (не тронут в этом треке)
  всё ещё диспетчерит по словарю v1 — `tool_start`/`tool_end`, которых на проводе больше нет, —
  то есть буквальное описание «текущего поведения» в деталях устарело бы в момент публикации
  этого же документа. Протокольный контракт (диспетчеризация по типу, forward-compat, отмена,
  таймаут от heartbeat, TanStack invalidation) остаётся верным независимо от внутреннего
  устройства стора и не создаёт немедленно устаревшего материала; глубокая перестройка
  фронтенд-потребления — предмет T2 (`frontend.md`/`conventions/frontend.md`, не в файловом
  скоупе T1).
- **Дрейф, поправленный на месте в соседних документах** (см. «Реализовано в фазе T1.9» выше за
  подробностями): `conventions/agent.md` (таблица коллабораторов `StreamEventMapper` называла
  `tool_start`/`tool_end` вместо актуального словаря T1.4, `TokenChunkMapper`/`HeartbeatPacer`
  отсутствовали в таблице вовсе); `agent-runtime.md` (`get_history` описывал фильтрацию, не
  typed parts; `stream_mode` был двухканальным со старым списком событий; абзац о субагенте не
  упоминал видимость его шагов через `parent_call_id`). `backend.md` сверен построчно — реального
  расхождения с кодом не найдено (документ намеренно абстрактен на уровне «события графа»),
  правок не потребовалось.
- **Фикс прод-бага «сводка компакции утекает в историю чата» (смежная находка `{T1.5}`, fixer,
  attempt 1).** Проявление: `GET /projects/{id}/chats/{cid}` отдавал ход ассистента двумя
  `text`-частями — первая целиком служебная сводка `[Previous conversation summary]…`, вторая
  настоящий ответ. Первопричина — не в `CheckpointHistory`, а в неверном допущении о позиции:
  `_reduce_context` создавал `summary_msg` **без `id`**, поэтому редьюсер `add_messages` не
  вставлял его в начало, а **дописывал в конец** состояния (узел возвращает
  `{"messages": [*result_prefix, response]}` — сводка ложится прямо перед ответом того хода,
  который её вызвал). Защита «отбрасываем всё до первого `HumanMessage`», описанная в
  `streaming.md` именно как страховка от сводки, промахивала мимо неё всегда, а не в краевом
  случае. Починено пометкой на источнике: `_reduce_context` ставит
  `additional_kwargs={"context_summary": True}`, `CheckpointHistory.history()` отбрасывает
  помеченные `AIMessage` до сегментации по ходам — сводка не попадает в parts, где бы ни лежала.
  Признак выбран флагом, а не префиксом содержимого (`"[Previous conversation summary]"`):
  текст — часть промпта суммаризации и меняется при его правке, тихо ломая матчинг, тогда как
  флаг переживает любую переформулировку. Прецедент в проекте — `security_redacted` из
  `tool_guards.py`, тем же способом (плоский булев ключ в `additional_kwargs`, строковый литерал
  в обеих точках, без общей константы) читаемый в `checkpoint_history.py`. Решение T1.7
  «сообщения до первого `HumanMessage` в parts не попадают» **не отменено** — оно осталось
  отдельным фильтром со своим смыслом (строка ленты без хода пользователя, на который она
  отвечает, бессмысленна); флаг закрывает случай, который эта защита промахивала.
  Дрейф поправлен на месте: `streaming.md` § «История: typed parts» утверждал, что сводка
  оказывается перед первым `HumanMessage`, — абзац переписан по фактическому поведению
  редьюсера. Верификация: `make check` зелёный, `make test` — 849 passed / 1 failed
  (`test_pricing_external.py`, внешний дрейф прайсинга, не наше); поведение снято на
  воспроизведении уровня чекпоинтера — состояние собрано настоящим `add_messages`, без флага
  история даёт два `text`-part, с флагом один. Тест-файлы не тронуты (A6).
- **Фикс «компакция невидима в Langfuse» (находка `{T1.5}`, fixer, attempt 1).** Проявление:
  вызова суммаризатора нет ни в трейсе хода, ни в учёте стоимости — поиск обсерваций с именем
  `context-summarization` по всему проекту давал ноль. Первопричина — цена изоляции токенов:
  трейсинг в проекте едет на `langfuse.langchain.CallbackHandler`, поэтому `"callbacks": []`,
  которым фаза T1.3 отрезала суммаризацию от `stream_mode="messages"`, отрезала её заодно и от
  Langfuse. Компенсировано телеметрией по прецеденту guard-классификатора (`security/observer.py`
  `record_classifier_generation`): `observe_compaction` в `agent/tracing.py` открывает генерацию
  `context-summarization` руками, `_reduce_context` оборачивает ею вызов модели. Отвязка callbacks
  осталась на месте — обсервация вешается на текущий Langfuse-контекст, а не на runnable-цепочку,
  поэтому в поток она ничего не возвращает и вкладывается под спан хода. Наблюдение
  `agent-run`-спана через инъекцию `enabled` тут не подходит: `_reduce_context` — функция уровня
  графа, до которой per-run хендл не доходит, а `get_client()` на неинициализированном клиенте
  безопасно вырождается в no-op (та же схема, что у классификатора).
  По **usage**: `extract_usage(response)` → `normalize_usage_for_langfuse` → `usage_details`, то
  есть ключи совпадают с ценами `configs/pricing.yaml`, и модель суммаризатора
  (`deepseek/deepseek-v4-flash`) там уже есть — вызов попадает в стоимость, а не только в трейс.
  Имя модели берётся у самого объекта модели (`model_name`) с фолбэком на
  `agent_config.summarization.model` — по нему Langfuse матчит прайсинг. Телеметрия fail-safe на
  всех трёх шагах: сбой открытия обсервации логируется и компакция идёт дальше, сбой `update`
  подавляется, падение суммаризатора помечает генерацию `level="ERROR"` и не мешает деградации в
  trim-only. Верификация: `make check` зелёный; `make test` — 849 passed / 1 failed
  (`test_pricing_external.py`, внешний дрейф прайсинга, не наше); тест на утечку токенов
  (`test_compaction_stream.py`) остался зелёным — `callbacks: []` не тронут; аргументы вызова сняты
  подменой Langfuse-клиента на записывающий: `start_as_current_observation(as_type="generation",
  name="context-summarization", model="deepseek/deepseek-v4-flash", model_parameters={"max_tokens":
  500}, metadata={messages_compacted, messages_kept, context_tokens_before})` и `update(output=…,
  usage_details={"input": 120, "output": 30, "total": 150, "output_reasoning": 12})`; на падении
  модели — `update(level="ERROR", status_message="summarization failed")` при сохранённом
  passthrough. Живой стенд не поднимался (провокация компакции требует правки `configs/agent.yaml`).
  Тест-файлы не тронуты (A6).
- **Расщепление флага усечения в истории (решение архитектора, правка поверх фаз).** У вызова
  инструмента усечению подлежат две независимые вещи — аргументы и результат. Живой поток их
  различает (`tool_call_args` и `tool_result` — отдельные события, у каждого свой `truncated`), а
  история схлопывала: `checkpoint_history.py` клал в `ToolCallPart.truncated` дизъюнкцию
  `args_truncated or result_truncated`. Потребитель из истории не мог понять, что именно обрезано,
  и на фронте это уже дало ложь на экране — маркер «обрезано сервером» у зоны результата всплывал
  при усечении одних лишь аргументов. Теперь поле одно на признак:
  `ToolCallPart.args_truncated` / `.result_truncated` (`services/agent_runner.py`), каждое
  заполняется своим значением в `_tool_call_turn_parts`, через `ToolCallPartOut` и `_part_out`
  уходит в API как есть. Обратный перенос («один флаг на оба, но брать `result_truncated`»)
  рассмотрен и отвергнут: он пометил бы аргументы усечёнными при любом длинном результате и
  заглушил бы подпись строки, которую live-лента рисует нормально. Момент выбран сознательно —
  контракт свежий, внешних клиентов нет; позже это было бы ломающее изменение публичного API.
  Хвост на фронте: `MessagePart` (`shared/api/chats.ts`) получил оба поля, а адаптер
  `fromMessageParts` (`shared/lib/agent-feed.ts`) лишился эвристики «обрезанный JSON аргументов не
  парсится» — костыля, который восстанавливал раздельность по косвенному признаку; вместе с ним
  ушёл импорт `parseToolArgs`. Потребители (`ActivityDetails.tsx`, `ActivityRow.tsx`,
  `MessageItem.tsx`) уже читали `argsTruncated`/`resultTruncated` порознь и правки не потребовали.
  Тесты: старые ассерты сохранены, добавлены проверки независимости —
  `test_history_flags_args_and_result_truncation_independently` (два вызова в одном ходе, у одного
  длинные args, у другого длинный результат), фронтовый кейс «не помечает результат усечённым,
  когда обрезаны только аргументы» и смоук `MessageItem` «усечение аргументов не метит зону
  результата» (маркер ровно один). Живой SSE не тронут — там флаги и так раздельные. Документация:
  `streaming.md` § «История: typed parts» (таблица + абзац про независимость) и § «Лимиты» (где
  перечислено, кто несёт флаг). Верификация: `make check` зелёный; `make test` — 914 passed /
  1 failed (`test_pricing_external.py`, внешний дрейф цен); на фронте `npx eslint .` и
  `npx prettier --check .` зелёные, `npx tsc -b --noEmit` — те же 11 ошибок в пяти файлах фазы
  T2.4, ни одной новой; `npx vitest run` — 255 passed / 17 failed при базе 254/17, то есть плюс
  один новый тест и ни одного нового падения.

- **Фикс блокера ревью-A: непроверенный результат инструмента больше не попадает на провод
  (attempt 1).** Что было: событие `tool_result` в контракте v2 несёт `content`, и снималось оно
  с payload'а узла `tools`, тогда как чекпоинт `TOOL_RESULT` (`guard_tool_results`) работал
  шагом позже — на входе в узел `agent`. То есть сырой, ещё не проверенный текст инструмента
  уходил пользователю в ленту, а редакция доставалась только модели; корректирующего события в
  контракте нет и быть не должно (`StreamEventMapper` под ключом `agent` смотрит лишь на
  `AIMessage`). У субагента то же самое было явнее: `_LifecycleEmittingTool` писал `tool_result`
  в `finally` сразу после `ainvoke` — до ReAct-узла, который только потом звал guard. Экспозиция
  новая, внесена этой итерацией: в v1 событие завершения инструмента содержимого не несло вовсе.
  Первопричина по контракту — не «guard поздно вызывается», а **место проверки не совпадало с
  местом, откуда данные уходят наружу**: выход узла `tools` читают сразу два потребителя (провод
  через `StreamEventMapper` и чекпоинтер), а проверка стояла у третьего (следующий узел). Фикс:
  `tool_guards.execute_tools_guarded` — узел `tools` обоих графов стал тонкой обёрткой над
  `ToolNode`, которая исполняет инструменты, прогоняет батч через `TOOL_RESULT` и **возвращает
  уже отредактированные `ToolMessage`**; из `agent_node`/`llm_node` предпроверка снята (иначе
  классификатор звался бы дважды). Побочный выигрыш: сырой результат больше не попадает и в
  чекпоинт — редакция заменяет сообщение, а не приписывается рядом replace-by-id. У субагента
  отчётность разнесена по границе «что уже проверено»: прокси оставляет за собой
  `tool_call_started`/`tool_call_args` и контекстные переменные, а `tool_result` эмитит узел
  `tools` субагентского графа через новый хук `report_tool_results`
  (`_make_tool_result_reporter`, `subagents/runner.py`). Осознанная цена, согласованная с
  архитектором: результат появляется в ленте позже на время работы классификатора. Заодно этим же
  переносом закрыт nit ревью-A о сырой ошибке: на ветке исключения узел отчитывается содержимым
  `ToolMessage`, который `ToolNode(handle_tool_errors=handle_tool_error)` уже санировал, — на
  провод больше не уходит `str(exc)` с путями и параметрами транспорта MCP, пользователь и модель
  видят один и тот же безопасный текст. Документация: `streaming.md` § «`tool_result` /
  `artifact_created`», § «Вложенность субагента», § «Security-чекпоинты» (п. 4);
  `agent-runtime.md` § граф субагента и `security/architecture.md` (таблица чекпоинтов + абзац
  про цикл субагента) — исправлен дрейф «проверки встроены в llm-узел / `agent_node`».
- **Фикс блокера ревью-A: триггер auto-title перевёрнут на позитивный предикат.**
  `_TITLE_GUARD_NEUTRAL_TYPES` перечислял два типа пролога (`stream_started`, `heartbeat`), а
  пролог бывает из трёх: `cancelled` пейсер отдаёт по своему таймеру из любой точки рана
  (`heartbeat.py`), тогда как guard `USER_INPUT` зовётся только после резолва модели,
  инструментов и сборки графа (`runner.py`) — заведомо позже первого тика. Отмена, нажатая пока
  классификатор думает, выставляла `guard_checked = True` и отправляла **непроверенный** ввод в
  title-модель, ломая инвариант feat-002. Первопричина — форма предиката, а не пропущенный
  элемент списка: denylist над множеством, которым мы не управляем, протекает при каждом новом
  типе пролога, и уже протёк один раз. Фикс: `_TITLE_GUARD_CLEARED_TYPES` — перечислены события,
  которые раннер физически не может выдать раньше вердикта (всё, что рождается в графе или в
  более поздних стадиях `_run_turn`); генерацию запускает только попадание в этот набор.
  Промах в новом наборе стоит чату сгенерированного имени, промах в прежнем стоил бы утечки
  непроверенного ввода — цена ошибки развёрнута в безопасную сторону. Цена решения: ран,
  отменённый до первого «доказывающего» события, остаётся без auto-title до следующей отправки.
  Дрейф закрыт тестом `test_title_trigger_classifies_every_runner_event_type`
  (`test_chat_service.py`): набор плюс пролог плюс `security_block` обязаны в точности покрывать
  словарь провода `RUNNER_FORWARDED_TYPES`, поэтому новый тип события нельзя молча не
  классифицировать. Документация: `streaming.md` § «`title_updated`».
- **Тесты фикса и мутационная проверка.** Новых кейсов пять, все закрывают дыру, а не
  подгоняют реализацию: `test_poisoned_tool_result_never_appears_on_the_updates_channel`
  (`tests/agent/test_graph.py` — собирает все `ToolMessage`, прошедшие через updates-канал, то
  есть ровно то, из чего мапперы лепят `content` события),
  `test_a_poisoned_subagent_tool_result_is_reported_redacted`
  (`tests/subagents/test_subagent_lifecycle_events.py`), параметризованный
  `test_send_message_skips_generation_when_cancelled_before_the_verdict` (три раскладки пролога)
  и его зеркало `..._keeps_generation_when_cancelled_after_the_verdict`, плюс дрейф-гейт словаря.
  Пятый кейс — `test_a_tools_domain_event_still_reaches_the_custom_channel`: узел `tools` стал
  обёрткой, поэтому тело инструмента резолвит stream writer на уровень глубже, а резолв там
  ambient (контекстная переменная конфига) — сломайся он, доменные события всех инструментов
  исчезли бы из ленты молча, ничего бы не упало. Мутации (каждая откачена, дерево чистое):
  возврат guard'а в `agent_node` + `guard=None` в узле `tools` → новый кейс красный (на проводе
  `['IGNORE ALL…', '[Tool result blocked…]']` — сырой текст первым, редакция вторым), все
  остальные кейсы файла зелёные, то есть до фикса дыру не ловил никто; отчёт субагента до
  проверки вместо после → красный ровно один новый кейс; возврат denylist `{stream_started,
  heartbeat}` → красные все три раскладки отмены. Четыре существующих теста пришлось поправить —
  они пиновали снятое поведение, не контракт:
  `test_a_failing_subagent_tool_is_reported_as_an_error_result` требовал сырой `str(exc)` в
  событии (то самое, что nit просил убрать, — ассерт перевёрнут на санированный текст), два
  кейса контекстных переменных перечисляли `tool_result` среди событий прямого `ainvoke`
  обёртки (событие переехало на узел, гарантия про сброс контекста не
  ослаблена — она держится на отдельном ассерте про `payload`), а параметризация
  `test_send_message_starts_generation_on_any_non_block_first_event` использовала `tool_start` —
  тип, снятый контрактом v2 и не эмитируемый прод-кодом (заменён на `tool_call_started_event`
  из conftest, чего и требует правило самого conftest'а). Ослабления ассертов ни в одном случае
  нет; правки помечены в отчёте оркестратору как точка, где независимость A6 задета.
  Верификация фикса: `make check` зелёный; `make test` — **922 passed / 1 failed**
  (`test_pricing_external.py`, внешний дрейф цен на `z-ai/glm-5.2`; воспроизводится на чистом
  дереве без правок фикса — не регрессия). Фронт не трогался: скоуп фикса — только
  `backend/**` и `doc/**`.

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
