# Implementation Plan: feat-011 / трек T1 — Продуктовые субагенты v1

## Контекст

Трек T1 — весь scope итерации feat-011: механика субагентов по паттерну **subagent-as-tool**. Основной ReAct-агент делегирует подзадачу изолированному субагенту через обычный tool `run_subagent(agent_type, task, input_artifact_ids?)`; субагент — отдельный скомпилированный `StateGraph` со своим state, вызываемый `ainvoke` внутри tool, наружу возвращается только результат. Чистота контекста — конструктивная: вход субагента собирает tool из `task` + артефактов, история сессии туда не передаётся. Первые потребители — judge-проходы скилла `tech-article-writing` (без tools) и web-research (firecrawl-toolset).

Вырожденная партиция — трек один, параллелизации нет; конвейер фаз последовательный.

Источники:
- Tasklist: `doc/tasks/tasklist-post-mvp.md` § `### feat-011` (цель, критерии приёмки, triggered-by).
- Design-brief: `doc/tasks/iterations/post-mvp/feat-011-subagents-v1/design-brief.md` (все архитектурные решения; `## Партиция треков` — файловый скоуп T1).
- Архитектура: `doc/tech/agent-runtime.md`, `doc/tech/prompt-management.md`, `doc/tech/observability.md`, `doc/security/architecture.md`; конвенция `doc/tech/conventions/agent.md`.
- Релевантные ADR (референс паттернов): ADR-017 (prompt-injection-defense), ADR-024 (streaming-security-guard), ADR-026 (tool-introduction-pattern), ADR-014 (dynamic-model-resolution).
- ADR этой итерации: **ADR-028** (следующий свободный номер).

Ключевые точки существующего кода, на которые опираются фазы (проверено по коду):
- `backend/app/agent/graph.py` — `build_graph`, `agent_node`, `_handle_tool_error` (callable для `ToolNode`), `_guard_tool_results` (модульный, переиспользуемый), inline-проверка `TOOL_CALL_ARG` внутри `agent_node`, `ToolNode(tools, handle_tool_errors=...)` + `tools_condition`, `trim_messages`.
- `backend/app/agent/graph_factory.py` — `GraphFactory.build` (per-request компиляция, паттерн для per-invoke Runner).
- `backend/app/agent/config.py` — pydantic-модели конфигов, `AgentConfig`, `LLMConfig`, `PromptsRegistry.resolve`, `load_agent_config`.
- `backend/app/agent/tools/artifacts.py` — паттерн `make_create_artifact_tool` (session factory в замыкании, `ToolRuntime`, `runtime.context.project_id`).
- `backend/app/repositories/artifact.py` — `ArtifactRepository.get_by_id` (без project-скоупа — фильтрацию по `project_id` делает вызывающий), поле `Artifact.project_id`.
- `backend/app/infra/llm.py` — `_build_chat_model`, `create_llm_from_config(settings, ResolvedModelConfig)`.
- `backend/app/infra/prompt_provider.py` — `get_prompt` (Langfuse + file fallback), `load_file`.
- `backend/app/main.py` (≈320–465) — сборка `internal_tools` / `global_tools`, built-in MCP пул (`mcp_tools`), конструирование `GraphFactory`, `security_guard`.
- `backend/app/agent/runner.py` — стрим-цикл (`graph.astream(stream_mode=["messages","updates"])`), аккумуляция `full_response`, canary/mid-stream проверки.
- `backend/scripts/sync_prompts.py` — `PROMPT_NAMES` (список синка Langfuse↔файлы).
- LangGraph API (проверено через `inspect` в `.venv`): `compile(checkpointer=..., *, store=...)` — `checkpointer=False` отключает наследование (ноль записей), `None` наследует родительский; `ToolNode(handle_tool_errors=<callable>)` поддерживается; `tools_condition` доступен.

## Фазы

### T1.1: Декларативный слой — спека, реестр, промпты, XML-обёртка

**Цель:** ввести конфигурацию субагентов (модель `SubagentSpec` + реестр в `agent.yaml`, промпт-контур, обёртка входного документа) без исполняемого поведения.

