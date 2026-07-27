# Implementation Plan: feat-001 / трек T1 — Backend: контракт SSE v2, след работы агента

## Контекст

Трек делает серверную половину «видимости работы агента»: перерабатывает поток событий из LangGraph в SSE (контракт v2), добавляет семантический custom-канал и вложенность субагента, собирает персистентный след работы (typed parts) из чекпоинтера, выкладывает машиночитаемый фикстур имён инструментов, закрывает попутные дефекты аудита и переписывает документацию стрима. Фронт (T2) стартует на готовом контракте — форма событий и фикстур имён, которые фиксирует этот трек, и есть его вход.

Источники:

- Запись итерации — [tasklist-dogfooding.md § feat-001 (A)](../../../../../tasklist-dogfooding.md) (P1 live-обратная связь, P3 reasoning-стрим, P3 интерактивность вывода, P2 `security_block`).
- Дизайн — [design-brief.md](../../design-brief.md): § «Контракт SSE v2» (включая абзац «Вложенность субагента»), § «Модель typed parts», § «Frontend» (абзац о реестре подписей — потребитель фикстура), § «Backend: ключевые изменения», § «Конвенции», § «Scope boundaries», § «Партиция треков» (границы T1).
- Аудит «как есть» с file:line — [event-map.md](../../event-map.md) (при конфликте приоритет у design-brief).
- Конвенции — [conventions.md](../../../../../../tech/conventions.md) (§ Тестирование, § Size-чек, § Git → Lifecycle итерации), [conventions/agent.md](../../../../../../tech/conventions/agent.md) (§ Agent Runtime — правило «новая сквозная забота → отдельный коллаборатор»), [conventions/api.md](../../../../../../tech/conventions/api.md).
- Архитектурная дока — [streaming.md](../../../../../../tech/streaming.md) (переписывается в этом треке), [agent-runtime.md](../../../../../../tech/agent-runtime.md), [backend.md](../../../../../../tech/backend.md).

Верифицировано по фактическому окружению (langgraph 1.1.3, langchain-core 1.2.18, langchain-openai 1.1.11) — фиксирую как входные факты реализации:

1. Граф вызывает LLM через `ainvoke`, но токен-стрим реально происходит: `BaseChatModel._should_stream` включает streaming, когда в run_manager есть `_StreamingCallbackHandler` — им и является langgraph'овый `StreamMessagesHandler` при `stream_mode="messages"`. Поэтому reasoning/`tool_call_chunks` действительно доступны в messages-канале.
2. Слияние `AIMessageChunk` конкатенирует `additional_kwargs["reasoning"]`, а `message_chunk_to_message` переносит `additional_kwargs` в итоговый `AIMessage` — на уровне библиотек reasoning до чекпоинта доезжает. Проверка фазы T1.1 остаётся: подтвердить это на фактическом ответе провайдера, а не только на библиотечной механике.
3. `tool_call_chunks` склеиваются по `index`; имя инструмента и `id` известны с первого чанка, `args` дособираются в валидный JSON к концу генерации — ранний `tool_call_started` из первого чанка реализуем.
4. `get_stream_writer()` работает внутри tool'а, исполняемого `ToolNode` основного графа. Вне графового контекста (прямой `tool.ainvoke` в тестах) он **бросает `KeyError: '__pregel_runtime'`** — эмиссия обязана быть через хелпер, безопасный вне рантайма.
5. Custom-события из вложенного скомпилированного графа (граф субагента) при `subgraphs=False` в родительский поток не всплывают; рабочий механизм — writer, захваченный в скоупе tool'а `run_subagent` и переданный вниз явным аргументом. Проверено экспериментально, решение и отклонённая альтернатива `subgraphs=True` зафиксированы в design-brief § «Контракт SSE v2» → «Вложенность субагента» — план на них опирается.
6. Имена built-in MCP-инструментов статически известны из `configs/agent.yaml` (`mcp_servers[*].allowed_tools`), а не только из живого MCP-соединения — фикстур имён (фаза T1.8) собирается детерминированно, без сети и БД.

## Фазы

### T1.1: Проверка reasoning в чекпоинте (+ условный дособор)

**Цель:** подтвердить, что `additional_kwargs["reasoning"]` доезжает до сохранённого в чекпоинт `AIMessage` на streaming-пути, и при отрицательном результате точечно дособрать его в узле графа — без изменения модели.

