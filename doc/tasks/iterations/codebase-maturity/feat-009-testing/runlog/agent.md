# Ф3 · S3 — Agent runtime · run-log

Скоуп критпути: модули `backend/app/agent/` (graph, graph_factory, runner,
prompt_builder, error_mapper, stream_events, checkpoint_history, config, tracing).
Тесты пишет независимый автор (не имплементер кода). Харнесс `packages/testing` и
общие conftest — не трогались. Все правки только в `backend/tests/agent/`.

## Возобновление

Прогон возобновлён после перезагрузки. На входе уже лежали (от прежнего прогона):
`conftest.py`, `test_config.py`, `test_error_mapper.py`, `test_prompt_builder.py`
(31 тест, зелёные). Оценил — годны, оставил, достроил вокруг. Точечно починил их
mypy-дрейф (см. ниже), не переписывал.

## Файлы

Достроено в этом прогоне:

- `test_graph.py` — граф на fake-модели: структура нод, happy-path роутинг,
  ReAct-петля, аккумуляция состояния, обработка ошибки tool, ветвление guard,
  HITL (interrupt/resume, update_state as_node), сбой модели.
- `test_graph_factory.py` — шов `model_factory`: инъекция фейка, дефолт = прод
  `create_llm_from_config`, добавление `extra_tools`, путь без суммаризации.
- `test_stream_events.py` — маппер `updates` → `StreamEvent`.
- `test_checkpoint_history.py` — read-side адаптер над чекпойнтером.
- `test_tracing.py` — fail-safe Langfuse-обёртка (disabled + подавление ошибок).
- `test_runner.py` — `LangGraphAgentRunner.stream` (SSE-оркестрация, sociable).
- `conftest.py` — добавлены фикстуры `checkpointer`/`store`/`agent_context` и
  фабрика `build_compiled_graph`; `RecordingPromptProvider` теперь подкласс
  `PromptProvider` (чистый тип там, где ждут конкретный класс).

Прежние (оставлены, точечно дотипизированы): `test_config.py`,
`test_error_mapper.py`, `test_prompt_builder.py`.

## Покрытые поведения / критпути

**graph.py** (через публичный `ainvoke`/`astream`/`aget_state`, не приватные ноды):
- структура: ноды `agent`/`tools` присутствуют;
- happy-path: ответ без tool_calls → роутинг в END (1 AI-сообщение);
- ReAct: tool_call → нода `tools` → возврат в `agent` → финальный ответ; полная
  аккумуляция `Human → AI(tool_call) → Tool → AI(final)`;
- `created_at` штампуется на ответе;
- ошибка tool: падающий инструмент → `ToolMessage(status="error")` с безопасным
  стабом, без утечки внутренностей (путь `/var/secrets` не в content) — через
  прод-хендлер `_handle_tool_error`;
- guard TOOL_CALL_ARG = INJECTION → tool_calls вычищены, `security_redacted=True`,
  роутинг в END (tools не запускаются);
- guard CLEAN → tool_calls проходят, инструмент исполняется;
- guard TOOL_RESULT = INJECTION (селективный стаб: args CLEAN, result INJECTION) →
  `ToolMessage` редактируется в стаб `redacted_tool_result`, `security_redacted`;
- HITL: `interrupt_after=["agent"]` → пауза до `tools` (`snapshot.next == ("tools",)`);
  resume (`ainvoke(None, ...)`) достраивает петлю; `update_state(as_node="agent")`
  засевает сообщения и продолжает с tools (частичный прогон);
- негатив: сбой модели (`RaisingFakeChatModel`) пробрасывается из графа.

**graph_factory.py** (шов C1, через публичный `build()` + прогон графа):
- инъектированный `model_factory` отдаёт фейк → граф отвечает фейком;
- дефолт (без override) маршрутизирует создание модели через
  `create_llm_from_config` (monkeypatch модульного символа → фейк, граф его гоняет);
- `extra_tools` доезжают до графа (per-request инструмент исполняется);
- `summarization=None` → build не конструирует реальный клиент суммаризации.

**stream_events.py**: agent tool_calls → `tool_start` (по одному на вызов);
ToolMessage → `tool_end`; `create_artifact` с artifact → `artifact_created` с
ремапом `type`→`artifact_type`; без artifact → только `tool_end`; неизвестная нода
/ пустой payload → ничего.