**Изменения:**
- `backend/app/agent/config.py` — новые pydantic-модели: `SubagentSpec` (`name`, `description`, `prompt`, `model: str | None = None`, `tools: list[str] = []`, `persistence: Literal["none","inherit"] = "none"`) и `SubagentsConfig` (`llm: LLMConfig`, `registry: list[SubagentSpec]`). Добавить поле `subagents: SubagentsConfig | None = None` в `AgentConfig`. Валидацию имён tool против пула здесь **не** делать (fail-fast — на старте приложения, фаза T1.3).
- `configs/agent.yaml` — секция `subagents`: глобальный дефолт `llm` (`model` + `extra_body`, по образцу `summarization`) и `registry` из трёх спек — `judge` (tools пуст, `persistence: none`, `prompt: subagent-judge`), `web-research` (`tools: [firecrawl_search, firecrawl_scrape_url, firecrawl_extract_data]`, `persistence: none`, `prompt: subagent-web-research`), `general-purpose` (tools пуст, `persistence: none`, `prompt: subagent-general-purpose`). `description` каждой спеки — то, что попадёт в description инструмента.
- `configs/prompts.yaml` — три записи (`subagent-judge`, `subagent-web-research`, `subagent-general-purpose`), привязанные к `source: agent.subagents.llm` (ключи `model`/`extra_body`), по образцу `summarization`.
- `configs/prompts/subagent-judge.txt`, `configs/prompts/subagent-web-research.txt`, `configs/prompts/subagent-general-purpose.txt` — seed-тексты (fallback PromptProvider). Judge: независимый рецензент, вердикт **с evidence** (цитаты/ссылки на места текста, не голое summary — анти-«claim laundering»), без переписывания. Web-research: ресёрчер, наружу — выжимка с источниками. General-purpose: generic изолированная подзадача. Промпты через skill `prompt-engineering`.
- `backend/scripts/sync_prompts.py` — добавить три имени в `PROMPT_NAMES` (round-trip синк Langfuse↔файлы).
- `configs/prompt_fragments.yaml` — обёртка входного документа с атрибуцией `id`/`title` (см. Open Questions по механике представления атрибутов — текущий `PromptFragmentsConfig.wrap` умеет только фиксированные open/close без атрибутов).

**Verification:**
- `make check` проходит; `load_agent_config()` разбирает новую секцию.
- Критерий приёмки (частично): «Реестр в `agent.yaml`»; «Промпты субагентов — в Langfuse-контуре (`prompts.yaml` + seed + file fallback); модель — дефолт `subagents.llm` + per-spec override» (декларативная часть).

### T1.2: SubagentRunner + toolless-граф + сборка входа

**Цель:** исполняющее ядро — компиляция per-invoke и запуск субагента без tools (движок judge / general-purpose), сборка входа из task + документов.

**Изменения:**
- Новый модуль-коллаборатор (по конвенции agent.md «новая забота → отдельный коллаборатор»), напр. пакет `backend/app/agent/subagents/` (`runner.py`, `graph.py`). Точное имя — на усмотрение implementer в рамках `backend/app/agent/**`.
- `graph.py` (субагентский): builder toolless-формы — один LLM-узел (`START → llm → END`), system message = **только** промпт спеки (никаких KS/memory/skills/compaction — чистота контекста), `trim_messages` как safety net для больших входов. Форма с tools — фаза T1.5.
- `runner.py` (`SubagentRunner`): держит реестр спек (`SubagentsConfig`), пул built-in инструментов (`dict[name → BaseTool]`, инжектируется — наполнение в T1.3/T1.5), `settings`, `prompt_provider`, `security_guard`, model factory. Метод `run(agent_type, task, documents, *, config)`:
  - резолвит спеку по `agent_type`; неизвестный тип → доменная ошибка со списком доступных типов (её транслирует tool в T1.3);
  - строит модель из `agent.subagents.llm` (+ per-spec `model`-override) через `_build_chat_model` / `ResolvedModelConfig`;
  - берёт текст промпта через `prompt_provider.get_prompt(spec.prompt)`;
  - собирает вход: `SystemMessage` = промпт спеки; `HumanMessage` = `task` + документы, **каждый** в XML-обёртке с атрибуцией (`id`, `title`) из `prompt_fragments.yaml`, порядок — как в списке;
  - компилирует граф per-invoke; `persistence: none` → `compile(checkpointer=False)` (ноль записей в PG);
  - вызывает `ainvoke` с тегом `subagent` в `config` (`config={"tags": ["subagent"], ...}` — фундамент фильтра T1.4) и проброшенными callbacks;
  - возвращает финальный текст графа (v1 — текст; поле `output_schema` не заводится, отмечается в ADR как extension point).
  - **Инвариант:** `run_subagent` никогда не попадает в toolset субагента — Runner исключает его из пула независимо от конфига (защита от рекурсии).

**Verification:**
- `make check` проходит.
- Критерий приёмки (частично): вход субагента собирается только из `task` + артефактов (каждый в обёртке с id/title), история сессии не утекает; `persistence: none` (v1). Полная e2e-проверка judge — после T1.3.

### T1.3: tool `run_subagent` + fetch артефактов + wiring в main.py

**Цель:** связать движок с основным графом — тонкий tool, fetch артефактов «всё или ничего», сборка description из реестра, fail-fast валидация имён tool на старте. После фазы judge и general-purpose работают end-to-end.