**Изменения:**
- `backend/tests/agent/` — тест-проба на реальном пути аккумуляции: узел графа с фейковой моделью, отдающей чанки с `reasoning` в `additional_kwargs` (в стиле `ReasoningChatOpenAI._convert_chunk_to_generation_chunk`), прогон через `astream(stream_mode=["messages"])` с чекпоинтером и чтение `channel_values["messages"]`. Проба остаётся в репозитории как регрессионный тест (её последующее уточнение — за `test-author`).
- Дополнительно — ручная проверка на живой reasoning-модели (`make dev` + запрос) и чтение `checkpoint_blobs`: библиотечная механика проверена, поведение конкретного провайдера — нет.
- `backend/app/agent/graph.py` — **только если проверка отрицательная**: дособрать reasoning в `agent_node` после `_invoke_llm` (перед записью `created_at`), не трогая `Message`/`MessageOut`/`ReasoningChatOpenAI`.

**Verification:**
- `make check` и `make test` проходят.
- Явный вывод зафиксирован в отчёте фазы: reasoning в чекпоинте есть / потребовался дособор (какой именно). От этого зависит T1.7 — часть `reasoning` в typed parts.

### T1.2: Каркас контракта SSE v2 в раннере — жизненный цикл потока

**Цель:** ввести транспортный каркас контракта: `stream_started`, `heartbeat`, терминальный `cancelled`, generic `security_block`, отзывчивая отмена и корректная очистка ресурсов рана.

**Изменения:**
- `backend/app/agent/runner.py` — `stream_started` первым yield'ом метода, до резолва модели/MCP/графа и до guard USER_INPUT; `security_block` эмитится с пустым payload (`reason` остаётся в логах/Langfuse — `RuntimeSecurityEnforcer.block_reason` не удаляется); отмена отдаёт `cancelled {}` вместо `error {detail}`; весь setup+стрим оборачивается так, чтобы `_cancel_events`/`_pending_cancels` чистились при любом выходе (ранний return на USER_INPUT-блоке, исключение setup-фазы) — попутная находка №2 аудита.
- Новый коллаборатор heartbeat/pacing (отдельный модуль в `backend/app/agent/`, по правилу conventions/agent.md «новая сквозная забота → отдельный коллаборатор, а не метод в runner»; runner.py уже 361 строка при пороге size-чека 500): обёртка над асинхронным генератором событий, которая при 5 с тишины эмитит `heartbeat {}` и **на том же таймере проверяет `cancel_event`** — отмена перестаёт зависеть от итераций `astream` (попутная находка №3 аудита). Интервал — бизнес-константа, не env.
- Общий хелпер усечения (лимит 2 000 символов + флаг `truncated`) — бизнес-константа в коде; используется дальше в T1.3/T1.4/T1.7.
- `backend/app/services/chat.py` — `cancelled` трактуется как терминальное событие наравне с `error`/`security_block` (пропуск post-hoc и `done`).
- `backend/app/api/routes/messages.py` — сверить транспортный fallback `error {"Stream failed"}` с `error_messages.yaml` (неточность №4 аудита; правка либо в коде, либо фиксация факта при переписывании `streaming.md` в T1.9).

**Verification:**
- `make check`, `make test` проходят.
- Критерии design-brief § «Контракт SSE v2»: `stream_started` уходит до setup-фазы; `heartbeat` приходит каждые 5 с в любой тишине (setup, исполнение инструмента, review); отмена — отдельным `cancelled`, не `error`; `security_block` без полей `reason`/`checkpoint`/`detection_layer`.
- Ручная проверка отзывчивости отмены во время долгого tool-вызова (`run_subagent`): `POST /cancel` завершает поток, не дожидаясь конца инструмента.
- После рана (успех, ошибка, блок на USER_INPUT, отмена) `_cancel_events` пуст.
- Обязательные кейсы из design-brief § «Тестовый scope (минимум)», относящиеся к фазе (вход для `test-author`, сами тесты пишет он): heartbeat приходит в тишине с заданным интервалом и не приходит, пока идут другие события; отмена даёт терминальный `cancelled`, а не `error`; `cancelled` прерывает поток без `done`.

### T1.3: Token-канал — reasoning_chunk, ранний tool_call_started/tool_call_args, изоляция суммаризатора