**checkpoint_history.py**: `raw_messages` → `[]` на miss и на ошибке бэкенда;
`history` мапит Human/AI, исключает tool-call-ходы, подменяет редактированный
контент, парсит `created_at`; `last_ai_message_id` пропускает tool-call AI;
`latest_redaction` находит редакцию (Tool→TOOL_RESULT, AI→TOOL_CALL_ARG), парсит
detection_layer (валидный/невалидный→None), скан ограничен предыдущим Human.

**tracing.py**: disabled → NoOp-span (trace_id None, методы не падают);
`score`/`finalize_blocked`/`set_output` подавляют ошибку бэкенда; mid-stream-hit
no-op при disabled; trace_id/callback проксируются.

**runner.py** (sociable: реальные ин-процесс соседи — GraphFactory с фейк-моделью,
CheckpointHistory над InMemorySaver, реальный enforcer с guard=None, disabled
tracer): happy-path → `text_chunk`* + `final_output_review_started/complete`, без
error/security_block; сбой модели → один `error` с generic-сообщением (без утечки);
pre-cancel → `error`(cancelled) без `text_chunk`; INJECTION на user_input
(стаб-enforcer) → `security_block`, поток останавливается; `get_history` /
`get_last_ai_message_id` отдают данные после прогона; `cancel` неизвестного треда
→ True.

## Результат `test-scope`

`make test-scope P=backend/tests/agent` → **78 passed** (≈2.0s). Из них 47
добавлено в этом прогоне (31 было). Lint (`ruff check`/`format`) — зелено.
`uv run mypy backend/` по файлам скоупа — **0 ошибок** (общий гейт backend сейчас
красен из-за параллельных чужих скоупов — `tests/personalization/*`; в моих файлах
чисто).

## Баги для Ф5 / заметки

- **Харнесс-гэп (не прод-баг): `fake_chat_model` ломает рекламируемый шов
  GraphFactory.** Замороженный `learnflow_testing.fakes.fake_chat_model` отдаёт
  голый `GenericFakeChatModel`, чей `bind_tools` не реализован
  (`NotImplementedError`). `build_graph`/`GraphFactory.build` вызывают
  `model.bind_tools(tools)` на инъектированной модели, поэтому связка из инструкции
  `GraphFactory(model_factory=model_factory(fake))` не может прогнать граф как есть.
  Обход — локальный адаптер `ToolBindingFakeChatModel` (`bind_tools → self`) в
  `tests/agent/conftest.py`; `packages/testing` не трогал. Для Ф5: добавить
  `bind_tools` в харнес-фейк (или `tool_binding_fake` в `packages/testing`), чтобы
  шов работал без локального адаптера. **Прод-кода это не касается — багом не
  считаю.**
- Прод-багов не нашёл: обработка ошибки tool не течёт, error_mapper не светит
  технические детали, guard-редакция и роутинг ведут себя по контракту.

## Непокрытое и почему

- **Компакция/суммаризация (`_reduce_context` в graph.py)** — целенаправленно не
  покрыта в S3. Ветка срабатывает только при `summarization` ≠ None и большом
  числе токенов, а `GraphFactory.build` конструирует summarization-клиент в обход
  инъектируемого `model_factory` (через реальный `create_summarization_llm`,
  нужен живой клиент). Детерминированно прогнать её через публичный шов нельзя без
  правки прода (новый шов) — это архитектурное решение, вне мандата автора тестов.
  Зафиксировано как кандидат: либо отдельный шов суммаризации в Ф-доработке, либо
  узкий тест `_reduce_context` напрямую (приватная функция — на грани конвенции
  «через публичный интерфейс»). Вынес архитектору, а не угадал.
- **runner: mid-stream / final-output INJECTION-редакция и in-graph inspect** —
  частично. Happy-path и pre-graph блок покрыты; ветки mid/final блока завязаны на
  side-effect-методы enforcer'а (редакция в чекпойнтере + пометка thread blocked),
  которые лезут в БД/репозитории — это территория S2 (`agent/security/*`,
  `runtime_security`), вне моего скоупа. Реакцию раннера на блок (эмит
  `security_block` + остановка) покрыл через стаб-enforcer на pre-graph-чекпойнте;
  дублировать тот же эмит на трёх остальных чекпойнтах смысла нет (одинаковая
  ветка эмита). Сам enforcer покрывает S2.
- **tracing: реальный Langfuse-путь** (enabled=True с живым клиентом) — не
  покрыт намеренно: это внешний эффект, по конвенции — eval/observability, не
  unit. Покрыта fail-safe-семантика (важная для устойчивости стрима).

## Блокеры

Нет. Замороженную инфру не правил; обход bind_tools — локальным адаптером в своём
conftest, эскалация по гэпу — выше для Ф5.
