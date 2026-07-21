# Конвенции: Agent

Проектные решения по agent runtime, скиллам, reasoning-моделям и именованию промптов. Ядро — [conventions.md](../conventions.md).

## Agent Runtime

Проектные решения по структуре agent runtime (`backend/app/agent/`). База — skill `langgraph-patterns`; здесь только выбранные развилки.

**Топология графа.** ReAct-цикл строится на pre-defined edges (`add_conditional_edges("agent", tools_condition)` + `add_edge("tools", "agent")`), не на Command API: топология известна на этапе компиляции, динамический routing не нужен. Checkpointer и Store (`AsyncPostgresSaver`/`AsyncPostgresStore`) — shared, создаются один раз в `lifespan` через `async with`; per-request пересобирается только граф (`GraphFactory`).

**Runner — оркестратор, не God Object.** `LangGraphAgentRunner` реализует контракт `AgentRunner` (stream / get_history / get_last_ai_message_id / cancel) и только оркеструет: стримит, принимает решения, эмитит SSE. Сквозные заботы вынесены в инжектируемых коллабораторов, у каждого своя причина меняться:

| Коллаборатор | Ответственность |
|--------------|-----------------|
| `RuntimeSecurityEnforcer` | Четыре runtime-чекпоинта guard'а (user input / mid-stream / final output / in-graph inspection) + редакция сообщений + пометка thread'а blocked. Каждый `check_*` делает свои сайд-эффекты и возвращает `SecurityOutcome | None`; runner по исходу решает `yield security_block`. |
| `AgentRunTracer` / `AgentRunSpan` | Langfuse-спан рана: score, finalize-on-block, output, mid-stream observation. Fail-safe (ошибки Langfuse подавляются). |
| `CheckpointHistory` | Единственное место, знающее форму `channel_values["messages"]`: чтение, маппинг в `Message`, поиск редакций. |
| `StreamEventMapper` | `stream_mode="updates"` → доменные `StreamEvent` (tool_start / tool_end / artifact_created). |

Принцип: новая сквозная забота в runtime → отдельный коллаборатор за портом, а не ещё один метод в runner.

**Слоистость security: движок vs enforcement.** Security-движок — `app/agent/security/` (детекторы, LLM-классификатор, `SecurityGuard`, типы): самодостаточный пакет, знающий, *что такое* инъекция. Точки применения (enforcement-адаптеры) живут уровнем выше, в `app/agent/`, рядом с кодом, который они защищают: `runtime_security.py` (`RuntimeSecurityEnforcer`) — stream-чекпоинты runner'а, `tool_guards.py` — in-graph чекпоинты `TOOL_RESULT`/`TOOL_CALL_ARG`, переиспользуемые основным графом и графами субагентов. Адаптеры знают, *где и как* вызвать guard и что делать с вердиктом (redact / срез `tool_calls`); в `security/` они не входят — движок не зависит от графов и runner'а.

## Skills

**Frontmatter `description` — стиль Claude Code.** Описание скилла в `SKILL.md` пишется как «назначение + триггеры»: одно-два предложения о том, что скилл делает, затем «Используй когда: <триггеры через запятую>». Формат намеренно совпадает с конвенцией skills Claude Code — скилл читаем любым агентом экосистемы без адаптации, а семантика срабатывания одинакова (system prompt продукта: «Load a skill when the user's task matches its description»). Description попадает в Skills Index — в system message каждого запроса — поэтому держится компактным; переносы строк нормализуются при сборке индекса (`scan_skills_index`).

## Reasoning LLMs

Часть моделей (OpenRouter-совместимые) отдают цепочку рассуждений в нестандартном поле `reasoning`. Чтобы извлекать её в `AIMessage.additional_kwargs["reasoning"]` — используется `ReasoningChatOpenAI` из `app/infra/llm.py`.

**Все модели проекта создаются как `ReasoningChatOpenAI` — безусловно.** Это безопасный надкласс `ChatOpenAI`: извлечение reasoning — no-op, когда провайдер не вернул поле `reasoning`. Поэтому ветки «`ReasoningChatOpenAI` или `ChatOpenAI` по флагу» нет — все фабрики (`create_llm_from_config` для агента, `create_summarization_llm` для summarizer, `create_guard_llm` для security guard) идут через единый приватный билдер `_build_chat_model`, который всегда возвращает `ReasoningChatOpenAI`.

**Конфигурация.** `extra_body.include_reasoning: true` управляет тем, *вернёт* ли провайдер reasoning (а не выбором класса):

- `configs/agent.yaml`: `llm.extra_body.include_reasoning`, `summarization.extra_body.include_reasoning`.
- `configs/security.yaml`: `llm_classifier.extra_body.include_reasoning`.

При `false`/отсутствии reasoning просто не приходит и его цена не списывается в Langfuse — но класс остаётся `ReasoningChatOpenAI`, поведение идентично `ChatOpenAI`.

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
