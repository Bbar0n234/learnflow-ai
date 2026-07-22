# Test Cases: feat-011 — Продуктовые субагенты v1 / трек T1

Трек T1 — весь scope итерации: механика **subagent-as-tool**. Основной ReAct-агент
делегирует подзадачу изолированному субагенту через tool `run_subagent`; субагент —
отдельный скомпилированный граф со своим state, наружу уходит только результат. Кейсы
ниже страхуют **новую фичу** (не поведение-сохраняющий рефактор): что судья возвращает
вердикт по чистому входу, что история сессии в субагент не утекает, что вход по
референсу работает «всё или ничего», что guard-переиспользование внутри субагентского
цикла редактирует заражённую страницу (новая attack-поверхность), и что токены
субагента не рисуются в чат. Отдельная страховка — рефактор выноса guard-хелперов в
`tool_guards.py` (T1.5) не сломал основной граф: закрыта существующим `tests/agent/`
(90 тестов, прогнаны — зелёные).

Тестовый скоуп — `backend/tests/subagents/` (scope_id = `subagents`). Прогон:
`make test-scope P=backend/tests/subagents`.

## Конвенции прохождения (инлайн — это рамка тестировщика)

**Статус и run-log.** У каждого кейса — текущий статус плюс опциональный run-log, если кейс прогонялся не раз:

- `- [x]` + лаконичный результат: что проверялось, что получилось, значимые нюансы. По заполненному чек-листу должно быть видно, что всё работает, без перепрохождения.
- `- [ ] ⚠️` + причина, если кейс не пройден или требует отдельного внимания.
- Кейсы с 👤 — требуют ручного действия / решения архитектора (UI, браузер); тестировщик помечает и эскалирует.
- **Доменные маркеры**: `📊` — проверка наблюдаемости (структура БД, метрики, Redis state, Langfuse); `🔴` — проверка реальных инъекций / атак / security-событий; `[auto]` — кейс закрыт автотестом (живёт в `tests/subagents/`); `*(регресс)*` — кейс страхует «поведение не сломалось».
- **run-log** (только у перепрогнанных кейсов): `runs: r1 ✅ → r2 ❌ (причина) → r3 ✅`.

**Ре-верификация.** Правка кода аннулирует прошлый зелёный статус затронутого. После фиксов: детерминированный гейт (`make check`/`make test-scope`) — перепрогон всегда; ручные/UI-кейсы — перепрогон только затронутой области.

**Диагностика — через наблюдаемость, не догадки.** Один кейс — одна попытка диагностики; не сошлось второй раз — fail + эскалация. Код тестировщик не правит: прод-баги, вскрытые кейсом, чинит **fixer** (не сам тестировщик).

**Скоуп по трекам.** Кейсы с префиксом трека (`{T1.x}`) гоняются на своём треке + Layer 0; cross-cutting (Layer 2/3 без префикса) — в INTEGRATION_TEST.

### Процесс (тестировщик поднимает стенд сам)

1. Инфраструктура: `make docker-up-db` (Postgres + Redis), `make migrate`, backend `make dev`, фронт `make dev-fe` — либо `make docker-up` целиком. Для ручного прогона субагентов нужен живой LLM-ключ (`LLM_API_KEY`) и, для web-research, firecrawl MCP.
2. Акторы через UI register / `/api/auth/register`: **user-a** (обычный, с проектом и артефактами).
3. Прогон сверху вниз; каждый failed-кейс — повторная попытка, затем фиксация в run-log.
4. После прогона — сводка (pass / failed / **deferred**). Deferred — 👤/заблокированные (нет ключей, занят стенд).

### Где смотреть состояние

| Что | Место |
|-----|-------|
| Фронт | `http://localhost:5173` (Vite) |
| Main app | `http://localhost:8000`, structlog stdout |
| Сеть / SSE | DevTools → Network |
| Langfuse | вложенные span'ы субагента (токены, стоимость) |

---

## Дизайн автотестов

Автотесты живут в `backend/tests/subagents/` (31 тест, все зелёные). Общий тест-фундамент
(`packages/testing`: `StubGuard`/`fake_chat_model` не понадобились — субагентские фейки
специфичны и живут в scope-conftest; переиспользованы `ProjectFactory`/`bind_session` и
транзакционный harness) и conftest-иерархия — не тронуты (заморожены). Модельный и
guard-швы закрыты детерминированными фейками; реальный Postgres поднимается только под
fetch артефактов tool'ом. Живого LLM/сети нет нигде.

**Покрываем автотестом:**

### `test_runner.py` — SubagentRunner.run (ядро subagent-as-tool)

