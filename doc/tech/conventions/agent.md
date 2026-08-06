# Конвенции: Agent

Проектные решения по agent runtime, скиллам, reasoning-моделям и именованию промптов. Ядро — [conventions.md](../conventions.md).

## Agent Runtime

Проектные решения по структуре agent runtime (`backend/app/agent/`). База — skill `langgraph-patterns`; здесь только выбранные развилки.

**Топология графа.** ReAct-цикл строится на pre-defined edges (`add_conditional_edges("agent", tools_condition)` + `add_edge("tools", "agent")`), не на Command API: топология известна на этапе компиляции, динамический routing не нужен. Checkpointer и Store (`AsyncPostgresSaver`/`AsyncPostgresStore`) — shared, создаются один раз в `lifespan` через `async with`; per-request пересобирается только граф (`GraphFactory`).

**Runner — оркестратор, не God Object.** `LangGraphAgentRunner` реализует контракт `AgentRunner` (stream / get_history / get_last_ai_message_id / cancel) и только оркеструет: стримит, принимает решения, эмитит SSE. Сквозные заботы вынесены в инжектируемых коллабораторов, у каждого своя причина меняться:

| Коллаборатор | Ответственность |
|--------------|-----------------|
| `RuntimeSecurityEnforcer` | Четыре runtime-чекпоинта guard'а (user input / mid-stream / final output / in-graph inspection) + редакция сообщений + пометка thread'а blocked. Каждый `check_*` делает свои сайд-эффекты и возвращает `SecurityOutcome | None`; runner по исходу решает `yield security_block`. Живёт и с `guard=None` (`LLM_DEFENSE_ENABLED=false`) — `check_*` в этом состоянии безопасные no-op'ы; публичное read-only свойство `active` (`guard is not None`) — единственный признак, по которому runner решает, эмитить ли `final_output_review_*` (→ [streaming.md](../streaming.md)). Runner не читает `Settings` и не заглядывает в приватные поля enforcer'а. |
| `AgentRunTracer` / `AgentRunSpan` | Langfuse-спан рана: score, finalize-on-block, output, mid-stream observation. Fail-safe (ошибки Langfuse подавляются). |
| `CheckpointHistory` | Единственное место, знающее форму `channel_values["messages"]`: чтение, маппинг в typed-parts `Message`, поиск редакций. |
| `TokenChunkMapper` | `stream_mode="messages"` chunk → `text_chunk` / `reasoning_chunk` / `tool_call_started` / `tool_call_args`. Per-run (фабрика в конструкторе раннера, не shared-инстанс) — накапливает состояние сборки tool-call args по `call_id`. |
| `StreamEventMapper` | `stream_mode="updates"` → `tool_call_cancelled`. Тоже per-run — ведёт список анонсированных, но ещё не разрешённых `call_id` (`tool_result` / `artifact_created` эмитит сам узел `tools`, повызовно, в custom-канал). |
| `HeartbeatPacer` | `heartbeat {}` на 5 с тишины в любой точке рана + проверка `cancel_event` на том же таймере (отмена остаётся отзывчивой во время долгого tool-вызова, не только между итерациями `astream`). |

Полный контракт SSE-событий, lifecycle и security-чекпоинты — [streaming.md](../streaming.md).

Принцип: новая сквозная забота в runtime → отдельный коллаборатор за портом, а не ещё один метод в runner.

**Инъектируемый `ToolRuntime`-параметр tool'а: точная аннотация + модульный sentinel.** Параметр tool'а, инъектируемый runtime'ом (`runtime: ToolRuntime`), аннотируется **ровно** типом `ToolRuntime` — не `ToolRuntime | None`: framework распознаёт инъекцию (и исключает параметр из LLM-схемы tool'а) по точному типу аннотации, а `Union`/`Optional` ломает и распознавание, и генерацию JSON Schema (`PydanticInvalidForJsonSchema`). Обязательный параметр без default при этом ломает прямой `tool.ainvoke({...})` без runtime (`ValidationError: Field required`) — тесты и ручные прогоны. Решение: default через модульную typed-константу `_NO_RUNTIME = cast("ToolRuntime", None)` (не инлайн в сигнатуре — ruff B008) и явная ветка `if runtime is None` в теле. Прецеденты: `app/agent/tools/user_memory.py`, `app/agent/tools/skill_context.py`.

**Слоистость security: движок vs enforcement.** Security-движок — `app/agent/security/` (детекторы, LLM-классификатор, `SecurityGuard`, типы): самодостаточный пакет, знающий, *что такое* инъекция. Точки применения (enforcement-адаптеры) живут уровнем выше, в `app/agent/`, рядом с кодом, который они защищают: `runtime_security.py` (`RuntimeSecurityEnforcer`) — stream-чекпоинты runner'а, `tool_guards.py` — in-graph чекпоинты `TOOL_RESULT`/`TOOL_CALL_ARG`, переиспользуемые основным графом и графами субагентов. Адаптеры знают, *где и как* вызвать guard и что делать с вердиктом (redact / срез `tool_calls`); в `security/` они не входят — движок не зависит от графов и runner'а.

**Точка проверки содержимого — узел, чей выход читают потребители.** Guard содержимого стоит в том узле, чей выход уходит наружу (провод событий, чекпоинтер, API), а не на входе следующего узла: выход узла читают сразу несколько потребителей, и проверка «шагом позже» правит картину только для модели, оставляя сырой текст на проводе и в чекпоинте. Поэтому `execute_tools_guarded` проверяет результат внутри узла `tools` (в обоих графах) и возвращает уже отредактированные сообщения, а событие результата субагентского вызова эмитит узел инструментов вложенного графа, не прокси-инструмент — в прокси текст ещё не прошёл ни guard, ни санитайзер ошибок `ToolNode`.

