# Summary: трек T1 — Продуктовые субагенты v1

## TL;DR

Фаза T1.1 (декларативный слой) реализована: `SubagentSpec`/`SubagentsConfig` в
`config.py`, секция `subagents` в `agent.yaml` (реестр из `judge` / `web-research` /
`general-purpose`), три записи в `prompts.yaml` (все на `agent.subagents.llm`), три
seed-файла промптов, `PROMPT_NAMES` в `sync_prompts.py` дополнен, обёртка `document` с
плейсхолдерами `{id}`/`{title}` добавлена в `prompt_fragments.yaml` — по решению
архитектора из Open Questions, класс `PromptFragmentsConfig` не менялся.

Фаза T1.2 (исполняющее ядро) реализована: новый пакет `backend/app/agent/subagents/`
(`graph.py` — toolless single-node `StateGraph`, `runner.py` — `SubagentRunner`).
`SubagentRunner.run(agent_type, task, documents, *, config)` резолвит спеку из реестра
(неизвестный тип → `UnknownSubagentTypeError` со списком доступных типов), строит
модель из `agent.subagents.llm` + per-spec override, берёт промпт спеки через
`PromptProvider`, собирает `SystemMessage` (только промпт спеки) + `HumanMessage`
(`task` + документы в обёртке `document` с id/title, экранированием кавычек, в порядке
списка), компилирует граф per-invoke (`checkpointer=False` при `persistence: none`),
вызывает `ainvoke` с тегом `subagent` в config, возвращает финальный текст. Инвариант
«`run_subagent` никогда не в toolset субагента» — реализован в конструкторе Runner
(pop из копии пула независимо от конфига). Форма с tools (ReAct-цикл, T1.5) — не
реализована: `build_subagent_graph` явно бросает `NotImplementedError` на непустом
`tools`, это заложенная точка расширения, а не забытый кейс. Tool `run_subagent` и
wiring в `main.py` — T1.3, вне scope.

Фаза T1.3 (tool + wiring) реализована: `backend/app/agent/tools/subagents.py` —
`make_run_subagent_tool(session_factory, runner, registry)` создаёт tool
`run_subagent(agent_type, task, input_artifact_ids?, runtime)`. Description собирается
на старте (`build_run_subagent_description`) из реестра — по одной строке `name:
description` на тип (паттерн Skills Index, `app.agent.tools.skills.scan_skills_index`).
Fetch артефактов — «всё или ничего»: любой несуществующий/невалидный-UUID/чужой
(`project_id` не совпал) id → error-строка с перечнем именно проблемных id, ни один
документ не передаётся в Runner, если хоть один id не резолвился. Невалидный
`agent_type` — `UnknownSubagentTypeError` из Runner ловится в tool и возвращается как
error-строка со списком типов (не транслируется в generic `handle_tool_errors`, чтобы
не потерять список); все прочие исключения (модельные ошибки, будущий
`NotImplementedError` web-research до T1.5) не ловятся тут — летят наружу и попадают
в `_handle_tool_error` основного `ToolNode`, граф не падает.

`backend/app/main.py`: собран built-in пул для субагентов = `internal_tools +
mcp_tools` (built-in MCP only, без user-installed — резолвится уже после built-in MCP
validation, но до `MCPToolResolver`, который занимается user MCP отдельно и по
времени позже). Fail-fast `_validate_subagent_tool_pool` — до конструирования
`SubagentRunner`, поднимает `RuntimeError` на первом же неизвестном имени tool в любой
спеке (агрегирует все проблемные спека→имена в одном сообщении, не только первую).
Секция `subagents` отсутствует/`None` → весь блок (пул, fail-fast, Runner, tool)
пропускается — приложение стартует без `run_subagent`, как и прочие опциональные
конфиги (`summarization`).

Нетривиальность, потребовавшая переработки существующего блока (не только
добавления): чтобы `run_subagent` попал в `tool_registry`/`fragment_corpus` guard'а
«как прочие internal-tools» (требование плана), пришлось учесть порядок
зависимостей — built-in MCP validation (`_validate_builtin_mcp`) требует уже
готового guard'а, а пул субагента требует уже готовых `mcp_tools`, которые
появляются только после этой валидации. Guard строится дважды через общий
замыкающий helper `_build_security_guard` (тот же `classifier`/`guard_observer`,
переиспользуются, не задваиваются): первый раз — из `internal_tools` без
`run_subagent`, используется только для `_validate_builtin_mcp`; второй раз — после
того как `run_subagent` добавлен в `internal_tools`, замещает `security_guard`
всюду, где он используется дальше (`GraphFactory`, `RuntimeSecurityEnforcer`,
`app.state.security_guard`). Корректность разбиения проверена по коду детекторов:
`PairedToolIdentifierDetector`/`FragmentDetector` не входят в `applies_to` для
`Checkpoint.MCP_METADATA` (только `UnicodeDetector` + классификатор), так что
неполнота реестра/корпуса в первой сборке не влияет на единственную проверку,
для которой она использовалась. См. «Решения и обоснования» — это не архитектурное
решение, а вынужденная последовательность внутри уже одобренного контракта.

Фаза T1.4 (изоляция токенов субагента в стриме) реализована: в
`backend/app/agent/runner.py`, ветка `mode == "messages"` стрим-цикла, чанки с тегом
`subagent` в `metadata["tags"]` отбрасываются (`continue`) **до** проверки
`isinstance(msg_chunk, AIMessageChunk)`, **до** `last_message_id`/`full_response`
и **до** canary/mid-stream проверок. Тег вынесен в общую константу `SUBAGENT_TAG`
(`backend/app/agent/subagents/runner.py`, экспортирована из пакета) вместо дублирования
строкового литерала `"subagent"` в двух файлах (Runner, который его ставит, и стрим-цикл,
который его фильтрует) — оба места теперь ссылаются на одно и то же имя.

Фаза T1.5 (tools-форма субагентского графа + переиспользование guard) реализована:
`build_subagent_graph` теперь ветвится на toolless-форму (`_build_toolless_graph`,
как в T1.2) и ReAct-форму (`_build_react_graph`, новая) — та же схема
`ToolNode(tools, handle_tool_errors=...)` + `tools_condition`, что в основном графе.
Guard-проверки (`TOOL_RESULT`/`TOOL_CALL_ARG`) вынесены из `backend/app/agent/graph.py`
в новый модуль-коллаборатор `backend/app/agent/tool_guards.py`
(`guard_tool_results`, `guard_tool_call_args`, `handle_tool_error`) — необходимость
отдельного модуля, а не прямого импорта из `graph.py` в `subagents/graph.py`,
обнаружилась как реальный circular import (см. «Решения и обоснования»), не
предусмотренный планом буквально. `SubagentRunner` получил `security_guard`/
`security_messages` в конструкторе и `canary_token` в `run(...)` — эта проводка
не была сделана в T1.3 (guard там не использовался, T1.5 — первый потребитель).
`recursion_limit` — invoke-time `RunnableConfig` (не compile-time параметр,
проверено `inspect` в T1.5), константа `SUBAGENT_RECURSION_LIMIT = 10` в
`runner.py`. `web-research` теперь исполняется end-to-end без `NotImplementedError`.