**Цель:** переработать фильтр messages-стрима так, чтобы reasoning и tool_call_chunks доходили до SSE, а посторонние генерации (суммаризатор) в него не попадали.

**Изменения:**
- `backend/app/agent/runner.py` + маппер token-канала (расширение `stream_events.py` или соседний модуль — по размеру): вместо одного `if` с «`AIMessageChunk` со строковым непустым content» — разбор чанка по трём веткам: текст → `text_chunk`, `additional_kwargs["reasoning"]` → `reasoning_chunk`, `tool_call_chunks` → `tool_call_started {call_id, tool}` на первом чанке вызова (дедуп по `call_id`/`index`) и `tool_call_args {call_id, args, truncated}` по завершении сборки JSON аргументов, до исполнения.
- Границы, вытекающие из scope boundaries («изменение guard-политик — вне scope»): reasoning-токены **не** попадают в `full_response`, не участвуют в canary/mid-stream/final-output проверках и не влияют на `last_message_id`. Фильтр по `SUBAGENT_TAG` сохраняется для token-канала. Это **осознанное решение архитектора** (стримить reasoning без guard-проверок: LLM-защита уходит под kill-switch chore-001, проприетарные reasoning-модели отдают суммированные рассуждения, а не сырые); долг записан в [harvest-proposals.md](../../harvest-proposals.md) на случай подъёма защиты под другой продакшн — на code review вопрос заново не поднимается.
- `backend/app/agent/graph.py` — вызов суммаризатора (`summarization_model.ainvoke([prompt, *old_messages])`) получает изолирующий `RunnableConfig` по образцу guard-классификатора (`security/classifier.py:93-99`: `callbacks: []` + собственные `tags`/`run_name`), чтобы токены компакции не текли в пользовательский стрим — попутная находка №1 аудита.
- Состояние сборки вызовов (какие `call_id` уже анонсированы, накопленные фрагменты args) — **per-run**, не на общем инстансе маппера, живущем в конструкторе раннера: иначе параллельные стримы смешиваются (жёсткое правило «никакого module-level/shared состояния»). Инстанс маппера создаётся внутри `stream()`; для тестов — инжектируемая фабрика.

**Verification:**
- `make check`, `make test` проходят, включая обновлённый `backend/tests/subagents/test_stream_isolation.py`.
- Критерии design-brief: `tool_call_started` появляется в момент первого `tool_call_chunk` (до завершения узла `agent`), `tool_call_args` — после дописывания JSON и до исполнения, `args` усечены до 2 000 символов с флагом `truncated`; `reasoning_chunk` идёт live.
- Токены суммаризатора и субагента в пользовательский поток не попадают (проверяется на срабатывании компакции — порог `context.max_tokens * compaction_threshold_ratio`).

### T1.4: Updates-канал — tool_result, tool_call_cancelled, artifact_created по атрибуту

**Цель:** привести маппер updates к контракту v2: результат исполнения со статусом, отмена срезанного guard'ом вызова, артефакт — по наличию `ToolMessage.artifact`.

**Изменения:**
- `backend/app/agent/stream_events.py` — удаление `tool_start`/`tool_end`; `tool_result {call_id, tool, status, content, truncated}` из `ToolMessage` (`status: success | error` — берётся из `ToolMessage.status`, content усечён общим хелпером); `artifact_created` эмитится по `msg.artifact is not None` вместо захардкоженного whitelist имён (`create_artifact`, `generate_image`); дедупликация с token-каналом — стартовые события в updates больше не порождаются.
- `tool_call_cancelled {call_id}`: признак среза — **`AIMessage` (именно `AIMessage`, не `ToolMessage`) с `additional_kwargs["security_redacted"]` и пустым `tool_calls`** (`guard_tool_call_args`, `tool_guards.py:154-171`). Сравнивать `original_detection_layer` со строкой `"tool_call_arg"` **нельзя**: поле хранит `DetectionLayer` (`canary` / `unicode` / `fragment` / `paired` / `llm_classifier` / `graceful_degradation`), а `"tool_call_arg"` попадает туда только fallback'ом при `detection_layer is None` — условие оказалось бы почти всегда ложным. Тот же флаг `security_redacted` ставит `guard_tool_results` на `ToolMessage`, поэтому проверка типа сообщения обязательна. События эмитятся для всех `call_id`, анонсированных token-каналом и не получивших `tool_result`, — требует того же per-run состояния, что и T1.3.
- `backend/tests/agent/test_stream_events.py`, `backend/tests/image_generation/test_stream_events_generate_image.py` — приводятся к новому словарю событий (тесты словаря, не новые кейсы; полноценный набор пишет `test-author`).