1. **Файл**: `tests/subagents/test_runner.py` — unit, шов модели (`create_llm_from_config`
   монкипатчится на `CapturingModel`), реальный toolless-граф; часть кейсов — на spy-графе
   (`compile_subagent_graph` подменён), чтобы наблюдать `ainvoke`-config.
2. **Тестирует**: `app.agent.subagents.runner :: SubagentRunner`
3. **Суть**: проверяет, что Runner собирает вход субагента строго из `task` + документов и
   ничего кроме (система = промпт спеки, human = task + документы в обёртке с id/title),
   что история сессии туда не попадает, что модель резолвится по каскаду «per-spec override
   → дефолт `subagents.llm`», что промпт берётся через PromptProvider, и что Runner
   штампует тег `subagent` и `recursion_limit` на config и компилирует с
   `checkpointer=False` при `persistence: none`. Отдельно фиксирует анти-рекурсивный
   инвариант: `run_subagent` вычищается из пула инструментов субагента.
4. **Кейсы**:
   - judge: система = ровно промпт спеки (маркер `PROMPT[subagent-judge]`, без KS/memory/skills), human = `task` + документ в обёртке `<document id=".." title="..">`; результат = финальный текст графа `[auto]`
   - вход = ровно `[SystemMessage, HumanMessage]` — история сессии не утекает `[auto]`
   - порядок документов сохранён; кавычки в `title`/`id` экранируются в `&quot;` `[auto]`
   - без документов — human = только `task` `[auto]`
   - неизвестный `agent_type` → `UnknownSubagentTypeError` со **сортированным** списком типов `[auto]`
   - модель: дефолт `subagents.llm.model`, когда у спеки нет override `[auto]`
   - модель: per-spec `model`-override побеждает `[auto]`
   - config: тег `subagent` добавлен без потери тегов/metadata вызывающего; `recursion_limit = SUBAGENT_RECURSION_LIMIT` `[auto]`
   - `persistence: none` → `compile(checkpointer=False)` — ноль записей в PG `[auto]` 📊
   - анти-рекурсия: `run_subagent` исключён из пула (спека, требующая его, не резолвится — `KeyError`) `[auto]`

### `test_graph.py` — субагентский граф: обе формы + guard внутри цикла

1. **Файл**: `tests/subagents/test_graph.py` — unit, фейк-модель (`ScriptedToolModel`/
   `InfiniteToolCallModel`) + `SelectiveGuard`-стаб на плоском вердикте, `checkpointer=False`.
2. **Тестирует**: `app.agent.subagents.graph :: build_subagent_graph`
3. **Суть**: проверяет, что пустой toolset даёт вырожденную одноузловую форму (llm без tools),
   а непустой — ReAct-цикл `llm → tools → llm → END`; и что внутри ReAct-цикла
   переиспользованный guard реагирует на вердикт с fail-safe redact-семантикой — заражённый
   результат инструмента (страница) редактируется заглушкой и **цикл продолжается**,
   инъекция в args инструмента срезает `tool_calls` (tools-узел не запускается), а CLEAN и
   SUSPICIOUS пропускают инструмент без редакции. Ограничение цикла — `recursion_limit`.
4. **Кейсы**:
   - toolless-форма: узел `llm` есть, узла `tools` нет; один LLM-ответ `[auto]`
   - ReAct-форма: узлы `llm` + `tools`; полный цикл `human→ai(tool_call)→tool→ai(final)` `[auto]`
   - 🔴 заражённая страница (`TOOL_RESULT` → INJECTION): контент ToolMessage заменён заглушкой, `security_redacted=True`, цикл дошёл до финального ответа `[auto]`
   - 🔴 инъекция в args (`TOOL_CALL_ARG` → INJECTION): `tool_calls` срезаны, tools-узел не выполнялся, `security_redacted=True` `[auto]`
   - CLEAN → инструмент выполняется штатно `[auto]` *(регресс поведения основного графа на новом узле)*
   - SUSPICIOUS на args → редакции нет, инструмент выполняется `[auto]`
   - `security_guard=None` → fail-open: заражённая страница доходит до модели без редакции `[auto]`
   - `recursion_limit` ограничивает бесконечный цикл tool_calls → `GraphRecursionError` `[auto]`

### `test_run_subagent_tool.py` — tool-обёртка: fetch «всё или ничего» + трансляция ошибок

1. **Файл**: `tests/subagents/test_run_subagent_tool.py` — integration, реальный Postgres
   (`tool_session_factory` на транзакционном откате, как в image-generation scope); Runner
   заменён recording-`SpyRunner` (его работа — модель/граф — покрыта в `test_runner.py`).
   Драйв через `tool.coroutine(...)` со сконструированным `ToolRuntime` (паттерн из
   `tests/image_generation/test_generate_image_tool.py`).
