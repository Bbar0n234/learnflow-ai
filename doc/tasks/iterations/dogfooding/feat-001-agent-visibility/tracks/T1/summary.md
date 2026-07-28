# Summary: feat-001 / трек T1 — Backend: контракт SSE v2, след работы агента

## TL;DR

Трек на текущий момент закрывает три фазы. **T1.1** (диагностика) подтвердила, что
`additional_kwargs["reasoning"]` доезжает до сохранённого в чекпоинт `AIMessage` на реальном
streaming-пути проекта без изменений `graph.py`. **T1.2** ввела транспортный каркас SSE v2 в
`runner.py`: `stream_started` до setup-фазы; коллаборатор `HeartbeatPacer` (heartbeat каждые
5 с + проверка `cancel_event` на том же таймере, отмена отзывчива и во время долгого
tool-вызова); терминальный `cancelled {}` вместо `error`; generic `security_block {}`;
устранена утечка `_cancel_events`. **T1.3** переработала token-канал: новый `TokenChunkMapper`
(`stream_events.py`, свежий экземпляр на каждый `stream()` — инжектируемая фабрика в
конструкторе раннера, а не shared-state) разбирает каждый сырой `AIMessageChunk` на
`reasoning_chunk` / `text_chunk` / раннюю пару `tool_call_started` + `tool_call_args` (дедуп по
`call_id`/`index`, JSON args собирается по фрагментам `tool_call_chunks`, эмиссия — по
достижении валидного JSON, до исполнения, усечение общим хелпером из T1.2). Guard-проверки
(canary/mid-stream) остаются только на `text_chunk` — reasoning и tool-call вне их скоупа,
осознанная граница архитектора. Попутно изолирован вызов суммаризатора
(`graph.py:_reduce_context`) через `RunnableConfig{callbacks: [], tags, run_name}` по образцу
guard-классификатора — токены компакции больше не текут в пользовательский `text_chunk`
(попутная находка №1 аудита закрыта).

`make check` зелёный на всех трёх фазах. `make test` в среде агента (сломанный проброс портов
Docker — см. ниже): **526 passed, 1 failed, 228 errors** (755 тестов всего) — тот же итог по
составу и общему числу тестов, что и в T1.2 (527 без-Postgres тестов = 526 зелёных + то же
известное внешнее падение прайсинга; ~228 падений на testcontainers-Postgres), т.е. фаза T1.3
не добавила ни одной новой красной строки и не поменяла состав падений. Явно прогнаны и
зелёные: `tests/agent`, `tests/chat`
(non-DB часть), `tests/subagents/test_stream_isolation.py`, `tests/image_generation`
(non-DB часть), `tests/agent/test_graph.py`/`test_graph_factory.py` (суммаризатор-фейки с новым
`config=` аргументом `ainvoke`). DB-интеграционный слой (~228 тестов, включая
`chat/test_message_stream.py`) по-прежнему не верифицируется в этой среде — тот же
инфраструктурный конфликт (testcontainers/Ryuk), что и в T1.2, не кодовый вопрос. Отдельно —
предсуществующее внешнее падение `test_pricing_external.py` (не связано ни с одной из фаз).
Ручная проверка на живой reasoning-модели (T1.1) не выполнена — нет сетевого доступа в среде
агента; отмечена как ручной кейс для архитектора.

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