**Verification:**
- `make check`, `make test` проходят.
- Критерии design-brief: ошибка инструмента отличима от успеха (`status`); `artifact_created` срабатывает на любом artifact-producing инструменте независимо от имени; срезанный guard'ом вызов даёт `tool_call_cancelled`, а не «висящую» активную строку; событий `tool_start`/`tool_end` в потоке больше нет.

### T1.5: Custom-канал — семантические agent_event из инструментов

**Цель:** включить `stream_mode="custom"` и научить наши инструменты сообщать о доменном действии.

**Изменения:**
- `backend/app/agent/runner.py` — `stream_mode=["messages","updates","custom"]`. Конверт custom-канала несёт поле типа события: раннер маппит в `agent_event {kind, payload, parent_call_id?}` только доменные kind'ы (`sphere_write`, `memory_write`, `skill_context_write`, `compaction`), а lifecycle-типы, которые шлёт через тот же writer обёртка субагента (`tool_call_started` / `tool_call_args` / `tool_result`, T1.6), пробрасывает как есть — заворачивать их в `agent_event` нельзя, на проводе должны быть те же типы, что у основного агента. Payload проходит усечение общим хелпером.
- Хелпер эмиссии в `backend/app/agent/` — **три источника writer'а в порядке приоритета**: (1) явно переданный writer из контекстной переменной, которую выставляет обёртка субагента (T1.6), (2) `get_stream_writer()`, (3) no-op вне графового рантайма. Первый пункт обязателен и не откладывается на T1.6: пулы субагентов собираются из тех же internal-инструментов (`backend/app/main.py:496` — `subagent_tool_pool = internal_tools + mcp_tools`), поэтому KS/memory/skill-context исполняются и внутри графа субагента, откуда `get_stream_writer()` в родительский поток не пишет; без явного writer'а «безопасный» хелпер молча проглотит эти события. Третий пункт нужен потому, что вне графа вызов бросает `KeyError '__pregel_runtime'` и сломал бы существующие тесты, вызывающие tools через `tool.ainvoke`.
- `backend/app/agent/tools/knowledge_sphere.py`, `user_memory.py`, `skill_context.py` — эмиссия `sphere_write` / `memory_write` / `skill_context_write` на пишущих операциях с минимальным payload (то, что нужно подписи на фронте: раздел/ключ/скилл).
- `backend/app/agent/graph.py` — эмиссия `compaction` в момент фактического сжатия контекста (`_reduce_context` вернул ops_prefix).

**Verification:**
- `make check`, `make test` проходят (включая существующие тесты инструментов, вызывающие их вне графа).
- Критерии design-brief § «Контракт SSE v2»: `agent_event` доезжает до SSE для всех четырёх kind'ов; в чекпоинт эти события не пишутся (осознанная граница — live-only).
- Хелпер отрабатывает во всех трёх режимах: в основном графе (через `get_stream_writer()`), при явно переданном writer'е (проверяется на T1.6) и вне графа (no-op, существующие тесты инструментов зелёные).

### T1.6: Вложенность субагента — parent_call_id для его инструментов

**Цель:** показать шаги субагента в живой ленте теми же событиями, что и шаги основного агента, с привязкой к родительскому вызову.