Отступлений от plan/design-brief нет. Решения сверх буквы плана — формулировки
(`description` спек в T1.1, текст description tool'а в T1.3) и мелкие технические
детали (тип `config` в Runner, обработка отсутствующего `document`-wrapper, двойная
сборка guard'а в T1.3, константа `SUBAGENT_TAG` вместо литерала в T1.4, вынос guard-
хелперов в отдельный модуль и выбор `SUBAGENT_RECURSION_LIMIT` в T1.5) — см. «Решения
и обоснования». `make check` зелёный на всех пяти фазах; T1.2/T1.3/T1.4/T1.5
дополнительно verification прогнаны вручную (смотри секции § Verification), плюс
существующий `tests/agent/` (90 тестов, включая guard-регрессию для основного графа)
прогнан после рефакторинга — зелёный, без изменений в тестах; pytest-автотесты для
T1.5 не пишет эта роль (независимый test-author).

Фаза T1.7 (обновление `SKILL.md`) реализована: судейские проходы (анти-слоп,
cold-reader) в Шаге 5 переписаны на механику `create_artifact` →
`run_subagent("judge", task=<инструкция прохода>, input_artifact_ids=[<id>])`;
общая механика — в едином месте (под п. 3, помечена «для ВСЕХ judge-проходов»),
cold-reader (п. 5) ссылается на неё и добавляет свою специфику — дисциплину
одного документа в списке. Frontmatter не тронут.

Фаза T1.6 (ADR-028) реализована: `doc/tech/adr/ADR-028-product-subagents.md`
зафиксировал решение итерации — паттерн subagent-as-tool, слоистость
`SubagentSpec`/`SubagentRunner`/tool, обе таблицы отклонённых альтернатив (паттерн
целиком: `langgraph-supervisor`/`langgraph-swarm`/`deepagents`; задание субагентов:
tool-per-role / generic `run_subagent` без реестра / реестр + один tool), sync v1 vs
async v2 (блокирующая природа judge + подводный камень некоординируемых конкурентных
ранов на один `thread_id` в OSS LangGraph), формат реестра (секция `subagents` в
`agent.yaml`, отклонение директории по образцу `skills/` до роста числа типов), вход
по референсу (`input_artifact_ids`, инжект кодом, всё-или-ничего), security-политика
(переиспользование checkpoint'ов основного графа на границе + inline-проверки внутри
цикла с fail-safe redact-семантикой), extension points (`output_schema`,
`persistence: inherit`, async v2 как вторая обёртка над Runner'ом — сформулированы как
свойства слоистости, без меток итераций).

Пост-имплементационный фикс (fixer): ручной прогон вскрыл boot-blocker — спека
`web-research` и `firecrawl.allowed_tools` в `agent.yaml` ссылались на
несуществующие имена firecrawl-tools (`firecrawl_scrape_url`/`firecrawl_extract_data`
вместо реальных `firecrawl_scrape`/`firecrawl_extract`), и fail-fast
`_validate_subagent_tool_pool` корректно валил старт. Неверный allowlist —
пред-существующий дрейф из feat-003 (основной граф жил с ним тихо: пересечение с
реальными именами оставляло только `firecrawl_search`); спека web-research
скопировала те же имена в T1.1, где fail-fast их уже не простил. Исправлено во всех
вхождениях, честный boot зелёный — детали в § «Решения и обоснования».

## T1.1: Декларативный слой — спека, реестр, промпты, XML-обёртка

**Реализовано:**
- `backend/app/agent/config.py` — новые модели `SubagentSpec` (`name`, `description`,
  `prompt`, `model: str | None = None`, `tools: list[str] = []`,
  `persistence: Literal["none", "inherit"] = "none"`) и `SubagentsConfig`
  (`llm: LLMConfig`, `registry: list[SubagentSpec] = []`). Поле
  `subagents: SubagentsConfig | None = None` добавлено в `AgentConfig`. Валидация имён
  `tools` против built-in пула не делалась (по плану — фаза T1.3).
- `configs/agent.yaml` — секция `subagents`: `llm` (дефолт `z-ai/glm-4.7-flash` +
  `extra_body.include_reasoning: true`, по образцу `summarization`) и `registry` из
  трёх спек: `judge` (`tools: []`, `persistence: none`, `prompt: subagent-judge`),
  `web-research` (`tools: [firecrawl_search, firecrawl_scrape_url,
  firecrawl_extract_data]`, `persistence: none`, `prompt: subagent-web-research`),
  `general-purpose` (`tools: []`, `persistence: none`, `prompt:
  subagent-general-purpose`). `persistence: none` указан явно в каждой спеке для
  читаемости конфига, хотя совпадает с дефолтом модели.
- `configs/prompts.yaml` — три записи (`subagent-judge`, `subagent-web-research`,
  `subagent-general-purpose`), все с `source: agent.subagents.llm`, `keys: {model:
  model, extra_body: extra_body}` — по образцу `summarization`.
- `configs/prompts/subagent-judge.txt`, `configs/prompts/subagent-web-research.txt`,
  `configs/prompts/subagent-general-purpose.txt` — seed-тексты, написаны через skill
  `prompt-engineering` (английский, XML-семантика секций, explain-why вместо голых
  правил). Judge — независимый рецензент, вердикт с evidence (цитаты/точные ссылки на
  места документа), явный запрет переписывать текст. Web-research — ресёрчер,
  инструктирован не «гулять» бесцельно по страницам и не пересказывать их дословно,
  наружу — выжимка с цитируемыми источниками и явным указанием разногласий/пробелов.
  General-purpose — generic изолированная подзадача без tools, инструкция не задавать
  уточняющих вопросов (субагент не может получить ответ) и явно фиксировать сделанные
  допущения.
- `backend/scripts/sync_prompts.py` — `PROMPT_NAMES` дополнен тремя именами
  (`subagent-judge`, `subagent-web-research`, `subagent-general-purpose`).
- `configs/prompt_fragments.yaml` — добавлена запись `document` в `wrappers`:
  `<document id="{id}" title="{title}">` / `</document>` — облегчённый вариант (а) из
  Open Questions, разрешённый архитектором. Плейсхолдеры остаются буквальными
  `{id}`/`{title}` в YAML; подстановка через `.format()` с экранированием кавычек в
  `title` — задача Runner'а (фаза T1.2), класс `PromptFragmentsConfig`/`open_close()`
  не менялся.

**Verification:**
- `load_agent_config()` разбирает новую секцию `subagents` без ошибок (проверено
  вручную — `cfg.subagents.registry` содержит три спеки с ожидаемыми полями).
- `load_prompts_registry().resolve(...)` для всех трёх новых имён промптов резолвит
  `{model, extra_body}` из `agent.subagents.llm`.
- `load_prompt_fragments().open_close("document")` возвращает пару тегов с
  плейсхолдерами `{id}`/`{title}`.
- `make check` — зелёный (ruff check, ruff format --check, mypy backend/services/tools,
  import-linter, arch-checker).

## T1.2: SubagentRunner + toolless-граф + сборка входа

**Реализовано:**
- `backend/app/agent/subagents/graph.py` — `build_subagent_graph(model, system_prompt,
  tools, max_tokens)`: builder toolless-формы (один узел `llm`, `START -> llm -> END`),
  `SystemMessage` внутри узла = только `system_prompt` (без KS/memory/skills/
  compaction, без `compose_for_llm` trust-boundary wrapping — untrusted MCP-описаний
  внутри субагента нет), `trim_messages` (strategy="last", `token_counter=
  count_tokens_approximately`, `start_on="human"`, `end_on="human"`) как safety net
  перед вызовом модели. Непустой `tools` → `NotImplementedError` с явной отсылкой на
  T1.5 — точка расширения, а не пропуск. `compile_subagent_graph(builder, *,
  checkpointer)` — тонкая обёртка над `builder.compile(checkpointer=...)`.
- `backend/app/agent/subagents/runner.py` — `SubagentRunner`:
  - Конструктор принимает `agent_config`, `prompt_fragments`, `prompt_provider`,
    `settings`, опциональный `tool_pool: dict[str, BaseTool] | None` (дефолт — пустой;
    наполнение — T1.3/T1.5). Копирует пул и `pop("run_subagent", None)`
    безусловно — инвариант анти-рекурсии не зависит от содержимого конфига.
  - `_resolve_spec` — резолв по `agent_type` из `dict[name -> SubagentSpec]`;
    промах → `UnknownSubagentTypeError(agent_type, available_types)` (список
    отсортирован).
  - `_resolve_model_config` — `spec.model or subagents_config.llm.model` + `extra_body`
    из `subagents.llm` (per-spec override `extra_body` не предусмотрен планом/брифом —
    только `model`); `ResolvedModelConfig(source="config")`, консистентно с
    `ModelConfigResolver.default()`.
  - `_build_input_message` — `HumanMessage`: `task` (если непустой) + каждый документ
    в `open_close("document")` с `.format(id=.., title=..)`, кавычки в `id`/`title`
    экранируются в `&quot;` (защита от разрыва атрибута — план требовал экранирование
    заголовка, id экранируется тем же хелпером для симметрии, см. «Решения»). Порядок
    — как в списке `documents`. Отсутствие wrapper'а в конфиге — graceful fallback
    (документ без обёртки), не исключение.
  - `run(agent_type, task, documents=None, *, config: RunnableConfig | None = None) ->
    str`: резолв спеки → модель через `create_llm_from_config` → промпt через
    `prompt_provider.get_prompt(spec.prompt)` → резолв `spec.tools` из
    `self._tool_pool` (строгая индексация — `KeyError`, если пул не содержит имя;
    T1.3 гарантирует консистентность на старте) → `build_subagent_graph` →
    `compile_subagent_graph(checkpointer=False if persistence == "none" else None)` →
    сборка `HumanMessage` → `graph.ainvoke({"messages": [human_message]}, config=
    {**config, "tags": [...existing, "subagent"]})` → возврат `result["messages"]
    [-1].content` (строкой; нестроковый content стрингуется defensively).
    `structlog` keyword-args логи на старте/финише рана (`agent_type`, `model`,
    `persistence`, `document_count`/`output_length`).

**Verification (вручную, `uv run python -c ...`, реальный `configs/` + фейковая
модель `GenericFakeChatModel`/спай над `CompiledStateGraph.ainvoke`):**
- `judge` end-to-end: `SystemMessage.content` == ровно текст `subagent-judge.txt`
  (без служебных секций); `HumanMessage.content` == `task + "\n\n" + "<document
  id=\"doc-1\" title=\"Draft &quot;v1&quot;\">\nBody text.\n</document>"` — кавычка в
  заголовке экранирована, порядок и атрибуты корректны.
- Граф-level `config`, переданный в `graph.ainvoke`, содержит переданные
  `metadata`/др. ключи + `tags: ["subagent"]` (существующие теги не теряются, если
  вызывающий код их передаст).
- `UnknownSubagentTypeError` — для несуществующего `agent_type` вернулся список
  `["general-purpose", "judge", "web-research"]`.
- Пул: `run_subagent` в конструкторе исключается из `self._tool_pool` даже если
  передан явно.
- `web-research` (tools непустые) → `build_subagent_graph` кидает `NotImplementedError`
  с текстом, отсылающим к T1.5 — подтверждён явный сигнал незавершённости, а не
  тихий toolless-фолбэк.
- `make check` — зелёный (ruff check/format, mypy backend/services/tools, import-linter,
  arch-checker).

## T1.3: tool `run_subagent` + fetch артефактов + wiring в main.py

**Реализовано:**
- `backend/app/agent/tools/subagents.py` — новый модуль:
  - `build_run_subagent_description(registry) -> str` — description tool'а: одна
    строка `- name: description` на спеку (паттерн Skills Index,
    `app.agent.tools.skills.scan_skills_index`), плюс инструкция про большой
    контекст → `create_artifact` → id, плюс явное указание семантики «всё или
    ничего» для `input_artifact_ids`.
  - `_fetch_documents(session_factory, artifact_ids, project_id)` — по каждому id:
    невалидный UUID / не найден / `artifact.project_id` не совпал с
    `runtime.context.project_id` → id попадает в список проблемных; если список
    проблемных id непуст — `([], error_string)` с перечислением **только**
    проблемных id (не всех запрошенных), ни один документ не возвращается, даже
    если остальные id валидны. Успех — документы в порядке `artifact_ids`.
  - `make_run_subagent_tool(session_factory, runner, registry) -> BaseTool` —
    собирает tool `run_subagent(agent_type, task, input_artifact_ids?, runtime)`.
    Порядок параметров (`runtime` перед опциональным `input_artifact_ids`) —
    вынужден синтаксисом Python (non-default после default запрещён); LangChain
    резолвит инжектируемый `runtime` по типу `ToolRuntime`, а не по позиции —
    проверено (`args`/`tool_call_schema` не содержат `runtime`, `args_schema.
    model_fields` — содержит, это ожидаемо и не влияет на видимую модели схему).
    `runtime.context is None` → `RuntimeError` (тот же паттерн, что
    `create_artifact`). `UnknownSubagentTypeError` из `runner.run(...)` — ловится
    здесь и возвращается как error-строка (`str(exc)`, уже содержит список типов);
    все остальные исключения (модельные ошибки инфраструктуры, будущий
    `NotImplementedError` от `build_subagent_graph` для `web-research` до T1.5) —
    не ловятся, летят наружу к `handle_tool_errors` основного `ToolNode`
    (`_handle_tool_error` в `graph.py`), граф продолжает работу с generic
    error-сообщением.
  - `backend/app/agent/tools/__init__.py` — экспортированы
    `make_run_subagent_tool`, `build_run_subagent_description`.
- `backend/app/main.py` (блок сборки tools в `lifespan`):
  - Построение security guard'а вынесено в замыкающий helper
    `_build_security_guard(tools_for_corpus)` (переиспользует уже созданные
    `classifier`/`guard_observer`, не пересоздаёт их) — вызывается **дважды**:
    первый раз сразу после сборки `internal_tools` (до `run_subagent`), второй —
    после того как `run_subagent` добавлен в `internal_tools`. Причина
    двойного вызова — в «Решения и обоснования».
  - `_validate_subagent_tool_pool(subagents_config, pool)` — новая module-level
    функция рядом с `_validate_builtin_mcp`: для каждой спеки проверяет, что все
    имена `spec.tools` есть в `pool`; при расхождении — одно агрегированное
    `RuntimeError` со всеми проблемными спеками сразу (не первая попавшаяся),
    формат `"{spec}: {tool1, tool2}; {spec2}: {tool3}"`.
  - Wiring — единый блок `if agent_config.subagents is not None:` после
    резолва `mcp_tools`: `subagent_tool_pool = {t.name: t for t in
    [*internal_tools, *mcp_tools]}` (built-in only — user MCP резолвится позже,
    через `MCPToolResolver`, отдельным путём, в пул субагентов не попадает) →
    fail-fast валидация → `SubagentRunner(...)` → `make_run_subagent_tool(...)`
    → `internal_tools = [*internal_tools, run_subagent]` → `security_guard,
    tool_registry = _build_security_guard(internal_tools)` (повторно, с полным
    списком). Отсутствие секции `subagents` → блок целиком пропускается,
    `run_subagent` не создаётся, остальной pipeline (guard, `global_tools`,
    `GraphFactory`) работает как раньше — приложение стартует без tool.
  - `global_tools = internal_tools + mcp_tools` — заменил явный список
    (`ks_tools + user_memory_tools + [...] + mcp_tools`), т.к. `internal_tools`
    теперь может включать `run_subagent`; оба выражения эквивалентны до этой
    фазы, дублирование убрано.

**Verification (вручную, `uv run python -c ...`, реальный `configs/agent.yaml`,
БД недоступна в sandbox — см. ниже, что проверено без неё):**
- **Импорт/сборка приложения без сети:** `import app.main` + `create_app()` на
  module-level (с фиктивными обязательными env-переменными: `JWT_SECRET`,
  `LLM_API_KEY`, `LLM_BASE_URL`, `CANARY_SECRET`, `MCP_ENCRYPTION_KEY`,
  `DATABASE_URL` — заведомо недостижимый хост) — успешно строит `FastAPI` со
  всеми роутами; `lifespan` (где живёт wiring субагентов) не выполнялся, т.к.
  требует реальных Postgres/Redis, недоступных в sandbox (сеть per-команда
  изолирована; поднимать `docker-up-db` не стал — в этом же хосте уже
  запущены Postgres/Redis другого параллельного worktree
  (`feat-010-image-generation`) на стандартных портах 5432/6379, трогать
  чужую БД не стал — см. CLAUDE.md § «Параллельная разработка»).
- **Fail-fast валидации имён tools** (`_validate_subagent_tool_pool`,
  напрямую, с реальным `agent_config.subagents` из `configs/agent.yaml`):
  пул с тремя firecrawl-инструментами → без исключения; пустой пул → поднялся
  `RuntimeError` с текстом `"web-research: firecrawl_search,
  firecrawl_scrape_url, firecrawl_extract_data"` (реальная спека `web-research`
  из конфига).
- **`build_run_subagent_description`** — с реальным реестром вернул текст с
  тремя строками `judge`/`web-research`/`general-purpose` и их description из
  `agent.yaml`, плюс инструкцию про `create_artifact`.
- **`run_subagent` end-to-end через tool-обёртку** (реальные `SubagentRunner` +
  `configs/`, `ArtifactRepository.get_by_id` замокан на фейковые артефакты —
  без реальной БД, `CompiledStateGraph.ainvoke` заспаен на фиксированный
  `AIMessage`, вызов через `tool.coroutine(...)` с сконструированным
  `ToolRuntime` — паттерн из `tests/image_generation/test_generate_image_tool.py`):
  - невалидный `agent_type` → `"Unknown subagent type 'nope'. Available types:
    general-purpose, judge, web-research"` (без исключения наружу).
  - один существующий id (своего project_id) + один чужой project_id + одна
    невалидная UUID-строка → error-строка перечисляет **только** проблемные два
    (`{foreign_id}, not-a-uuid`), не включает валидный id — подтверждает
    «всё или ничего» без частичного пропуска.
  - единственный несуществующий id → error с этим id, ни один subagent не
    запущен (Runner.run не вызывался — подтверждено отсутствием побочного лога
    `"subagent run started"`).
  - валидный `judge` + один валидный документ с кавычкой в title → результат
    tool == сконструированный `AIMessage.content`; захваченный `HumanMessage`,
    отправленный в под-граф, содержит `task + "\n\n" + "<document id=\"...\"
    title=\"Draft &quot;v1&quot;\">\nBody text of the draft.\n</document>"`;
    захваченный `config`, переданный в `graph.ainvoke`, сохранил внешний тег
    `"main-graph"` из `runtime.config` и добавил `"subagent"` (`tags:
    ["main-graph", "subagent"]`) — подтверждает проброс `runtime.config` из
    tool в `Runner.run(config=...)`.
- **Guard-реестр после wiring** (напрямую, без `main.py`'s lifespan): собрал
  `run_subagent` tool и прогнал `collect_tool_registry([run_subagent])` /
  `collect_fragment_corpus(..., internal_tools=[run_subagent])` — реестр
  содержит запись `"run_subagent": [...]` (параметры, включая служебный
  `runtime` — унаследованная особенность `collect_tool_registry`, читающего
  полный `args_schema.model_fields`, а не публичную `args`-схему; так же ведут
  себя уже существующие `create_artifact`/`generate_image`, не регрессия),
  корпус содержит description tool'а целиком.
- `make check` — зелёный (ruff check/format, mypy backend/services/tools,
  import-linter, arch-checker).

## T1.4: Изоляция токенов субагента в стриме (фильтр по тегу)

**Реализовано:**
- `backend/app/agent/runner.py`, стрим-цикл, ветка `mode == "messages"`: сразу
  после `msg_chunk, chunk_metadata = data` — если `SUBAGENT_TAG in
  (chunk_metadata.get("tags") or ())`, `continue` **до** проверки
  `isinstance(msg_chunk, AIMessageChunk)`, **до** `last_message_id`/`full_response`
  и **до** canary/mid-stream проверок (`_enforcer.check_mid_stream`). `cancel_event`
  не тронут — проверяется безусловно на **каждой** итерации цикла ещё до диспетчеризации
  по `mode` (было так уже до этой фазы), так что отмена остаётся отзывчивой и на
  отфильтрованных чанках без дополнительного кода. `updates`-ветка не изменена —
  `tool_start`/`tool_end` для `run_subagent` идут из неё, как и раньше. Callbacks/
  Langfuse (`span.callback_handler` в `config["callbacks"]`) не затронуты — фильтр
  работает только на стороне проекции `stream_mode="messages"` в этом цикле.
- `backend/app/agent/subagents/runner.py` — тег вынесен в константу `SUBAGENT_TAG:
  Final = "subagent"` (рядом с существующей `RUN_SUBAGENT_TOOL_NAME`), используется
  и там, где Runner его проставляет (`run()`, сборка `tags` в `run_config`), и
  экспортирована из `app.agent.subagents.__init__` — стрим-цикл импортирует оттуда
  же (`from app.agent.subagents import SUBAGENT_TAG`), не из внутреннего модуля
  `subagents.runner` напрямую (тот же паттерн публичного API пакета, что уже
  использует `main.py` для `SubagentRunner`). Один литерал вместо двух — тег ставится
  и фильтруется по одному и тому же имени.

**Verification:**
- `make check` — зелёный (ruff check/format, mypy backend/services/tools,
  import-linter, arch-checker).
- **Юнит-уровень (по букве плана — «фейковый граф, эмитящий чанки с тегом и без»):**
  фейковая `FakeGraph.astream()` напрямую отдаёт в `LangGraphAgentRunner.stream()`
  сценарий из шести событий — два `messages`-чанка с `tags=["subagent"]` (в т.ч. один
  с посторонним `seq:step:3` в списке тегов и **другим** `msg_chunk.id`, чтобы
  проверить, что подмена `last_message_id` не происходит), два `updates`, два чистых
  `messages`-чанка без тега. Результат: `text_chunk` содержит ровно `"Hello world"` —
  оба `LEAKED_SUBAGENT_TOKEN_*` не просочились; без фильтра (тот же сценарий на
  версии `runner.py` без изменений T1.4, проверено — временный `git stash` фикса)
  тот же прогон даёт `"LEAKED_SUBAGENT_TOKEN_1LEAKED_SUBAGENT_TOKEN_2Hello world"` —
  подтверждает, что тест действительно ловит регрессию, а не проходит вхолостую.
- **Интеграционный уровень (реальный `build_graph`/`GraphFactory`/`LangGraphAgentRunner`,
  фейковые стримящие модели, реальный `ToolNode`):** tool вызывает настоящий
  вложенный `StateGraph` (та же форма, что `build_subagent_graph`) через `ainvoke`
  с `tags=["subagent"]`, взятыми из `runtime.config` (как в реальном `SubagentRunner`).
  `text_chunk`-поток содержит ровно финальный ответ основного агента, без токенов
  вложенного графа; `tool_start`/`tool_end` присутствуют.
- **Важное наблюдение, не меняющее реализацию, но важное для понимания механики:**
  при этом интеграционном прогоне отфильтрованные тегом чанки субагента и без
  тега (т.е. фикс T1.4 временно убран) **не появлялись в `stream_mode="messages"`
  вообще** — не из-за тега, а потому что LangGraph по умолчанию (`astream(...,
  subgraphs=False)`, этот параметр `runner.py` не передаёт и не менялся в этой фазе)
  исключает из `messages`-режима любой чанк, чей `langgraph_checkpoint_ns` глубже
  родительского (проверено инструментированием `StreamMessagesHandler.on_chat_model_start`
  из `langgraph.pregel._messages` — вызов для вложенного графа реально доходит с
  правильным тегом `["subagent", ...]` в `tags`, но обрывается на строке `if not
  self.subgraphs and len(ns) > 0 and ns != self.parent_ns: return` раньше, чем
  успевает записать `self.metadata[run_id]`, из-за чего последующие
  `on_llm_new_token` для этого run_id не эмитятся). Иными словами: для текущей формы
  вызова субагента (`ainvoke` вложенного скомпилированного графа **изнутри coroutine
  tool'а**, не как зарегистрированный узел графа) изоляция токенов уже обеспечена
  дефолтным поведением LangGraph, независимо от тега. Фильтр по тегу, тем не менее,
  реализован буквально по плану/брифу — это не лишняя работа: (а) он документирует
  инвариант явно в коде рядом с остальными инвариантами цикла, не полагаясь на
  недокументированное поведение приватного `subgraphs`-фильтра LangGraph; (б) он
  остаётся единственной защитой, если когда-либо `subgraphs=True` понадобится для
  другой легitimate цели (например, чтобы стримить состояние настоящих
  узлов-подграфов где-то ещё в основном графе) — без тега это сразу же стало бы
  реальной утечкой. Юнит-тест (фейковый граф) проверяет именно код фильтра
  напрямую, независимо от того, срабатывает ли путь LangGraph по умолчанию —
  поэтому демонстрирует и живую регрессию (см. выше), и не зависит от этой
  особенности LangGraph. Эскалации не потребовалось — план просил реализовать
  фильтр по тегу буквально, что сделано; наблюдение зафиксировано здесь как
  контекст для будущих фаз/ревью, а не как расхождение с планом.

## T1.5: Tools-форма субагентского графа + переиспользование guard (web-research)

**Реализовано:**
- `backend/app/agent/tool_guards.py` — новый модуль-коллаборатор. Три функции,
  дословно перенесённые из `backend/app/agent/graph.py` (то же поведение, те
  же логи/severity/event-поля, никаких новых `event_type`): `handle_tool_error`
  (был `_handle_tool_error`), `guard_tool_results` (был `_guard_tool_results`),
  `guard_tool_call_args` — новая функция, выделенная из inline-блока
  `agent_node` (шаг 5 «Post-guard: TOOL_CALL_ARG»). Ведущий underscore убран
  из имён при переносе — это больше не module-private детали `graph.py`, а
  общий контракт двух графов (см. «Решения и обоснования» насчёт причины
  выноса в отдельный модуль, а не прямого импорта из `graph.py`).
- `backend/app/agent/graph.py` — `agent_node` теперь вызывает
  `guard_tool_results`/`guard_tool_call_args`/`handle_tool_error` из
  `tool_guards.py` вместо inline-кода/module-private функций; строка кода
  шага 5 сократилась с ~45 строк до вызова `response = await
  guard_tool_call_args(response, security_guard, runtime.context.canary_token,
  list(messages))` + `return {"messages": [*result_prefix, response]}` —
  функционально идентично прежнему `if ... return {...redacted}; return
  {...response}` (проверено `tests/agent/test_graph.py`, 90/90 зелёных, включая
  все guard-тесты: `test_guard_injection_on_tool_call_args_strips_tool_calls`,
  `test_guard_clean_lets_tool_calls_execute`,
  `test_guard_injection_on_tool_result_redacts_tool_message`,
  `test_guard_suspicious_on_tool_call_args_does_not_redact`).
- `backend/app/agent/subagents/graph.py` — `build_subagent_graph` ветвится:
  пустой `tools` → `_build_toolless_graph` (код T1.2 без изменений, вынесен в
  отдельную функцию); непустой `tools` → новая `_build_react_graph` — те же
  строительные блоки, что основной граф: `model.bind_tools(tools)`,
  `ToolNode(tools, handle_tool_errors=handle_tool_error)`, `tools_condition`,
  `add_conditional_edges("llm", tools_condition)` + `add_edge("tools", "llm")`.
  Guard внутри узла `llm` — тот же порядок операций, что `agent_node`:
  pre-guard `TOOL_RESULT` над батчем `ToolMessage` (замена на `tool_result_stub`
  по id, цикл продолжает) → `trim_messages` (safety net, `end_on=("human",
  "tool")` — как в основном графе, а не `end_on="human"` toolless-формы, потому
  что здесь сообщения могут заканчиваться `ToolMessage`) → вызов модели →
  post-guard `TOOL_CALL_ARG` (`tool_calls` обнуляются при `INJECTION`, следующий
  `tools_condition` роутит в END). Оба чека — no-op при `security_guard=None`
  (см. ниже). `NotImplementedError` для непустого `tools` — убран.
  `build_subagent_graph` получил три новых keyword-only параметра
  (`security_guard`, `canary_token`, `tool_result_stub`) с дефолтами
  (`None`/`""`/`""`) — не ломает существующие вызовы toolless-специй.
- `backend/app/agent/subagents/runner.py` — `SubagentRunner.__init__` получил
  `security_guard: SecurityGuard | None = None` и
  `security_messages: SecurityMessages | None = None` (эта проводка не была
  сделана в T1.3 — guard там не был нужен, T1.5 первый потребитель).
  `run(...)` получил `canary_token: str = ""` keyword-only параметр,
  пробрасывается и в `build_subagent_graph(...)`, и в guard-чеки внутри узла.
  Новая константа `SUBAGENT_RECURSION_LIMIT: Final = 10` — `recursion_limit`
  проверен через `inspect` как **invoke-time** ключ `RunnableConfig`, не
  compile-time параметр (design-brief оставлял открытым, «проброс через
  config/compile» — решено по факту API), поэтому передаётся в `run_config`
  наравне с `tags`: `{**config, "tags": [...], "recursion_limit":
  SUBAGENT_RECURSION_LIMIT}`. Применяется безусловно (в т.ч. для toolless-специй
  — безвредно, однонодовый граф никогда не зацикливается).
- `backend/app/agent/tools/subagents.py` — `run_subagent` tool теперь передаёт
  `canary_token=runtime.context.canary_token` в `runner.run(...)` (было
  недоступно раньше — `AgentContext.canary_token` уже существовал, но Runner
  не принимал этот параметр до T1.5).
- `backend/app/main.py` — конструктор `SubagentRunner(...)` дополнен
  `security_guard=security_guard` (интеримный guard — тот же, что уже
  использовался для `_validate_builtin_mcp`, до второй пересборки с
  `run_subagent` в реестре) и `security_messages=security_config.messages`.
  Обоснование выбора интеримного, а не финального guard'а — см. «Решения и
  обоснования» (та же природа компромисса, что уже задокументирована в T1.3
  для двойной сборки guard'а).

**Verification (вручную, `PYTHONPATH=. uv run python ...`, фейковые модели
`tool_binding_fake`/`ToolBindingFakeChatModel` из `tests/agent/conftest.py`,
реальные `build_subagent_graph`/`compile_subagent_graph`/`SubagentRunner`;
скрипты не сохранялись как тест-файлы — scope этой роли их не пишет):**
- **ReAct-цикл `build_subagent_graph(tools=[search])` end-to-end** (без
  guard'а): `llm → tools → llm → END`, финальный `AIMessage.content ==
  "final answer"`, `ToolMessage` присутствует в истории.
- **`TOOL_RESULT` injection внутри цикла**: guard-стаб возвращает `INJECTION`
  для `Checkpoint.TOOL_RESULT` → `ToolMessage.content` заменён на
  `tool_result_stub` (`"[REDACTED]"`), `additional_kwargs["security_redacted"]
  is True`, цикл **продолжает** (следующий `llm`-узел получил редактированный
  результат, не оборвался) — та же fail-safe redact-семантика, что в основном
  графе.
- **`TOOL_CALL_ARG` injection**: guard-стаб возвращает `INJECTION` для
  `Checkpoint.TOOL_CALL_ARG` → ответ модели с `tool_calls=[]` после редакции,
  граф завершается за 2 сообщения (human + redacted AI) — `tools`-узел
  **не вызывается вовсе** (`tools_condition` роутит в END по пустым
  `tool_calls`), `additional_kwargs["security_redacted"] is True`.
- **`recursion_limit` ограничивает цикл**: модель, запрограммированная
  бесконечно возвращать новые `tool_calls`, с `config={"recursion_limit": 6}`
  → `GraphRecursionError` поднят вместо бесконечного цикла.
- **`security_guard=None` → fail-open, не блокирует**: ReAct-цикл с
  `security_guard=None` проходит идентично «без guard'а вовсе» — оба чека
  no-op, консистентно с тем, как `agent_node` основного графа ведёт себя при
  `security_guard=None`.
- **`SubagentRunner.run("web-research", ...)` end-to-end** (с
  `create_llm_from_config` и `compile_subagent_graph` замоканы на фейковую
  модель/spy, `security_guard` — записывающий стаб): захваченный `config`,
  переданный в `graph.ainvoke`, содержит `recursion_limit ==
  SUBAGENT_RECURSION_LIMIT`, `tags == {"main-graph", "subagent"}` (внешний тег
  из `runtime.config` сохранён, `subagent` добавлен), `metadata` из внешнего
  `config` не потерян; guard получил оба чека (`TOOL_CALL_ARG`, `TOOL_RESULT`)
  с `canary_token == "canary-999"`, переданным в `runner.run(..., canary_token=
  ...)` — подтверждает сквозную проводку canary-токена tool → Runner → узел
  графа → guard.check.
- **Регрессия основного графа**: `tests/agent/test_graph.py` (90 тестов
  всего в `tests/agent/`) прогнан после рефакторинга `graph.py`/выноса в
  `tool_guards.py` — все зелёные без изменений в тест-файлах, включая
  guard-специфичные тесты (`_SelectiveGuard`-based) и ReAct/interrupt/resume
  тесты, не связанные с guard'ом напрямую (структура графа не изменилась).
- **Сборка приложения**: `import app.main` + `create_app()` (те же
  фиктивные обязательные env-переменные, что в T1.3, `lifespan` не
  выполнялся — БД недоступна в sandbox, без изменений от T1.3) — успешно
  строит `FastAPI` с новым сигнатурой `SubagentRunner(..., security_guard=,
  security_messages=)`.
- `make check` — зелёный (ruff check/format, mypy backend/services/tools,
  import-linter, arch-checker).

## T1.6: ADR-028 — Продуктовые субагенты (subagent-as-tool)

**Реализовано:**
- `doc/tech/adr/ADR-028-product-subagents.md` — новый ADR, номер свободен
  (последний существующий — ADR-027). Скелет секций — по образцу ADR-024/026,
  объединённый (оба документа используют разное подмножество секций Статус/
  Контекст/Решение/Рассмотренные-или-Отклонённые-альтернативы/Обоснование/
  Следствия/Связанные документы; ADR-028 использует полный набор, т.к.
  content по критерию приёмки требует и таблиц альтернатив, и связного
  решения по многим аспектам сразу). Содержание — по фазе T1.6 плана и
  критерию приёмки tasklist (совпадают дословно): паттерн subagent-as-tool
  и его отклонённые альтернативы (`langgraph-supervisor`/`langgraph-swarm`/
  `deepagents`); отклонённые альтернативы задания субагентов (tool-per-role,
  generic `run_subagent` без реестра); sync v1 vs async v2 с обоснованием
  (блокирующий judge, подводный камень двух конкурентных ранов на один
  `thread_id` в OSS LangGraph — double-texting недоступен вне платной
  платформы); формат реестра (секция `subagents` в `agent.yaml`, отклонение
  директории `skills/`-образца до роста числа типов); вход по референсу
  (`input_artifact_ids`, инжект кодом а не моделью, всё-или-ничего);
  persistence-режимы (`none`/`inherit`) с обоснованием через роль
  checkpointer'а; security-политика (граница — checkpoint'ы основного графа,
  внутри цикла — переиспользуемый guard-модуль с fail-safe redact); extension
  points (`output_schema`, `persistence: inherit`, async v2 как вторая
  обёртка над Runner'ом) — сформулированы как свойства слоистости
  архитектуры, без меток вида «будет в feat-XXX» (соответствует запрету
  CLAUDE.md на временные метапометки в документах).
- Диаграммы в ADR не дублируются — design-brief уже содержит все нужные
  Mermaid-диаграммы (flowchart паттерна, sequence вход-по-референсу,
  flowchart промпт-контура, flowchart tools-формы, sequence стриминг-
  изоляции); ADR ссылается на design-brief как источник визуализации
  (Single Source of Truth, skill `aidd-methodology` § «ADR и архитектурные
  документы»), не копирует их — консистентно с тем, что ни ADR-024, ни
  ADR-026 диаграмм не содержат.

**Verification:**
- Контент-ревью против критерия приёмки ADR из tasklist (дословно тот же
  список, что в фазе T1.6 плана) — все восемь пунктов присутствуют текстом
  выше; `make check` фазу не затрагивает (docs-only изменение).

## T1.7: Обновление SKILL.md — judge-проходы через артефакт

**Реализовано:**
- `skills/tech-article-writing/SKILL.md`, Шаг 5 — п. 3 (анти-слоп-проход) и
  п. 5 (cold-reader-проход) переписаны на механику субагентов: черновик
  сохраняется через `create_artifact`, затем `run_subagent("judge",
  task=<инструкция прохода>, input_artifact_ids=[<id артефакта>])` — контракт
  взят дословно из tool'а T1.3 (с точки зрения модели — `agent_type`, `task`,
  опциональный `input_artifact_ids`; параметр `runtime` инжектируется
  рантаймом, моделью не передаётся и не виден в description). Общая механика
  описана один раз (под п. 3, помечена «для ВСЕХ judge-проходов: этот,
  cold-reader, любой добавленный» — как и было в исходном тексте), п. 5
  ссылается на неё и добавляет свою специфику — дисциплину одного документа
  в `input_artifact_ids` (только черновик статьи, без ресёрчей и соседних
  материалов) вместо прежней общей формулировки «свежий субагент читает
  только текст статьи».
- Издержка версий у артефактов отмечена явно в общей механике (под п. 3):
  если черновик правился после последнего сохранения, для нового прохода
  нужен новый `create_artifact` → новый id — старый id больше не
  соответствует правленому тексту.
- Критерии судейских проходов (анти-слоп по `anti-slop-checklist.md`,
  cold-reader по проклятию знания) не менялись — правка касается только
  механики доставки текста судье и того, кто выполняет проход (независимый
  субагент вместо самопроверки в текущем контексте).
- Frontmatter (`description`) не тронут — изменение только в теле документа
  (Шаг 5).

**Verification:**
- Контент-ревью против критерия приёмки «Judge-проходы `SKILL.md` обновлены:
  черновик → `create_artifact` → id судье» — оба прохода (анти-слоп,
  cold-reader) явно описывают эту последовательность; вызов `run_subagent`
  указан с точной сигнатурой из T1.3 (`agent_type`, `task`,
  `input_artifact_ids`).
- `make check` фазу не затрагивает (правка одного skill-документа, без кода).

## Решения и обоснования

- **Тексты `description` в реестре и seed-промптов — решения сверх буквы плана.**
  Design-brief и plan.md фиксируют смысл (judge — вердикт с evidence, web-research —
  выжимка с источниками, general-purpose — generic), но не дословный текст. Писал их
  как продакшн tool-description/system-prompt: английский язык (консистентно с
  `create_artifact`/`system.txt` — весь текст, видимый модели, на английском), explain-why
  вместо голых правил (skill `prompt-engineering`). Это не архитектурное решение —
  чистая формулировка внутри уже одобренного контракта, эскалации не требовало.
- **`persistence: none` указан явно в каждой спеке**, а не оставлен на дефолт модели.
  Причина — читаемость: реестр в `agent.yaml` — единственное место, где архитектор
  видит все три спеки разом; явное поле делает v1-инвариант («все три — none»)
  видимым без похода в код модели. Отклонение от буквального минимализма («раз дефолт
  совпадает — не писать»), но не от плана — план прямо перечисляет `persistence: none`
  в описании каждой спеки.
- **`sync_prompts.py` — правка ограничена `PROMPT_NAMES`.** `_update_yaml_config` /
  `_update_agent_yaml` внутри скрипта не различают новые имена промптов (ветки
  `if/elif` покрывают только `system`/`summarization`/`security-classifier`) — для
  `subagent-*` при обратном sync конфиг из Langfuse просто не запишется обратно в
  `agent.yaml` (текст промпта — запишется). Это существовало как ограничение скрипта
  до этой фазы (он писался под три конкретных промпта) и не входит в scope T1.1 по
  плану («добавить три имени в `PROMPT_NAMES`» — буквально то, что сделано). Не чинил
  проактивно — это не дрейф документации/кода против факта, а сознательно
  ограниченный scope существующего инструмента; если архитектор сочтёт нужным
  расширить `_update_agent_yaml` под секцию `subagents.llm`, это отдельное решение
  (три записи используют один и тот же `agent.subagents.llm` — потребует
  дедупликации логики "какая из трёх последней запишет конфиг").
- **Стартовый seed (`backend/app/main.py::_seed_prompts`) новых правок не требует.**
  Проверено по коду: `_seed_prompts` итерируется по `prompts_registry.prompts` (ключи
  из `prompts.yaml`), не по хардкоженному списку — три новых промпта подхватятся
  автоматически при следующем старте приложения. `PROMPT_NAMES` в `sync_prompts.py` —
  независимый список, специфичный только для обратного Langfuse→файлы sync-скрипта.
- **Валидация имён `tools` в спеках не добавлена** — намеренно, по плану (fail-fast
  резолв из built-in пула — фаза T1.3, когда пул собирается в `main.py`). На этой фазе
  `tools: list[str]` — просто список строк без семантической проверки.

- **Экранирование кавычек применено к `id`, а не только к `title`.** Open Questions
  разрешал экранирование конкретно в `title` (id — код-контролируемый UUID из
  `ArtifactRepository`, кавычек не содержит). Решил экранировать оба атрибута одним
  и тем же хелпером (`_escape_attr`) — нулевая цена, устраняет теоретический риск
  сломанного тега, если источник `id` когда-нибудь перестанет быть гарантированным
  UUID (например, тестовый вызов Runner напрямую, не через tool). Не расширяет
  контракт и не меняет поведение для реального пути (T1.3 fetch по UUID) —
  чисто защитная избыточность, не архитектурное решение.
- **Тип `config` в `SubagentRunner.run` — `RunnableConfig | None`, а не
  `dict[str, Any] | None`.** План говорит буквально `run(agent_type, task, documents,
  *, config)` без типа. `RunnableConfig` — существующий в проекте TypedDict
  (`app/agent/security/classifier.py` уже так делает для guard-вызовов) — точнее
  документирует контракт (`tags`/`callbacks`/`metadata`/...), чем голый `dict`;
  slicing через `{**(config or {}), "tags": tags}` возвращает валидный `RunnableConfig`
  без `type: ignore`.
- **Резолв `spec.tools` из `self._tool_pool` — строгая индексация (`KeyError` при
  отсутствии), без try/except и без тихого дропа отсутствующих имён.** Рассмотренная
  альтернатива — молча пропускать нерезолвящиеся имена (`if name in pool`): отклонена,
  потому что маскирует рассинхрон реестра и пула ложным «работает без tools», когда на
  самом деле спека их требует. Строгая индексация — правильный сигнал в промежуточном
  состоянии до T1.3 (fail-fast валидация имён при старте приложения делает эту ветку
  недостижимой в проде; до T1.3 `KeyError` при прямом вызове `run("web-research", ...)`
  — ожидаемо, потому что пул по умолчанию пуст).
- **`build_subagent_graph` кидает `NotImplementedError` на непустом `tools`, а не
  тихо строит toolless-граф, игнорируя `tools`.** План: «заложи расширяемость, но не
  реализуй ReAct-ветку» — трактовал это как «интерфейс уже принимает `tools`, но
  поведение для непустого списка обязано быть явной ошибкой», а не «тихо не
  учитывать `tools`» (последнее скрыло бы от вызывающего кода/будущих тестов, что
  `web-research` не работает end-to-end до T1.5, и рисковало бы create ложное
  впечатление рабочего инструмента без своих tools). **Суперсидировано в
  T1.5**: `tools`-ветка теперь реализована (`_build_react_graph`), `raise`
  убран — фиксирую здесь только как исторический контекст решения T1.2, не
  как актуальное поведение (актуальное — секция «T1.5» выше).
- **`_resolve_model_config` не поддерживает per-spec `extra_body`-override —
  только `model`.** `SubagentSpec.model: str | None` (T1.1) — единственное override
  поле по плану/брифу («опциональный per-type override `model`»); `extra_body` всегда
  берётся из `subagents.llm`. Согласовано с буквой обеих фаз, не расширение.
- **`checkpointer` в `compile_subagent_graph` типизирован как `Any`**, не как
  `Checkpointer | None` (тип LangGraph) — консистентно с `compile_graph` в
  `backend/app/agent/graph.py`, который делает то же самое (`checkpointer: Any`).
  Не вводит новое расхождение со стилем модуля.

- **Guard в `main.py` строится дважды через общий helper, вместо одного вызова
  без `run_subagent` в реестре/корпусе.** План требует включить `run_subagent` «в
  реестр детекторов/tool_registry, как прочие internal-tools» — но по факту
  зависимостей в существующем коде это невозможно одним проходом: пул tools
  субагента = `internal_tools + built-in mcp_tools`, а `mcp_tools` резолвится
  только *после* `_validate_builtin_mcp`, которая сама требует уже готового
  `security_guard` (построенного из `internal_tools` на тот момент — без
  `run_subagent`, которого ещё не существует). Рассмотренные альтернативы:
  (а) не включать `run_subagent` в реестр/корпус вообще — отклонено, прямое
  нарушение буквы плана и реальная брешь: утечка идентификатора/параметров
  `run_subagent` через заражённый tool-результат не будет поймана
  `PairedToolIdentifierDetector`; (б) реструктурировать так, чтобы `mcp_tools`
  резолвились до guard'а — отклонено, сломало бы независимо мотивированный
  порядок «guard должен существовать, чтобы провалидировать remote MCP
  metadata на инъекции» (эта проверка логически обязана идти первой). Выбранное
  решение — helper `_build_security_guard`, вызываемый дважды с переиспользуемыми
  `classifier`/`guard_observer` (не пересоздаются, не задваивают LLM/наблюдатель),
  пересоздаются только зависящие от `tools_for_corpus` части
  (`PairedToolIdentifierDetector`, `FragmentDetector`, `SecurityGuard`).
  Корректность разбиения не эвристическая, а проверена по коду: у
  `PairedToolIdentifierDetector`/`FragmentDetector` `Checkpoint.MCP_METADATA`
  отсутствует в `applies_to` (только `UnicodeDetector` + классификатор туда
  входят) — значит первая (неполная) сборка guard'а функционально идентична
  второй (полной) для единственной проверки, для которой она используется
  (`_validate_builtin_mcp`). Ссылка на первый вызов задокументирована в коде
  (комментарий над первым `_build_security_guard(internal_tools)`), чтобы не
  создать впечатление забытого дублирования при последующем чтении. Это не
  архитектурное решение и не новый контракт — реализационный manoeuvre внутри
  уже одобренного требования плана, эскалации не потребовало.
- **Тексты `description` tool'а (`build_run_subagent_description`) — решение
  сверх буквы плана**, аналогично T1.1: план требует «список тип: описание» +
  инструкцию про большой контекст → артефакт → id, но не дословный текст.
  Написан как продакшн tool-description (английский, explain-why), консистентно
  с `create_artifact`/`system.txt`. Дополнительно явно проговорена семантика
  «всё или ничего» для `input_artifact_ids` прямо в description — не требуется
  планом буквально, но снижает риск, что модель воспримет частичный успех как
  ожидаемое поведение и будет ретраить не так, как нужно.
- **`UnknownSubagentTypeError` ловится в tool, а не отдаётся `handle_tool_errors`
  основного `ToolNode`.** План разделяет два вида ошибок явно: невалидный
  `agent_type` → «ошибка со списком типов» (специфический текст), прочие
  ошибки субагента → generic `handle_tool_errors`. Не документировано отдельно
  как решение, но исполнено буквально по плану — фиксирую здесь, потому что это
  единственное исключение, обрабатываемое внутри tool, а не пробрасываемое
  наружу, и без явного упоминания могло бы выглядеть как несогласованность с
  «пусть летят в handle_tool_errors».
- **`SUBAGENT_TAG` — общая константа в `app.agent.subagents.runner`, а не
  строковый литерал `"subagent"` в обоих местах (Runner, стрим-цикл).** План/бриф
  говорят буквально `"subagent"` как тег, не требуют константы. Решение — чисто
  техническое (один источник истины для тега вместо двух независимо
  поддерживаемых литералов), не меняет наблюдаемое поведение и не вводит новый
  контракт; экспортирована через `app.agent.subagents.__init__`, чтобы стрим-цикл
  импортировал из публичного API пакета, не из внутреннего `subagents.runner`
  напрямую (консистентно с тем, как `main.py` уже импортирует `SubagentRunner`).

- **Guard-хелперы вынесены в новый модуль `app/agent/tool_guards.py`, а не
  импортированы напрямую из `app/agent/graph.py` в `app/agent/subagents/graph.py`,
  как буквально написано в плане/брифе («обе проверки в `graph.py`
  параметризованы guard'ом»).** Первая попытка — прямой импорт
  `from app.agent.graph import _guard_tool_call_args, ...` в
  `subagents/graph.py` — воспроизводимо ловит `ImportError: cannot import
  name '_guard_tool_call_args' from partially initialized module
  'app.agent.graph' (most likely due to a circular import)` при загрузке
  `tests/conftest.py`/`app.main`. Причина — реальный цикл через пакетные
  `__init__.py`, не гипотетический: `app.agent.graph` импортирует
  `app.agent.tools.ks_helpers`, что триггерит выполнение
  `app.agent.tools.__init__` (импорт субмодуля пакета сначала грузит сам
  пакет), которое эагерно импортирует `app.agent.tools.subagents` (T1.3) →
  `app.agent.subagents` (пакет) → `subagents.runner` → `subagents.graph` —
  который до этой правки замыкал цикл обратно на `app.agent.graph`, ещё не
  успевший определить `_guard_tool_call_args` (она ниже по файлу той же
  точки, где `graph.py` начинает импортировать `app.agent.tools.ks_helpers`).
  Рассмотренные альтернативы: (а) оставить прямой импорт и разорвать цикл
  переносом импорта `ks_helpers` внутрь функции (`# circular: ...`) —
  отклонено, размывает границу «новая забота → отдельный коллаборатор»
  (conventions.md) ради обхода, а не устранения зависимости; (б) вынести
  общие хелперы в отдельный модуль без зависимостей на `app.agent.tools` —
  выбрано: `tool_guards.py` зависит только от
  `app.agent.security.guard`/`app.agent.security.types`/`langchain_core`,
  которые не создают цикл ни с `app.agent.tools`, ни с `app.agent.subagents`.
  Функции перенесены дословно (текст/поведение не менялся), только
  переименованы без ведущего underscore (`handle_tool_error`,
  `guard_tool_results`, `guard_tool_call_args`) — они больше не
  module-private детали `graph.py`, а разделяемый контракт двух графов;
  `graph.py` импортирует их обратно и использует как раньше. Формально это
  расходится с буквальным «в `graph.py`» из плана, но реализует ту же цель
  (переиспользуемый guard-код, один источник истины, идентичное поведение) —
  трактовал как реализационную необходимость, а не архитектурную развилку;
  других жизнеспособных мест для этих трёх функций, не создающих цикл, нет
  (`app.agent.security.*` — тоже вариант, но `handle_tool_error` не про
  security per se, а `tool_guards.py` рядом с `graph.py`/`subagents/graph.py`
  читается яснее по локальности использования). Проверено регрессией:
  `tests/agent/test_graph.py` (90 тестов) зелёный без изменений в
  тест-файлах, `import app.main` + `create_app()` строит приложение.
- **`SUBAGENT_RECURSION_LIMIT = 10`, а не значение по умолчанию LangGraph
  (25) и не per-spec конфигурируемое поле.** План/бриф требуют
  `recursion_limit`, но не называют число и не заводят под него поле в
  `SubagentSpec`. Выбор константы, а не спек-поля — план перечисляет только
  `tools`/`model`/`persistence` как per-spec override'ы в T1.1, добавление
  `recursion_limit` в схему `SubagentSpec` — расширение контракта конфига
  сверх плана, не делал. Число `10` — не default LangGraph (`25`), а
  сознательно меньшее значение: делегированная субагенту подзадача — разово
  ограниченный кусок работы (design-brief: «не крутится бесконечно»), а не
  открытый агентский цикл; 10 суперступеней (~5 раундов
  `llm → tools → llm`) — щедро для v1-набора инструментов (3 firecrawl-tool
  на `web-research`), но много ниже LangGraph-дефолта, так что ловит
  зацикливание раньше. Это оценочное число, не выведенное из документа —
  если оно окажется тесным для реальных web-research-сценариев, это
  наблюдаемо (`GraphRecursionError` в логе tool-error) и легко поднять одной
  строкой; фиксирую как решение implementer'а в рамках задачи «ограничь
  цикл», не как архитектурный контракт.
- **`SubagentRunner.__init__` получил `security_guard`/`security_messages`,
  `run(...)` — `canary_token`; main.py передаёт интеримный (не финальный)
  guard.** Ни план, ни T1.3-код не заводили эту проводку — до T1.5 guard
  внутри субагента не использовался, добавлять его раньше было бы
  преждевременным расширением интерфейса. Выбор интеримного guard'а
  (собранного до того, как `run_subagent` добавлен в `internal_tools`,
  см. `_build_security_guard` в T1.3) для конструктора `SubagentRunner` —
  не реордер существующего кода, а использование уже вычисленного на тот
  момент значения `security_guard`; финальный guard (после `run_subagent`
  зарегистрирован) конструируется двумя строками позже и физически не может
  быть готов раньше конструктора `SubagentRunner`, который сам нужен для
  сборки tool'а `run_subagent`, — циклическая зависимость, решённая тем же
  способом и по тем же причинам, что уже описаны для двойной сборки guard'а
  в T1.3. Функционально интеримный и финальный guard эквивалентны для чеков,
  которые выполняет цикл субагента (`TOOL_RESULT`/`TOOL_CALL_ARG` над
  firecrawl-инструментами web-research, не над `run_subagent` — который в
  toolset субагента не попадает по инварианту Runner'а), так что выбор не
  меняет наблюдаемое поведение.
- **`recursion_limit` — invoke-time ключ `RunnableConfig`, не параметр
  `compile()`.** План формулирует буквально «проброс в `config`/`compile`»,
  оставляя выбор на усмотрение implementer'а («реши по фактическому API»).
  Проверено `inspect.signature(Pregel.ainvoke)` и
  `typing.get_type_hints(RunnableConfig)` — `recursion_limit` есть в
  `RunnableConfig` (наравне с `tags`/`metadata`/`callbacks`), `compile()`
  такого параметра не принимает. `SubagentRunner.run` добавляет его в
  `run_config` рядом с `tags`, не трогая `compile_subagent_graph`.

- **T1.7 — общая механика judge-прохода описана один раз (под п. 3 Шага 5),
  cold-reader (п. 5) ссылается на неё вместо повторения полного текста.**
  Альтернатива — продублировать `create_artifact` → `run_subagent(...)` в
  обоих пунктах явно — отклонена: исходный текст `SKILL.md` уже был построен
  так (правило «для ВСЕХ judge-проходов» вынесено под п. 3, п. 5 не повторял
  его), правка сохраняет эту структуру и минимизирует дифф, вместо того
  чтобы вводить повтор там, где скилл до правки его не имел. Единственное,
  что п. 5 добавляет поверх общей механики, — дисциплину одного документа в
  `input_artifact_ids`, специфичную для cold-reader.

- **Fix (fixer, attempt 1): неверные имена firecrawl-tools в `agent.yaml` —
  boot-blocker, вскрытый fail-fast'ом.** Ручной прогон трека упёрся в
  `RuntimeError: subagents config error — unknown tool name(s) in registry:
  web-research: firecrawl_scrape_url, firecrawl_extract_data` — приложение не
  стартовало. Первопричина двусоставная. (1) `mcp_servers.firecrawl.allowed_tools`
  содержал неверные имена `firecrawl_scrape_url`/`firecrawl_extract_data` **до
  feat-011** — git-археология (`git blame`) показывает, что allowlist пришёл
  коммитом `d29efda` (feat-003, runtime agent configuration, апрель 2026), задолго
  до этого трека. Основной граф жил с этим тихо: резолвер MCP-tools фильтрует
  пересечением (`main.py`: `tools = [t for t in tools if t.name in allowed]`), а
  реальные имена сервера — `firecrawl_scrape`/`firecrawl_extract`, поэтому оба
  просто отсеивались, и у основного агента из трёх заявленных firecrawl-tools
  фактически работал только `firecrawl_search` — молча, без ошибки. Это дрейф
  конфига против реального MCP-сервера, исправляемый по ходу. (2) Спека
  `web-research` (T1.1, этот трек) скопировала те же неверные имена в `tools`, и
  здесь они уже не могли отсеяться тихо: `_validate_subagent_tool_pool` (T1.3) —
  fail-fast, который требует резолва **каждого** имени из спеки в пуле; пул после
  фильтрации allowlist'ом содержал только `firecrawl_search`, поэтому два имени
  web-research не резолвились и валидатор аварийно валил boot. То есть новая
  проверка feat-011 вскрыла латентный дефект, который раньше не проявлялся.
  **Фикс:** `firecrawl_scrape_url` → `firecrawl_scrape`, `firecrawl_extract_data`
  → `firecrawl_extract` во всех четырёх вхождениях `configs/agent.yaml` (спека
  `web-research` + `allowed_tools`). Реальные имена подтверждены tester'ом запросом
  `tools/list` к `https://mcp.firecrawl.dev/mcp`. Больше нигде в `configs/` эти
  имена не встречались (seed-промпт `subagent-web-research.txt` их не упоминает).
  Публичный контракт не менялся — только строковые значения имён; ни код, ни тесты
  на старые имена не завязаны (валидатор — общий, имена читает из конфига). **Ре-
  верификация:** честный full-boot (`make dev`, реальный fetch `tools/list`, БД на
  `:5433`) — `mcp tools loaded tool_count=3` (все три firecrawl-tool теперь
  проходят allowlist, было бы 1 до фикса), `run_subagent tool registered
  tool_pool_size=12`, `Application startup complete` без RuntimeError; `make check`
  и `make test-scope P=backend/tests/subagents` (31 passed) — зелёные.
  `plan.md:37` содержит те же неверные имена — исторический артефакт, не
  трогался.

- **Docs-updater: B3 исправлен, acknowledged-дрейф закрыт точечно, новый документ не заводился.**
  `doc/tech/adr/ADR-028-product-subagents.md:11` — `firecrawl_scrape_url`/
  `firecrawl_extract_data` заменены на актуальные `firecrawl_scrape`/
  `firecrawl_extract` (review-b nit). `design-brief.md:5,132` (итерационный
  артефакт) не тронут — те же устаревшие имена там исторически допустимы
  (review-b это прямо разрешает). Acknowledged-дрейф из review-b закрыт без
  нового документа: субагенты — расширение существующего agent runtime, не
  новый архитектурный концепт (workflow.md § 4.2 — нет ни кросс-сервисности,
  ни отдельного жизненного цикла сверх того, что уже фиксирует ADR-028), а
  ADR уже существует. Добавлен раздел «Субагенты» в `agent-runtime.md`
  (после `MCP Integration`, до `Security`) — паттерн, слоистость
  `SubagentSpec`/`SubagentRunner`/tool, диаграмма потока (`agent node → tool
  run_subagent → SubagentRunner → Subagent StateGraph`, стиль без
  layer-подложек — консистентно с уже существующими диаграммами этого файла,
  напр. «Agent Graph»), обе формы графа (toolless/ReAct), состав tool-пула,
  persistence-режимы, наблюдаемость — со ссылками на ADR-028 и точечными
  доками, без дублирования таблиц отклонённых альтернатив ADR. `## Tools` —
  «Четыре категории» → «Пять», добавлена подсекция `Subagents` (`run_subagent`
  → ссылка на новый раздел); `## Configuration` — строка `subagents` в
  таблице секций `agent.yaml`. Точечные правки в четырёх доках: `prompt-
  management.md` (три строки Prompt Inventory для `subagent-*` + `subagents.
  llm` в списке файлов конфигурации); `streaming.md` (абзац в подсекции
  `AgentRunner` про фильтр по тегу `subagent`, до накопления `full_response`);
  `observability.md` (предложение в `## Tracing` про вложенные span'ы
  независимо от `persistence`); `security/architecture.md` (новая короткая
  секция «Субагенты: переиспользование границы» перед `## Observability` —
  граница на входе через существующие checkpoint'ы, переиспользование guard'а
  внутри ReAct-цикла, состав tool-пула без user-installed MCP; ADR-028
  добавлен в «Связанные документы»). `doc/index.md` не менялся — ADR-028 не
  вынесен отдельной строкой в навигации по тому же принципу, по которому там
  уже отсутствуют ADR-022/023/024/026/027 (список ADR в index.md выборочный,
  не исчерпывающий; feat-011 эту практику не меняет). Tasklist § feat-011
  «Документация» дополнен ссылками на `tracks/T1/{plan,summary,test-cases}.
  md`, `review-a.md`, `review-b.md`, `harvest-proposals.md`, ADR-028 — по
  образцу записи feat-010.
- **Не чинил (не дрейф, осознанное ограничение инструмента, уже
  задокументированное выше в этом файле):** `sync_prompts.py::
  _update_agent_yaml` не пишет обратно `model`/`extra_body` для `subagent-*`
  промптов в `configs/agent.yaml` (ветки `if/elif` не покрывают эти три
  имени) — текст промпта синкается исправно, конфиг-часть остаётся
  ограничением существующего скрипта. `prompt-management.md` описывает
  sync обратный путь в общей форме («Обновляет `configs/agent.yaml`»), не
  перечисляя built-in исключения по промпту — специфика уровня одного
  скрипта, не архитектурный контракт; не стал вводить в доку оговорку ради
  детали реализации одного инструмента синхронизации.

## Follow-ups

## SOFA-посты (id / применил / результат)
