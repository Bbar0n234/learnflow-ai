## Code Review Report — режим B (соответствие контракту)

Ревью diff `develop...HEAD` (31 файл) против conventions.md (ядро + agent.md + testing.md),
design-brief, ADR-028 и затронутых доков `doc/tech/`. Детерминированные инварианты
(`make check`, import-linter, arch-checker) взяты из arch-checker-report, не перепроверялись.

### Summary
- blocker: 0 / nit: 3 / pre-existing: 1
- Реализация плотно следует plan/design-brief; обоснованные отклонения (вынос guard-хелперов
  в `tool_guards.py`, двойная сборка guard в `main.py`, `SUBAGENT_RECURSION_LIMIT` константой)
  задокументированы в summary § «Решения и обоснования» и приемлемы по существу.
- Главная находка — незамеченный дрейф в **постоянном** документе ADR-028 (устаревшие имена
  firecrawl-tools), см. отдельную секцию для docs-updater.

### Замечания

| Severity | Намерение | Файл:строка | Норма (ссылка) | Замечание | Предложение |
|---|---|---|---|---|---|
| nit (question) | Ограничить ReAct-цикл субагента | `backend/app/agent/subagents/runner.py:55` | conventions.md § «Что попадает в env» / § «Таймауты и retry» | `SUBAGENT_RECURSION_LIMIT = 10` — код-константа. Ближайший аналог операционного порога agent runtime — `context.max_tokens` — живёт в `configs/agent.yaml` (`ContextConfig`), не как module-константа и не в env. Значение «условно operational» (для реальных web-research-сценариев ручку могут захотеть повернуть); по § env-таблице такое лучше выносить из кода. Не blocker: plan/brief не требовали конфиг-поля, это v1-инвариант, порог наблюдаем (`GraphRecursionError` в tool-error). | Вынести в `subagents.llm`/`ContextConfig` (`configs/agent.yaml`) по образцу `max_tokens`, если архитектор согласен считать его operational knob; иначе оставить константой сознательно. Вопрос к архитектору. |
| nit (question) | Доменный сигнал неизвестного типа | `backend/app/agent/subagents/runner.py:74` | conventions.md § «Модель ошибок: доменные исключения, не транспорт» | `UnknownSubagentTypeError(Exception)` наследует голый `Exception`, не иерархию `AppError`. Ловится локально в tool (`tools/subagents.py:148`), до HTTP-барьера не долетает, `code`/`status` ему не нужны — поэтому по существу приемлемо (agent-internal control-flow, а не сервисное доменное исключение). Фиксирую как question: формально вне `AppError`-иерархии. | Оставить как есть (обоснованно — не транспортное исключение) либо подтвердить у архитектора, что agent-internal исключения, гасимые в tool, вне действия § AppError. |
| nit | Точность постоянного документа | `doc/tech/adr/ADR-028-product-subagents.md:11` | CLAUDE.md § «Документация описывает текущее состояние» / «Исправляй дрейф на месте» | ADR-028 (постоянный doc в `doc/tech/adr/`) в § Контекст ссылается на несуществующие имена `firecrawl_scrape_url`/`firecrawl_extract_data` как на текущий факт («уже работает в проде»). Fixer этой же итерации исправил эти имена в `configs/agent.yaml` на реальные `firecrawl_scrape`/`firecrawl_extract`, но ADR остался с устаревшими — фактическая ошибка в постоянной доке, внесённая итерацией. | Заменить на `firecrawl_scrape`/`firecrawl_extract` в ADR-028:11 (для docs-updater; вынесено также в секцию дрейфа). |

### Blocker без прецедента в conventions
Нет.

### Незамеченный дрейф документации (для docs-updater)

**1. Постоянная дока с устаревшими именами firecrawl-tools (внесено итерацией, НЕ отмечено в summary).**
Fixer поправил `configs/agent.yaml` (`firecrawl_scrape_url`→`firecrawl_scrape`, `firecrawl_extract_data`→`firecrawl_extract`) и в summary упомянул только `plan.md:37` как исторический артефакт. Осталось незамеченным:
- `doc/tech/adr/ADR-028-product-subagents.md:11` — **постоянный** архитектурный документ, старые имена как текущий факт. Требует правки (см. nit выше).
- `doc/tasks/.../feat-011-subagents-v1/design-brief.md:5,132` — итерационный артефакт; исторически допустимо оставить, но при желании согласовать с фактом стоит поправить точечно.