**Изменения:**
- `backend/app/agent/tools/subagents.py` — в тот момент, когда `run_subagent` исполняется (скоуп основного графа, writer доступен), захватывается stream writer и `tool_call_id` собственного вызова (инъекция `ToolRuntime`), и передаётся вниз в `SubagentRunner.run`.
- `backend/app/agent/subagents/runner.py` — обёртка вокруг резолва `resolved_tools`. Каждый обёрнутый инструмент даёт **все четыре события брифа** с `parent_call_id` родительского `run_subagent`:
  - `tool_call_started {call_id, tool, parent_call_id}` — перед исполнением; `call_id` берётся из вызова субагентского инструмента,
  - `tool_call_args {call_id, args, truncated, parent_call_id}` — там же: при обёртке исполнения аргументы уже известны целиком (в отличие от основного агента, где они собираются из token-чанков), без них зона «ВЫЗОВ» вложенной строки останется пустой,
  - `tool_result {call_id, tool, status, content, truncated, parent_call_id}` — после исполнения, `status` по факту исключения/успеха,
  - `agent_event {kind, payload, parent_call_id}` — от самих инструментов (KS/memory/skill-context доступны субагенту через общий пул): обёртка выставляет контекстную переменную с writer'ом и `parent_call_id` на время исполнения инструмента, хелпер из T1.5 её подхватывает. Переменная **устанавливается и сбрасывается по токену в `finally`** (`contextvars.ContextVar.set()` → `reset(token)`), иначе значение протечёт на следующие инструменты того же таска и `parent_call_id` прилипнет к чужим событиям. Без явного writer'а субагентные `agent_event` теряются молча.
- `SubagentRunner` остаётся на `ainvoke`; отдельных типов событий для вложенности нет.
- Механизм эмиссии — **явно переданный writer, а не `get_stream_writer()` внутри графа субагента** (design-brief § «Вложенность субагента»: `subgraphs=True` отклонён, `astream` сохраняет форму кортежа `(mode, data)` и изоляцию по `SUBAGENT_TAG`).
- Вход (task) и ответ субагента отдельным каналом не эмитятся — это `args`/`content` самого вызова `run_subagent`, уже покрытые T1.3/T1.4.

**Verification:**
- `make check`, `make test` проходят; `backend/tests/subagents/test_stream_isolation.py` дополнен фактом «субагентные custom-события проходят, его LLM-токены — нет».
- Критерий design-brief § «Вложенность субагента»: все четыре типа событий (`tool_call_started` / `tool_call_args` / `tool_result` / `agent_event`) доезжают до SSE с корректным `parent_call_id`; токены субагента в чат по-прежнему не попадают.
- Проверка на сценарии, где субагент вызывает KS/memory-инструмент: `agent_event` виден в потоке (не теряется молча) и несёт `parent_call_id`.

### T1.7: История — typed parts из чекпоинтера

**Цель:** отдать в API упорядоченный след работы агента (`reasoning` | `text` | `tool_call`), собранный из чекпоинта, без новой персистентности и миграций.

**Изменения:**
- `backend/app/agent/checkpoint_history.py` — снятие фильтров «без `ToolMessage`, без `AIMessage` с `tool_calls`» и **группировка сообщений в ход**: буквальное снятие фильтров дало бы несколько `MessageOut` на один ход агента, тогда как бриф § «Целевой UX» требует одно сообщение ассистента = последовательность parts. Правило сборки:
  - границы хода — от `HumanMessage` до следующего `HumanMessage`; всё между ними (`AIMessage` с `tool_calls`, `ToolMessage`, финальный `AIMessage`) складывается в один ассистентский `Message`;
  - `id` и `created_at` берутся у **финального `AIMessage` без `tool_calls`** — по этому `id` в `routes/chats.py:86-95` резолвятся `trace_id`, `feedback_score` и `artifacts`, и он же приходит в `done.message_id` (инвариант сохраняется, а не вводится заново);
  - `content` остаётся плоским текстом этого же финального сообщения (обратная совместимость и degraded-случай);
  - ход без финального `AIMessage` (оборвался на tool-вызове) отдаётся с `id` последнего доступного `AIMessage` — parts показывают, докуда агент дошёл;
  - сообщения, лежащие **до первого `HumanMessage`** треда, в parts не попадают — осознанно. Это меняет видимое поведение: после компакции `graph.py:75-83` кладёт в чекпоинт `summary_msg = AIMessage(...)` без `id`, стоящий перед самым ранним оставшимся `HumanMessage`, и сегодня `history()` отдаёт его отдельным сообщением ассистента. Сводка предыдущего разговора — служебное содержимое контекста, а не ход агента; в ленте ей места нет.