2. **Тестирует**: `app.agent.tools.subagents :: make_run_subagent_tool`
3. **Суть**: проверяет, что tool достаёт артефакты по `input_artifact_ids` с проектным
   скоупом и семантикой «всё или ничего» — любой чужой, несуществующий или невалидный-UUID
   id проваливает **весь** вызов (error-строка перечисляет только проблемные id, Runner не
   запускается), а валидный набор доходит до Runner байт-в-байт с атрибуцией id/title. Плюс
   трансляцию `UnknownSubagentTypeError` в error-строку (граф не падает), проброс
   `runtime.config`/canary в Runner и `RuntimeError` при отсутствии `AgentContext`.
4. **Кейсы**:
   - неизвестный `agent_type` → error-строка со списком типов (не исключение наружу) `[auto]`
   - валидный артефакт → доходит до Runner как `SubagentDocument(id, title, content)` байт-в-байт `[auto]`
   - 🔴 чужой project_id + невалидный UUID в списке → error перечисляет только их, валидный id не назван, Runner **не** вызван (всё или ничего) `[auto]`
   - несуществующий id → error, Runner не вызван `[auto]`
   - без `input_artifact_ids` → Runner получает `documents == []` `[auto]`
   - `runtime.config` и `canary_token` проброшены в `Runner.run` `[auto]`
   - `runtime.context is None` → `RuntimeError` `[auto]`

### `test_stream_isolation.py` — изоляция токенов субагента в стриме

1. **Файл**: `tests/subagents/test_stream_isolation.py` — sociable-unit, реальный
   `LangGraphAgentRunner` + фейк-граф (`_FakeGraph.astream` отдаёт скриптованную смесь
   `messages`/`updates`), guard выключен (`RuntimeSecurityEnforcer(guard=None)` — все чек-пойнты
   no-op), Langfuse off.
2. **Тестирует**: `app.agent.runner :: LangGraphAgentRunner.stream` (ветка фильтрации по тегу)
3. **Суть**: проверяет, что чанки LLM, помеченные тегом `subagent`, отбрасываются из
   `text_chunk`/`full_response` до аккумуляции, а токены основного агента стримятся штатно;
   индикация работы субагента (`tool_start`/`tool_end` из `updates`) при этом продолжает
   идти. Тест бьёт по коду фильтра напрямую — независимо от того, что дефолт LangGraph
   (`subgraphs=False`) уже прячет эти чанки (см. summary T1.4).
4. **Кейсы**:
   - tagged-чанки (в т.ч. с посторонним тегом `seq:step:3` в списке) выброшены; `text_chunk` = только основной агент (`"Hello world"`) `[auto]`
   - `tool_start`/`tool_end` для `run_subagent` проходят, пока токены субагента фильтруются `[auto]`

### `test_tool_pool_validation.py` — fail-fast валидация имён tool на старте

1. **Файл**: `tests/subagents/test_tool_pool_validation.py` — solitary-unit, чистая функция
   над `dict[name → tool]`.
2. **Тестирует**: `app.main :: _validate_subagent_tool_pool`
3. **Суть**: проверяет, что неизвестное имя tool в любой спеке валит старт приложения
   (`RuntimeError`), а не всплывает лениво на первом вызове; все проблемные спеки
   агрегируются в одном сообщении; полностью резолвящийся реестр проходит.
4. **Кейсы**:
   - все имена резолвятся → без исключения `[auto]`
   - неизвестное имя → `RuntimeError` с именем спеки и tool `[auto]`
   - несколько проблемных спек → все в одном сообщении `[auto]`

**Осознанно не покрываем автотестом:**

- **Композиция пула субагентов в `main.py` lifespan (user-installed MCP исключены; пул =
  `internal_tools + built-in mcp_tools`)** — чистый glue-wiring внутри `lifespan`, требует
  реального Postgres/Redis и порядка сборки guard'а (двойная сборка, см. summary T1.3);
  бизнес-ветвлений нет → мягкий гейт glue. Инвариант «user MCP не в пуле» — следствие
  композиции, а не отдельной функции → ручной кейс `{T1.5-mcp}` (Layer 2, требует живого
  user-MCP). Fail-fast-часть композиции (валидатор) покрыта юнитом отдельно.