**Изменения:**
- Новый tool-фабрика (напр. `backend/app/agent/tools/subagents.py`), паттерн `make_create_artifact_tool`: `session_factory` в замыкании, `SubagentRunner` в замыкании. `run_subagent(agent_type, task, input_artifact_ids?, runtime)`:
  - description собирается **на старте** из реестра — список `тип: описание` (паттерн Skills Index / ADR-026); инструкция модели: большой контекст → сохранить артефактом → передать id;
  - fetch артефактов по `input_artifact_ids` через `ArtifactRepository.get_by_id`, скоуп по `runtime.context.project_id`; семантика **всё или ничего**: любой чужой (`project_id` не совпал) или несуществующий id → error-строка tool с перечнем проблемных id, без частичного входа;
  - невалидный `agent_type` → error-строка со списком типов; ошибка субагента → error через callable `handle_tool_errors` основного `ToolNode`, основной граф продолжает работу;
  - при успехе — вызывает `SubagentRunner.run(...)`, возвращает результат как контент ToolMessage.
- `backend/app/main.py` (блок сборки tools ≈330–465):
  - построить пул built-in инструментов для субагентов из `internal_tools` + built-in `mcp_tools` (**без** user-installed MCP — trust-граница);
  - сконструировать `SubagentRunner` (реестр из `agent_config.subagents`, пул, guard, prompt_provider, settings, session_factory);
  - **fail-fast:** для каждой спеки проверить, что все имена `tools` резолвятся в пуле; неизвестное имя → ошибка старта приложения (как для остальных `configs/*.yaml`);
  - собрать tool `run_subagent` и добавить в `global_tools` (и, соответственно, в реестр детекторов/`tool_registry`, как прочие internal-tools);
  - исключить `run_subagent` из субагентского пула (совместно с инвариантом Runner).

**Verification:**
- `make check` проходит; приложение стартует.
- Критерии приёмки: `run_subagent("judge", task, input_artifact_ids)` возвращает вердикт; вход только из task + артефактов, история не утекает; любой чужой/несуществующий id → ошибка tool целиком, граф не падает. Реестр в `agent.yaml`; description собирается из реестра на старте; невалидный тип → ошибка со списком; неизвестное имя tool в спеке → ошибка старта.

### T1.4: Изоляция токенов субагента в стриме (фильтр по тегу)

**Цель:** токены LLM субагента не рисуются в чат и не попадают в `full_response` — фильтр по тегу `subagent` в стрим-цикле runner'а.

**Изменения:**
- `backend/app/agent/runner.py` — в ветке `mode == "messages"` стрим-цикла: отбрасывать чанки, помеченные тегом `subagent` (тег приходит в metadata чанка), **до** аккумуляции `full_response` и **до** canary/mid-stream проверок. Следствия сохранить: `full_response` чистый, `last_message_id` не портится id чанков субагента, `cancel_event` продолжает проверяться на отфильтрованных чанках (отзывчивость отмены во время рана субагента), Langfuse не задет (callbacks не трогаются), `tool_start`/`tool_end` для `run_subagent` идут штатно из `updates`.

**Verification:**
- `make check` проходит.
- Критерий приёмки: «Токены субагента не рисуются в чат и не попадают в `full_response` (фильтр по тегу)»; запуски субагентов видны в Langfuse вложенными span'ами (следствие проброса callbacks — проверить, что фильтр их не ломает).

### T1.5: Tools-форма субагентского графа + переиспользование guard (web-research)

**Цель:** ReAct-форма субагента с инструментами — цикл с guard-проверками, `recursion_limit`; web-research работает end-to-end.