- Состав parts: `reasoning {content}` из `additional_kwargs["reasoning"]` (результат T1.1), `text {content}` из `AIMessage.content`, `tool_call {call_id, tool, args, status, result_preview, truncated}` из `AIMessage.tool_calls` + парного по `tool_call_id` `ToolMessage`. Общий хелпер усечения (2 000 символов, T1.2) применяется и к `args`, и к `result_preview` — бриф § «Лимиты» требует усечения в SSE **и** API; `truncated` поднимается, если усечено хотя бы одно из полей. Порядок parts — порядок сообщений в треде.
- `backend/app/services/agent_runner.py` — `Message` получает `parts`; `content`, `redacted`, `created_at` остаются как есть (совместимость).
- `backend/app/api/schemas/chats.py` — `MessageOut.parts` (дискриминированный по `type` список), остальные поля без изменений.
- `backend/app/api/routes/chats.py:86` — проброс `parts` в `MessageOut`.
- Инварианты, вытекающие из брифа: `redacted`-сообщения отдают parts согласованно с существующей политикой редакции; `last_ai_message_id` продолжает игнорировать `AIMessage` с `tool_calls` (иначе `done.message_id` перестанет указывать на финальный ответ); субагентные шаги и `agent_event` в parts не попадают (live-only).

**Verification:**
- `make check`, `make test` проходят (включая `backend/tests/agent/test_checkpoint_history.py`).
- Критерии design-brief § «Модель typed parts»: перезагрузка чата показывает те же действия, что были в live (кроме осознанно исключённых — вложенной хронологии субагента и факта компакции); миграций нет; `content` продолжает возвращаться.
- Ход с несколькими tool-вызовами отдаётся **одним** `MessageOut` с последовательностью parts, а не набором сообщений; `trace_id` / `feedback_score` / `artifacts` продолжают резолвиться (тот же `id`).
- Обязательные кейсы из design-brief § «Тестовый scope (минимум)», относящиеся к фазе (вход для `test-author`): сборка parts из чекпоинта — ход «reasoning → tool_call → text», парность `AIMessage.tool_calls` ↔ `ToolMessage` по `tool_call_id`, `status=error` у упавшего инструмента, усечение `args`/`result_preview` с флагом `truncated`, поведение на `redacted`-сообщении, ход без финального `AIMessage`.

### T1.8: Фикстур имён инструментов — контракт для реестра подписей T2

**Цель:** выложить в репозиторий машиночитаемый список имён built-in/internal инструментов, сгенерированный из того же реестра, из которого граф реально получает инструменты, и защитить его от расхождения бэкенд-гейтом.

**Изменения:**
- `backend/app/agent/tools/` — функция сборки имён (`build_internal_tools` / экспорт имён) как **единственный** источник: возвращает имена internal-инструментов (`ks_tools`, `user_memory_tools`, skill-context, `load_skill`, `create_artifact`, `generate_image`, `run_subagent`) плюс built-in MCP-имена из `configs/agent.yaml` → `mcp_servers[*].allowed_tools` (все объявленные серверы, независимо от `enabled`: флаг меняется по окружениям, а подпись на фронте нужна в любом). Детерминированно, без сети и БД.
- `backend/app/main.py` — сборка `internal_tools` идёт через эту же функцию, а не собственным списком (файл входит в файловый скоуп T1 по § «Партиция треков»). Правка минимальная и обязательная: фикстур, собранный из параллельного списка, разъедется с рантаймом.
- Генератор — тонкий CLI поверх этой функции (`scripts/`, входит в скоуп T1; по образцу существующего `scripts/langfuse_security_experiment.py`): пишет отсортированный JSON.
- Фикстур — `backend/contracts/agent-tool-names.json`: под `backend/`, потому что владелец и источник — бэкенд, а T2 его только читает (относительным путём из vitest); новый top-level-каталог не заводится, `packages/` зарезервирован под импортируемые библиотеки (conventions.md § Раскладка workspace). Формат — отсортированный массив имён + пометка происхождения (`internal` / `builtin_mcp`), чтобы фронт-тест мог требовать подпись для обеих групп; пользовательские MCP-инструменты в фикстур **не** попадают (резолвятся в рантайме, по брифу рендерятся сырым именем с пометкой источника).
- Drift-гейт — детерминированная проверка «закоммиченный фикстур == сгенерированный на текущем коде» в `backend/tests/agent/`: pytest-форма выбрана как не требующая новой цели Makefile и уже покрытая CI (`make test`); падение указывает на команду перегенерации.