- **`persistence: inherit` (checkpointer=None, наследование родительского PG-чекпойнтера)** —
  ни одна v1-спека его не использует (все `none`); ветка компиляции существует как
  extension point → включится первым HITL-потребителем, тогда и integration-кейс. Автотест
  на неиспользуемую ветку был бы false-green.
- **Качество вердикта judge / точность guard на реальных атаках / качество выжимки
  web-research** — это **eval**, не unit (`testing.md` § Граница unit/eval): недетерминированный
  живой LLM под строгим `assert ==` даёт флак → eval-контур в backlog, вне CI-гейта. →
  ручной приёмочный хвост `{T1.1}`/`{T1.4}`.
- **Вложенные Langfuse-span'ы субагента (токены/стоимость через проброс callbacks)** —
  наблюдаемость на живом трейсинге; фильтр по тегу callbacks не трогает (проверено, что
  фильтр их не ломает — юнит стрима), но сам факт вложенного span'а виден только в живом
  Langfuse → ручной кейс `{T1.4-obs}` 📊.
- **End-to-end judge/web-research через реальную модель (скилл статей: черновик →
  `create_artifact` → id судье)** — сквозной путь с живым LLM и firecrawl → ручной
  Layer 2/3.

**Замеченные прод-баги (для fixer'а, сам не чиню):** нет. Наблюдаемое поведение совпадает
с контрактом брифа во всех покрытых точках.

### Layer 0: Automated gate

- [x] `make check` — ruff + mypy + arch-checker → **0 ошибок** (mypy проверяет `backend/tests`; все фейки типизированы/каст явный).
- [x] `make test-scope P=backend/tests/subagents` — 31 тест зелёный.
- [x] `make test-scope P=backend/tests/agent` — 90 тестов зелёные *(регресс: рефактор `tool_guards.py` не сломал основной граф)*.

---

## Ручные кейсы + статусы

Узкий ручной хвост — то, что не закрыто автотестом (живой LLM/firecrawl, Langfuse,
сквозной UX). Статусы и run-log ведут tester/fixer.

### Layer 1: Трек T1 — субагенты v1

> ⚠️ **БЛОКЕР при boot (эскалировано fixer'у, [prod]).** С поставленным `configs/agent.yaml`
> приложение **не стартует**: fail-fast `_validate_subagent_tool_pool` падает —
> `RuntimeError: subagents config error — unknown tool name(s) in registry: web-research:
> firecrawl_scrape_url, firecrawl_extract_data`. Причина: спека `web-research` и allowlist
> `mcp_servers.firecrawl.allowed_tools` ссылаются на **несуществующие** имена firecrawl-tools.
> Реальные имена MCP-сервера firecrawl (проверено запросом `tools/list` к
> `https://mcp.firecrawl.dev/mcp`): `firecrawl_scrape` и `firecrawl_extract` (не
> `firecrawl_scrape_url`/`firecrawl_extract_data`; `firecrawl_search` — верно). Те же неверные
> имена — в `plan.md:37`. Валидатор отработал корректно (это как раз Layer 2 fail-fast) —
> ловит реальный дефект конфига. **Чтобы прогнать ручной хвост, тестировщик временно
> локально исправил оба имени** (`_scrape_url`→`_scrape`, `_extract_data`→`_extract`) в
> `agent.yaml` (в спеке и в allowlist), поднял стенд, прогнал кейсы, **затем откатил правку** —
> дерево оставлено как поставлено (боевой фикс — за fixer'ом). Все статусы `{T1.x}` ниже
> получены на исправленном конфиге; с поставленным конфигом стенд не поднимается вовсе.

- [x] `{T1.1}` 🔴 judge-проход анти-слопа: user-a сохраняет черновик статьи через
  `create_artifact`, агент вызывает `run_subagent("judge", task=<инструкция анти-слоп-скана>,
  input_artifact_ids=[<id>])` → в ответ приходит вердикт **с evidence** (цитаты/ссылки на
  места текста, не голое summary); цитаты бьются с черновиком байт-в-байт. Требует живого LLM.
  — **PASS.** user-a (`demo`) сохранил черновик «Draft: Async Python» через `create_artifact`
  (id `94443899-db9c-4f83-949e-c7f7be01aaa0`; SSE `artifact_created`). `run_subagent("judge",
  input_artifact_ids=[id])` → вердикт с evidence: 7 findings, каждый с точной verbatim-цитатой
  из черновика («In today's fast-paced world…», «It's important to note that async is not a
  silver bullet», «At its core…», «Let's delve into a concrete example», «In conclusion…»,
  «tapestry … woven together thoughtfully», «modern developer») + разбор «почему slop» — не
  голое summary. Все цитаты сверены с сохранённым artifact-контентом — байт-в-байт. Evidence
  ссылается на документ по id (`<document id=94443899…>`) — XML-атрибуция обёртки работает.
  Субагент: `model=glm-4.7-flash`, `tool_count=0` (toolless), `persistence=none`, 34s.
  Langfuse trace `ce435f8c`.
- [x] `{T1.2}` cold-reader-проход: тот же артефакт, `task=<инструкция cold-reader>`,
  дисциплина одного документа в `input_artifact_ids` → вердикт про недосказанность; в вход
  судьи не попали ни история сессии, ни ресёрчи (чистота «свежих глаз») — проверяется по
  Langfuse-инпуту вложенного span'а. Требует живого LLM.
  — **PASS.** Тот же артефакт `94443899…`, `task=<cold-reader>`, `input_artifact_ids=[один id]`
  (лог субагента `document_count=1` — дисциплина одного документа). Вердикт про недосказанность:
  8 findings про assumed knowledge / неопределённые термины (coroutine, event loop, I/O-bound,
  `fetch(url)`, CPU-bound, concurrency), каждый на verbatim-цитате. Чистота «свежих глаз»
  проверена по Langfuse-инпуту вложенного span'а: вход субагента = ровно `[system, user]` —
  система = только промпт-спека judge, user = `task` + один `<document id=… title=…>`; истории
  сессии нет (baseline-turn «pong» в инпуте отсутствует), ресёрчей нет. Langfuse trace `a8963ad4`.
- [x] `{T1.3}` web-research end-to-end: `run_subagent("web-research", task=<ресёрч-запрос>)`
  → субагент ходит firecrawl-инструментами, наружу возвращает выжимку **с источниками**;
  страницы не попали в контекст основного агента (в чате их токенов нет). Требует firecrawl
  MCP + живой LLM.
  — **PASS.** `run_subagent("web-research", task=<latest stable Python version>)` → субагент
  реально ходил firecrawl (в Langfuse-трейсе `9c20ad0f` TOOL-вызовы `firecrawl_search` +
  `firecrawl_scrape`; ReAct-цикл ~210s, лог `tool_count=3`), наружу вернул выжимку с 4
  официальными источниками (python.org/downloads, .../release/python-3146, blog.python.org,
  docs.python.org changelog). Страницы **не** попали в контекст основного агента: 0 `text_chunk`
  между `tool_start`/`tool_end` `run_subagent`; в чат ушла только финальная выжимка (46 чанков),
  без контента скрейпленных страниц.
- [x] `{T1.4}` 📊 изоляция токенов в живом UI: во время рана субагента в чате не рисуются
  его токены (DevTools → Network SSE: нет `text_chunk` от субагента), но виден
  `tool_start`/`tool_end` для `run_subagent`; отмена во время рана субагента отзывчива.
  — **PASS (SSE-слой, проверен curl'ом — браузера нет).** Изоляция: во всех прогонах с
  субагентом (judge/cold-reader/web-research) **0** `text_chunk` между `tool_start` и `tool_end`
  `run_subagent` — токены субагента в чат не текут; `tool_start`/`tool_end` для `run_subagent`
  присутствуют. Отмена: POST `/cancel` дёрнут ровно в момент `tool_start` `run_subagent`
  (HTTP 200) → поток корректно завершился `error: "Request was cancelled."`, без зависания.
  Латентность ~27s после cancel = субагент (блокирующий `ainvoke` внутри tool) досчитывал;
  `cancel_event` проверяется на границе итерации основного графа, поэтому отмена во время рана
  субагента вступает в силу по возврате субагента (sync v1, задокументировано в ADR-028), а не
  мгновенно mid-subagent — это ожидаемо, поток не виснет. 👤 **Остаток архитектору:** живой
  UI/DevTools (визуальный индикатор набора, прекращение спиннера отмены) — только в браузере.
- [x] `{T1.4-obs}` 📊 наблюдаемость: запуск субагента виден в Langfuse **вложенным span'ом**
  с токенами и стоимостью (проброс callbacks через contextvars); при `persistence: none` в
  PG нет чекпойнт-записей субагентского thread'а.
  — **PASS.** В Langfuse запуск субагента виден вложенными span'ами с тегом `subagent`:
  `CHAIN LangGraph`/`CHAIN llm` + `GENERATION ReasoningChatOpenAI model=glm-4.7-flash` с
  токенами (`usage` input/output) и стоимостью (напр. judge-run: input=642/output=2338,
  cost=0.00124925) — callbacks проброшены через contextvars, субагент считается на своей модели
  glm-4.7-flash (основной агент — glm-5). PG: после всех субагентских прогонов (judge×3,
  cold-reader, web-research) в таблице `checkpoints` только thread_id основных чатов (4 моих +
  2 seed) — **ни одной** чекпойнт-записи субагентского thread'а (`persistence=none` →
  `compile(checkpointer=False)`, ноль записей).
- [x] `{T1.5-mcp}` trust-граница: user-installed MCP-инструмент **не** доступен субагенту
  web-research (в его toolset только built-in firecrawl). Требует установленного
  user-MCP-сервера у user-a.
  — **PASS (прямое доказательство).** На чат установлен user-MCP `deepwiki`
  (`https://mcp.deepwiki.com/mcp`, tools: `read_wiki_structure`/`read_wiki_contents`/
  `ask_question`; `/test` → connect OK). Запущен `run_subagent("web-research")`. В Langfuse
  (trace `9c20ad0f`): у всех 4 субагентских `GENERATION` (тег `subagent`, glm-4.7-flash)
  bound-toolset — **только** `firecrawl_*`; deepwiki-имён нет ни в одном. У основного агента
  (glm-5) в bound-toolset — и deepwiki, и firecrawl. Лог старта субагента: `tool_count=3`
  (ровно firecrawl_search/scrape/extract), не 6. Структурно: `subagent_tool_pool` собирается
  на старте из `internal_tools + built-in mcp_tools` (`main.py:481`, лог «run_subagent tool
  registered tool_pool_size=12»); user-MCP резолвится позже per-request через `MCPToolResolver`
  (`main.py:549`) и попадает только в основной граф. Trust-граница соблюдена.

### Layer 2: Integration (cross-cutting, в INTEGRATION_TEST)

- [x] Старт приложения с реальными `configs/agent.yaml`: секция `subagents` разбирается,
  `run_subagent` зарегистрирован в `tool_registry`/`fragment_corpus` guard'а как прочие
  internal-tools; при подмене имени tool в спеке на несуществующее — приложение падает на
  старте (fail-fast). *(валидатор покрыт юнитом; здесь — реальный boot)*
  — **PASS.** Boot с поставленным (fixer-фиксом закрытым) `configs/agent.yaml` проходит:
  `mcp tools loaded tool_count=3` (реальные имена firecrawl_search/scrape/extract резолвятся),
  затем второй `security guard initialized` показывает `corpus_items` 11→12 и
  `tool_registry_size` 9→10 — `run_subagent` попал и в `fragment_corpus`, и в `tool_registry`
  наравне с прочими internal-tools; `run_subagent tool registered tool_pool_size=12`,
  `Application startup complete.` Fail-fast: временная подмена `firecrawl_scrape`→
  `firecrawl_scrape_BOGUS` в `tools` спеки web-research (на копии, откачена) → boot прерывается
  `RuntimeError: subagents config error — unknown tool name(s) in registry: web-research:
  firecrawl_scrape_BOGUS` → `Application startup failed. Exiting.` Валидатор назвал спеку и
  проблемный tool. Правка откачена, `git diff configs/` пуст.
- [x] Ошибка субагента (модельный сбой / `recursion_limit`) транслируется через
  `handle_tool_errors` основного `ToolNode` в generic error-ToolMessage — основной граф
  **продолжает** работу, тред не падает.
  — **PASS (модельный сбой; least-invasive, детерминированно).** Спровоцировано временным
  per-spec override `judge.model: z-ai/nonexistent-model-xyz-BOGUS` (на копии, откачено; boot с
  ним проходит — модель валидируется на вызове, не на старте). Drove demo/demo: агент вызвал
  `run_subagent("judge", input_artifact_ids=[94443899…])`; богус-модель субагента подняла
  `BadRequestError` в `subagents/graph.py :: llm_node` → исключение прошло сквозь tool
  `run_subagent` (там ловится только `UnknownSubagentTypeError`) → `handle_tool_error` основного
  `ToolNode` (`app.agent.tool_guards`) залогировал `tool execution failed error_type=BadRequestError`
  с exc_info и вернул generic `_TOOL_ERROR_MESSAGE` как `ToolMessage(status="error")`. Основной
  граф **продолжил**: SSE отдал `tool_start`→`tool_end` для `run_subagent`, затем `text_chunk`
  («Let me try the review again:») — тред не упал, ни `error`, ни `security_block` в стриме нет.
  Правка откачена, `git diff` пуст. *(Ветку `recursion_limit`→`GraphRecursionError` отдельно не
  гонял — модельный сбой честнее и детерминированнее; трансляция `recursion_limit` покрыта
  автотестом `test_graph`, а трансляция ошибки наружу — этим кейсом.)*

### Layer 3: E2E (cross-cutting, в INTEGRATION_TEST)

- [ ] 👤 Сквозной сценарий скилла `tech-article-writing`: автор доводит черновик до
  judge-проходов через артефакт, получает вердикты, правит текст, пересохраняет артефакт
  (версий нет — нужен новый `create_artifact`), повторяет проход. Проверка UX-цельности.
  — 👤 **DEFERRED архитектору (UX-приёмка человеком).** Сам не проходил — кейс про цельность
  UX-петли скилла в живом UI, машинно не верифицируется. **Prerequisites (проверено машинно):**
  judge возвращает вердикт с evidence на артефакт-входе — `{T1.1}` PASS; дисциплина одного
  документа + чистота «свежих глаз» (в вход судьи не течёт история/ресёрчи) — `{T1.2}` PASS;
  сохранение черновика через `create_artifact` (SSE `artifact_created`) — `{T1.1}` PASS; изоляция
  токенов субагента в стриме — `{T1.4}` PASS. **Остаётся человеку:** сквозная UX-цельность петли
  (автор → judge-проход → правка текста → пересохранение новым `create_artifact`, версий нет →
  повторный проход) в браузере — визуальная связность, удобство, отсутствие мёртвых состояний.

---

## Находки ревью [severity+owner]

**Легенда владельца:** `[test]` — фикс за test-author · `[infra]` — за packages/testing · `[prod]` — прод-баг, за fixer (+эскалация) · `[doc]` — документация.

**Итог:** major — нет; один blocker [prod] (F1) — вскрыт ручным прогоном, закрыт fixer'ом. Фейки честны, контракт совпадает, независимость A6 соблюдена (в диффе тронута только untracked-директория `backend/tests/subagents/`; `git diff HEAD --stat` по `backend/tests/`+`packages/testing/` пуст). Ниже — F1 плюс два minor-замечания.

- **F1 blocker [prod]** `configs/agent.yaml` — спека `web-research` (`subagents.registry`) и `mcp_servers.firecrawl.allowed_tools` ссылались на несуществующие имена firecrawl-tools (`firecrawl_scrape_url`/`firecrawl_extract_data`); fail-fast `_validate_subagent_tool_pool` корректно валил boot. Реальные имена (tools/list к `https://mcp.firecrawl.dev/mcp`): `firecrawl_scrape`/`firecrawl_extract`.
  - ✅ **Закрыто (fixer, attempt 1):** оба имени исправлены во всех 4 вхождениях `agent.yaml` (спека + allowlist); честный boot проходит (`mcp tools loaded tool_count=3`, `run_subagent tool registered`, `Application startup complete`), `make check` + `make test-scope P=backend/tests/subagents` (31 passed) зелёные.
- **R1 minor [infra]** `backend/tests/subagents/conftest.py:216-257` — транзакционный harness `outer_conn`/`_bound_session`/`tool_session_factory`/`seed_session` скопирован дословно из `backend/tests/image_generation/conftest.py:41-79` (сверено: идентичны). Вариант «несколько sibling-сессий на одном outer-conn» нужен обоим scope'ам, потому что tool открывает собственную сессию через инжектируемую фабрику — обычный `learnflow_testing.db.transactional_session` отдаёт лишь одну сессию и закрывает свой conn, поэтому не подходит. Дублирование здесь intra-package и scope-локальное (осознанный трейд-офф ради параллельного авторинга, задокументирован в шапке conftest), потому minor, не major. → Предлагаемый фикс: вынести connection-sharing-вариант рядом с `transactional_session` в `packages/testing/learnflow_testing/db.py` (напр. фабрика sibling-сессий на общем conn), чтобы image-generation и subagents делили одну реализацию вместо copy-paste, который со временем разъедется.
- **R2 minor [test]** `backend/tests/subagents/test_stream_isolation.py:37` — `pytestmark = pytest.mark.integration`, но тест не поднимает реальную инфру: фейк-граф (`_FakeGraph`), `InMemorySaver`, `guard=None`, Langfuse off — реальны только ин-процесс коллабораторы (`LangGraphAgentRunner`/`RuntimeSecurityEnforcer`/`StreamEventMapper`). Это sociable-unit, а не integration; по семантике маркеров проекта (быстрый unit-гейт vs полный набор с БД) он должен идти в unit-гейт. → Предлагаемый фикс: сменить маркер на `pytest.mark.unit`. (`test_run_subagent_tool.py` помечен `integration` корректно — там реальный Postgres.)
  - ✅ **Закрыто (test-author, GREEN r1):** маркер сменён на `pytest.mark.unit`; label в § Дизайн автотестов поправлен на sociable-unit. `make test-scope`/`make check` зелёные.

**Чисто:**
- False-green: не найден. Все ассерты содержательны, тестов без проверок нет. Фейки не лгут — сверено с продом: `SelectiveGuard.check(content, checkpoint, **kw)` совпадает с `SecurityGuard.check` (`security/guard.py:76`, позиционные content/checkpoint + kw-only history/canary); `RecordingPromptProvider` наследует `PromptProvider` и повторяет `get_prompt(name, **variables)`/`get_config(name)` (`infra/prompt_provider.py:38,60`); `CapturingModel`/`ScriptedToolModel` duck-типизируют `bind_tools`+`ainvoke`, которые и зовёт граф; `_FakeGraph.astream(_input,_config,*,stream_mode,context)` совпадает с вызовом в `runner.py:159`. Тесты guard/stream используют **реальные** коллабораторы (`RuntimeSecurityEnforcer` c guard=None — no-op на всех чек-пойнтах, `runtime_security.py:84/119/149`; реальный `StreamEventMapper` эмитит `tool_start`/`tool_end`, `stream_events.py:27/37`), а не проверяют собственные моки.
- Тавтология/enshrined-баг: нет. Каскад модели сверяется с реальным `configs/agent.yaml` (`test_runner.py:218`), а не с захардкоженным значением; guard-ветки проверяют реакцию кода на вердикт, не качество (граница unit/eval соблюдена).
- Флак: loop scope согласован (`asyncio_default_fixture_loop_scope="function"`, session-scoped `engine` + function-scoped `outer_conn` — тот же рабочий паттерн, что в image-generation); свежий compile/checkpointer в каждом тесте (`checkpointer=False`); реальной сети/ключа/недетерминированного LLM нет нигде; общего мутабельного состояния между тестами нет.
- Дубли/инфра-по-слою: реальный Postgres только в `test_run_subagent_tool.py` (integration — tool лезет в `ArtifactRepository`, слой оправдан); `SpyRunner`/`SelectiveGuard`/`_SpyCompiled` — на швах, mock-heavy нет; `ProjectFactory`/`bind_session` переиспользованы из `packages/testing`, не продублированы.
- Критпути: guard внутри субагентского цикла закрыт сверх happy — INJECTION по обоим чек-пойнтам (`TOOL_RESULT` redact + продолжение, `TOOL_CALL_ARG` срез tool_calls), CLEAN, SUSPICIOUS (не редактит), `guard=None` fail-open, `recursion_limit`→`GraphRecursionError`; анти-рекурсия (`run_subagent` вне пула), all-or-nothing по чужому/несуществующему/битому UUID.
- Осознанно непокрытое (`persistence: inherit`, композиция пула в lifespan, eval-качество, вложенные Langfuse-span'ы) — согласовано с § Coverage/DoD и § Граница unit/eval; автотест на неиспользуемую ветку был бы false-green.

---

## Покрытие (опционально)

| Критерий приёмки (tasklist § feat-011) | Закрывающие кейсы |
|---|---|
| judge возвращает вердикт; вход только task+артефакты в обёртке id/title; история не утекает | `test_runner` (вход/история), `{T1.1}`/`{T1.2}` (вердикт с evidence на живом LLM) |
| чужой/несуществующий id → ошибка целиком, граф не падает | `test_run_subagent_tool` (всё-или-ничего) |
| реестр в `agent.yaml`; description из реестра; невалидный тип → ошибка со списком | `test_runner` (unknown type), `test_run_subagent_tool` (трансляция), Layer 2 (boot) |
| неизвестное имя tool → ошибка старта | `test_tool_pool_validation` |
| redact `TOOL_RESULT`/`TOOL_CALL_ARG` внутри субагентского цикла (red-team) | `test_graph` 🔴 (обе ветки + fail-open) |
| `recursion_limit` | `test_graph` (GraphRecursionError) |
| user-installed MCP не в пуле | `{T1.5-mcp}` (ручной, glue-композиция) |
| `persistence: none` → checkpointer=False | `test_runner` (spy-compile) |
| токены субагента не в `full_response` (фильтр по тегу) | `test_stream_isolation` |
| анти-рекурсия (`run_subagent` не в toolset субагента) | `test_runner` (пул) |
| модель — дефолт `subagents.llm` + per-spec override | `test_runner` (каскад) |
| промпт через PromptProvider | `test_runner` (маркер + `calls`) |
| вложенные Langfuse-span'ы | `{T1.4-obs}` (ручной, живой трейсинг) |