**2. Ожидаемый (acknowledged) дрейф — новые публичные контракты ещё не отражены в `doc/tech/`.**
Проверено: subagent-поверхность **чисто аддитивна** — ни одно утверждение в существующих `agent-runtime.md`/`streaming.md`/`security/architecture.md`/`prompt-management.md` код не делает ложным; доки просто не содержат нового раздела. Решение зафиксировано в ADR-028 + design-brief, распространение — за docs-updater:
- `agent-runtime.md` — паттерн subagent-as-tool: tool `run_subagent`, `SubagentRunner`, реестр `subagents` в `agent.yaml`, общий модуль `tool_guards.py` (guard-хелперы теперь разделяются основным и субагентским графами), toolless/ReAct-формы субагентского графа.
- `streaming.md` — фильтрация токенов субагента по тегу `subagent` в стрим-цикле: `full_response` больше не содержит токены субагента; `tool_start`/`tool_end` для `run_subagent` идут штатно.
- `security/architecture.md` — trust-граница субагента: пул = internal + built-in MCP, **без** user-installed MCP; переиспользование guard'а (`TOOL_RESULT`/`TOOL_CALL_ARG`, fail-safe redact) внутри цикла web-research; toolless-субагенты внутренних проверок не получают.
- `prompt-management.md` — три новых промпта (`subagent-judge`/`subagent-web-research`/`subagent-general-purpose`) в Langfuse-контуре; обёртка `document` в `prompt_fragments.yaml`.

### Pre-existing

| Severity | Файл:строка | Норма | Замечание |
|---|---|---|---|
| pre-existing (low-confidence) | `backend/app/agent/tool_guards.py:106,166` | conventions.md § «Security Event Logging» | Лог-вызовы `"tool_result injection blocked"` / `"tool_call_arg injection blocked"` эмитят `security_event=True` без обязательных по § Security Event Logging полей `event_type` (из vocabulary) и `severity`. Код **перенесён дословно** из `agent/graph.py` (pre-existing, не введён feat-011). Возможно намеренно — канонический SIEM-event может эмитить observer-путь guard'а отдельно, а это операционный лог; поэтому low-confidence. Не относится к scope итерации; сигнал для бэклога/архитектора, не blocker. |

### Что проверено и признано соответствующим (без замечаний)
- **Типизация:** `SubagentSpec`/`SubagentsConfig` — `BaseModel` с явными полями (§ Типизация «YAML-конфиг = BaseModel»); `config: RunnableConfig` — приём стороннего TypedDict, не заведение своего (§ TypedDict); `checkpointer: Any` — консистентно с `graph.py`; `SubagentDocument` — `@dataclass` value-объект по таблице форм.
- **Обработка ошибок:** `_fetch_documents` возвращает error-строку (§ Агентные tools — доменное отсутствие → graceful, tool возвращает строку, агент продолжает); прочие исключения летят в `handle_tool_error` основного `ToolNode` (§ Агентные tools — `handle_tool_errors=<callable>`, thread валиден); анти-рекурсия (`pop run_subagent` из пула) и «всё-или-ничего» fetch — по design-brief.
- **fail-safe guard в субагентском цикле:** та же redact-семантика, что `agent_node` (`security_guard=None` → fail-open, консистентно); наблюдаемость сохранена.
- **Логирование:** keyword-args, уровни по смыслу (INFO для старт/финиш рана субагента как бизнес-события; INFO, не ERROR, для клиентской ошибки fetch — по § Антипаттерны).
- **Слой/ответственность:** новый пакет `subagents/` и `tool_guards.py` — в границах `backend/app/agent/**`; вынос guard-хелперов в отдельный модуль вместо импорта из `graph.py` устраняет реальный circular import (не дублирует паттерн, § agent.md «новая забота → коллаборатор»).
- **Тесты:** раскладка `backend/tests/subagents/` (новый scope-каталог по подсистеме — testing.md § Структура), маркеры `unit`/`integration`, фейки вместо БД/сети (`create_llm_from_config` monkeypatched) — по testing.md § Фейки LLM/guard; корректность самих тестов — режим A.
- **ADR-028** содержит все обязательные разделы (паттерн + обе таблицы отклонённых альтернатив, sync v1/async v2, формат реестра, вход по референсу, persistence, security-политика, extension points).