**Verification:**
- `make check`, `make test` проходят; drift-гейт краснеет, если добавить инструмент в реестр и не перегенерировать фикстур (проверяется вручную на временной правке).
- Фикстур содержит все имена, которые агент реально получает при старте (сверка с логом `main.py` о собранных инструментах на живом запуске), и не содержит пользовательских MCP-имён.
- Путь и формат зафиксированы в плане и в чек-листе конвенций (T1.9) — T2 может опереться на них, не читая код бэкенда.

### T1.9: Документация — streaming.md и чек-лист конвенций

**Цель:** привести доку в соответствие реализованному контракту и зафиксировать конвенцию «добавляешь инструмент агенту».

**Изменения:**
- `doc/tech/streaming.md` — переписывается целиком: состав событий v2 и их источники, терминальные события (`done` / `error` / `security_block` / `cancelled`), heartbeat и таймаут от него, лимиты усечения, forward-compat (неизвестные типы игнорируются), вложенность через `parent_call_id`, обновлённые диаграммы lifecycle и отмены, актуальное описание изоляции субагента и суммаризатора. Закрываются четыре неточности аудита: `security_block` может прийти **после** `final_output_review_complete`; `final_output_review_*` не эмитятся на чисто tool-ходе без текста; pre-stream гейт 403 `require_unblocked_thread`; транспортный fallback `error {"Stream failed"}` мимо `error_messages.yaml`.
- `doc/tech/conventions/agent.md` — чек-лист «добавляешь инструмент агенту» (пункты 1–4 design-brief § «Конвенции»), плюс правило эмиссии `agent_event` через безопасный хелпер (прямой `get_stream_writer()` падает вне графового рантайма). Пункт 1 получает машинную опору: инструмент добавляется в общий реестр → перегенерируется фикстур `backend/contracts/agent-tool-names.json` (иначе краснеет backend drift-гейт) → подпись заводится на фронте (иначе краснеет тест полноты реестра T2). Команда перегенерации указывается явно.
- Дрейф, замеченный попутно, — правится на месте: `agent-runtime.md` и `backend.md` в частях, описывающих поток событий / коллабораторов раннера, если реализация их расходит.

**Verification:**
- `make check` проходит (документные проверки/ссылки).
- Ни одно утверждение `streaming.md` не расходится с кодом: состав событий и payload'ы сверены с реализованными мапперами; переписанные диаграммы верифицированы по коду (conventions.md § Mermaid Styling), рендер проверен на тёмной теме.
- Чек-лист конвенций содержит все четыре пункта брифа; пункт 1 (реестр подписей фронта) сформулирован так, что T2 может его исполнить.

## Cross-cutting

После всех фаз трека:

- `make check` и `make test` зелёные; ручных миграций нет (persistence в треке не появляется — проверить, что `alembic` не тронут).
- Полный проход по составу событий design-brief § «Контракт SSE v2»: каждое событие таблицы либо эмитится, либо явно помечено как неприменимое в текущей конфигурации (`final_output_review_*` при выключенной LLM-защите).
- Немые зоны из event-map § «Немые зоны» закрыты: открытие потока (`stream_started` + `heartbeat`), исполнение инструмента (`heartbeat` + ранний старт), пауза перед `done` (`heartbeat` + review-события).
- Попутные фиксы аудита закрыты и упомянуты в отчёте: изоляция суммаризатора (№1), утечка `_cancel_events` (№2), отзывчивость отмены во время долгого инструмента (№3), неточности `streaming.md` (№4).
- Контракт стабилен и описан — T2 может стартовать: `streaming.md` служит для фронта единственным источником формы событий, `backend/contracts/agent-tool-names.json` — единственным источником имён инструментов.
- Scope boundaries соблюдены: rich-рендер, вложенная хронология субагента в истории, персистентность рана при дисконнекте, `title_updated`, изменения guard-политик и Langfuse-трейсинга — не трогаются.

## Open Questions

Нет открытых вопросов. Три вопроса первой редакции плана разрешены архитектором: `routes/chats.py` входит в скоуп T1 (партиция брифа дополнена); механизм вложенности субагента — явно переданный writer, `subgraphs=True` отклонён (зафиксировано в брифе § «Вложенность субагента»); имена инструментов для реестра T2 — машиночитаемый фикстур, генерируемый бэкендом (фаза T1.8).