**Изменения:**
- Субагентский `graph.py` — ветка непустого toolset: ReAct-цикл `ToolNode(tools, handle_tool_errors=<callable>)` + `tools_condition` (те же встроенные блоки, что в основном графе), `recursion_limit` (проброс в `config`/`compile`), `trim_messages` safety net. System message — по-прежнему только промпт спеки.
- Переиспользование guard внутри цикла с той же fail-safe redact-семантикой, что в основном `agent_node`:
  - `TOOL_RESULT` — переиспользовать модульный `_guard_tool_results` из `backend/app/agent/graph.py` (заражённая страница → подмена заглушкой `security_redacted`, цикл продолжает);
  - `TOOL_CALL_ARG` — вынести inline-проверку из `agent_node` (`backend/app/agent/graph.py`) в переиспользуемый helper (брифом предусмотрено: «обе проверки в `graph.py` параметризованы guard'ом»), применить в субагентском узле (инъекция в args → срез `tool_calls`). Это рефактор в границах `backend/app/agent/**`, поведение основного графа не меняется.
- Toolless-типы (judge, general-purpose) внутренних проверок не получают (untrusted-источников нет; вход проверен на границе основным графом).

**Verification:**
- `make check` проходит.
- Критерий приёмки: `web-research` — firecrawl-toolset; внутри цикла работают проверки `TOOL_RESULT`/`TOOL_CALL_ARG` (redact-семантика), `recursion_limit`; user-installed MCP в субагентов не попадают (следствие композиции пула в T1.3).

### T1.6: ADR-028 — Продуктовые субагенты (subagent-as-tool)

**Цель:** зафиксировать архитектурное решение итерации отдельным ADR.

**Изменения:**
- `doc/tech/adr/ADR-028-<slug>.md` (напр. `ADR-028-product-subagents.md`). Содержание по критерию приёмки: паттерн subagent-as-tool; отклонённые альтернативы (`langgraph-supervisor`/`langgraph-swarm`/`deepagents`; generic `run_subagent(instruction,input)` без реестра; tool-per-role); sync v1 vs async v2 (обоснование блокирующего judge, подводный камень двух ранов на один `thread_id`); формат реестра (секция `subagents` в `agent.yaml`, отклонение директории по образцу `skills/` до роста числа типов); вход по референсу (`input_artifact_ids`, инжект кодом, всё-или-ничего); security-политика (переиспользование checkpoint'ов основного графа на границе + inline-проверки внутри цикла с tools); extension points (`output_schema` v2, `persistence: inherit`, async v2 как вторая обёртка над Runner). Стиль — skill `aidd-methodology` + существующие ADR (формат ADR-024/026).

**Verification:**
- `make check` не затрагивает (docs), но контент-ревью против критерия приёмки ADR (все перечисленные пункты присутствуют).

### T1.7: Обновление SKILL.md — judge-проходы через артефакт

**Цель:** судейские проходы скилла статей интегрируют механику субагентов (черновик → `create_artifact` → id судье).

**Изменения:**
- `skills/tech-article-writing/SKILL.md` — в Шаге 5 (анти-слоп-проход, cold-reader-проход) дополнить: черновик сохраняется через `create_artifact`, затем `run_subagent("judge", task=<инструкция прохода>, input_artifact_ids=[<id>])`. Cold-reader — дисциплина одного документа в списке (только текст статьи). Отметить издержку: версий у артефактов нет — проход по правленому тексту требует пересохранения.

**Verification:**
- Контент-ревью против критерия приёмки «Judge-проходы `SKILL.md` обновлены: черновик → `create_artifact` → id судье». Frontmatter-стиль description не трогать (изменение — в теле).

## Cross-cutting

После всех фаз — сверить полный список критериев приёмки итерации (tasklist § feat-011):
- ADR со всеми обязательными разделами (T1.6).
- judge end-to-end: вердикт; вход только task + артефакты в обёртке id/title; история не утекает; чужой/несуществующий id → ошибка целиком, граф не падает (T1.2/T1.3).
- Реестр в `agent.yaml`; description из реестра на старте; невалидный тип → ошибка со списком; неизвестное имя tool → ошибка старта (T1.1/T1.3).
- web-research: firecrawl-toolset; `TOOL_RESULT`/`TOOL_CALL_ARG` redact внутри цикла; `recursion_limit`; user-installed MCP исключены (T1.5).
- Промпты в Langfuse-контуре (`prompts.yaml` + seed + fallback); модель — дефолт `subagents.llm` + per-spec override (T1.1/T1.2).
- `persistence: none|inherit` в спеке (v1 — none); запуски видны в Langfuse вложенными span'ами (T1.2/T1.4).
- Токены субагента не в чате и не в `full_response` (T1.4).
- Judge-проходы `SKILL.md` обновлены (T1.7).
- `make check` зелёный на всём треке.
- Автотесты (в т.ч. red-team инъекция страницей внутрь субагентского цикла — новая поверхность) пишет независимый test-author отдельно; в этот план не входят.

## Open Questions

1. ~~**Механика атрибутированной XML-обёртки входного документа в `configs/prompt_fragments.yaml`.**~~ **Разрешено архитектором (эскалация на фазе PLAN):** вариант (а) в облегчённой форме — open-тег в `prompt_fragments.yaml` содержит плейсхолдеры `{id}`/`{title}` (`<document id="{id}" title="{title}">` / `</document>`); Runner берёт пару через `open_close()` и подставляет значения (`.format` с экранированием кавычек в `title`). Текст обёртки целиком остаётся в YAML (консистентно с брифом «все XML-обёртки — в prompt_fragments.yaml»), класс `PromptFragmentsConfig` не меняется.

Нет открытых вопросов.