### Добавляешь инструмент агенту

Чек-лист, обязательный для любого нового tool'а (internal или built-in MCP):

1. **Подпись фронта.** Имя инструмента получает запись в реестре подписей фронта (`shared/config/agent-tools.ts`; состав записи — [frontend.md § «Добавляешь инструмент агенту»](frontend.md#добавляешь-инструмент-агенту)). Полноту сторожит машинная цепочка, не память разработчика: инструмент добавляется в реестр бэкенда (`app.agent.tools.registry`) → перегенерируется фикстур `backend/contracts/agent-tool-names.json` (`PYTHONPATH=backend uv run --package learnflow-backend python scripts/generate_tool_names_fixture.py`, из корня репозитория) → пропуск регенерации красит backend drift-гейт (`backend/tests/agent/test_tool_names_fixture.py`) → отсутствие подписи на фронте красит фронтовый тест полноты реестра. Пропустить любое звено — увидеть красный CI, не тихий пробел в UI.
2. **Артефакт — по атрибуту, не по имени.** Artifact-producing инструмент возвращает `response_format="content_and_artifact"`; событие `artifact_created` эмитится по наличию `ToolMessage.artifact`, не по whitelist имён — новый инструмент не требует правки маппера.
3. **Доменное действие — через `agent_events.emit_agent_event`, не напрямую.** Инструмент, совершающий доменную запись (Knowledge Sphere, память, skill context), сообщает об этом через хелпер `app.agent.agent_events.emit_agent_event(kind, payload)`, не через голый `get_stream_writer()`: последний бросает `KeyError`/`RuntimeError` вне графового рантайма (юнит-тесты, вызывающие tool через `tool.ainvoke(...)` напрямую) и молча пишет в никуда, если тул исполняется внутри графа субагента (тот работает через `ainvoke`, его собственный custom-стрим никто не читает). Хелпер разруливает оба случая и приписывает `parent_call_id`, если вызов идёт из-под субагента.
4. **UI-содержимое результата — raw-разворот, не rich-рендер.** Результат инструмента показывается в развороте сырым текстом с усечением (2000 символов + `truncated`, `app.agent.text_limits.truncate`) — типизированный rich-рендер по видам результата не вводится этим чек-листом.

Полный контракт событий, которые видит фронт (`tool_call_started` / `tool_call_args` / `tool_result` / `agent_event` / …), — [streaming.md](../streaming.md).

## Skills

**Frontmatter `description` — стиль Claude Code.** Описание скилла в `SKILL.md` пишется как «назначение + триггеры»: одно-два предложения о том, что скилл делает, затем «Используй когда: <триггеры через запятую>». Формат намеренно совпадает с конвенцией skills Claude Code — скилл читаем любым агентом экосистемы без адаптации, а семантика срабатывания одинакова (system prompt продукта: «Load a skill when the user's task matches its description»). Description попадает в Skills Index — в system message каждого запроса — поэтому держится компактным; переносы строк нормализуются при сборке индекса (`scan_skills_index`).

## Reasoning LLMs

Часть моделей (OpenRouter-совместимые) отдают цепочку рассуждений в нестандартном поле `reasoning`. Чтобы извлекать её в `AIMessage.additional_kwargs["reasoning"]` — используется `ReasoningChatOpenAI` из `app/infra/llm.py`.

**Все модели проекта создаются как `ReasoningChatOpenAI` — безусловно.** Это безопасный надкласс `ChatOpenAI`: извлечение reasoning — no-op, когда провайдер не вернул поле `reasoning`. Поэтому ветки «`ReasoningChatOpenAI` или `ChatOpenAI` по флагу» нет — все фабрики (`create_llm_from_config` для агента, `create_summarization_llm` для summarizer, `create_guard_llm` для security guard) идут через единый приватный билдер `_build_chat_model`, который всегда возвращает `ReasoningChatOpenAI`.

**Конфигурация.** `extra_body.reasoning: {effort, exclude}` управляет тем, *вернёт* ли провайдер reasoning и с какой глубиной (а не выбором класса): `effort` задаёт уровень рассуждений — OpenRouter нормализует значение между провайдерами (конвертация в token-budget/thinkingLevel) и молча маппит на ближайший поддерживаемый уровень, если провайдер не поддерживает запрошенный ровно; `exclude: false` — не отбрасывать рассуждения из ответа. Единая форма применяется во всех точках: `configs/agent.yaml` (`llm.extra_body`, `summarization.extra_body`, `subagents.llm.extra_body`) и `configs/security.yaml` (`llm_classifier.extra_body`). Методика подбора самих моделей и effort-уровня по роли — [reference/model-selection.md](../../reference/model-selection.md).

Legacy-алиас `extra_body.include_reasoning: true` (флаг без градации effort) сохранён в схеме (`LLMExtraBody`) для обратной совместимости, в текущих конфигах не используется.

При `exclude: true` reasoning не приходит и его цена не списывается в Langfuse — но класс остаётся `ReasoningChatOpenAI`, поведение идентично `ChatOpenAI`.

**Видимость.** В Langfuse generation `additional_kwargs.reasoning` попадает в поле output вместе с основным текстом; цена reasoning-токенов учитывается через `usage.completion_tokens_details.reasoning_tokens` — требуется корректный `prices.output_reasoning` в определении модели.

## Prompt Naming

Системные промпты в Langfuse именуются по формату `{name}--{label}`:

```
system--development
system--production
summarization--development
summarization--production
```

Двойной дефис (`--`) разделяет имя промпта и label окружения. Обеспечивает полную изоляцию dev/prod: каждое окружение имеет собственную историю версий. Подробнее — [prompt-management.md](../prompt-management.md).
