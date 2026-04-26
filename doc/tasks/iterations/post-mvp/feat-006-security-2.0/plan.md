# Implementation Plan: feat-006 Security 2.0 — Phases 1–3 (Track A)

## Context

После Security 1.0 (feat-004) Red Team подтвердил две активные проблемы:

- **Class 1 — coverage gaps.** Защищён только USER_INPUT + canary-on-output. Tool arguments, tool results, KS write, MCP metadata, custom instructions write — не проверяются. MCP injection через tool arguments уже утекал системный промпт.
- **Class 2 — weak boundary.** Нет бинарной enforceable границы между «что агент раскрывает» и «что нет». Точные имена internal tools / параметры / схемы утекают через social engineering.

Итерация расширяет существующий `SecurityGuard` extension point на все I/O границы графа + вводит бинарную границу **PROTECTED / DISCLOSABLE** (наш код / всё внешнее), принудительно применяемую output-классификатором и детерминированными детекторами.

План покрывает **Track A, Phases 1–3** из §9.1 design-brief'а (реализация guard-кода, интеграция в runtime, add-time checkpoints). Phase 4 (eval infra, Track B: harvest из Langfuse, HTTP runner, cases.jsonl) — вне scope этого плана (описан в design-brief'е как самостоятельный трек работ, отдельный артефакт).

## Референсы

| Документ | Зачем |
|---|---|
| [doc/workflow.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-006-security-2.0/doc/workflow.md) | Жизненный цикл итерации, структура артефактов, требования к plan.md |
| [doc/tech/conventions.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-006-security-2.0/doc/tech/conventions.md) | Git flow, именование, логирование structlog keyword-args, Prompt Naming `{name}--{label}` |
| [doc/tasks/tasklist-post-mvp.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-006-security-2.0/doc/tasks/tasklist-post-mvp.md) | Scope feat-006: P1 KS Write Guard / LLM Output Classifier, P2 Tool Result Guard / Semantic Similarity + новые (Tool Call Guard, Boundary formalization) |
| [doc/tasks/iterations/post-mvp/feat-006-security-2.0/design-brief.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-006-security-2.0/doc/tasks/iterations/post-mvp/feat-006-security-2.0/design-brief.md) | Threat model, принципы, taxonomy, coverage map, component spec, prompt texts, phasing |
| [doc/tasks/iterations/post-mvp/feat-006-security-2.0/test-cases.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-006-security-2.0/doc/tasks/iterations/post-mvp/feat-006-security-2.0/test-cases.md) | 82 test case, входной чек-лист верификации |
| [doc/security/architecture.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-006-security-2.0/doc/security/architecture.md) | Security 1.0 architecture, extension points, observability |
| [doc/security/threat-model.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-006-security-2.0/doc/security/threat-model.md) | Threat model V1–V3 |
| [doc/research/security/](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-006-security-2.0/doc/research/security) | R1 (mcp-defense), R2 (output-similarity-metric), R3 (confidentiality-boundary) — закрыты |
| [doc/tech/adr/ADR-017-prompt-injection-defense.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-006-security-2.0/doc/tech/adr/ADR-017-prompt-injection-defense.md) | Sec 1.0: sync guard, fail-open, hardening wrapper |
| [doc/tech/prompt-management.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-006-security-2.0/doc/tech/prompt-management.md) | PromptProvider, Langfuse seed/sync, file fallback |
| [feat-004 summary](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-006-security-2.0/doc/tasks/iterations/post-mvp/feat-004-security/summary.md) | Baseline Sec 1.0 |

## Ветка

Согласовано с архитектором — продолжаем на существующей ветке `pmvp/feat-006-security-2.0` (консистентно с feat-002/003/004/005, commits R1/R2/R3/design-brief/test-cases уже здесь).

**Шаг 0 (перед реализацией):**

```bash
git fetch origin
git switch pmvp/feat-006-security-2.0   # если нет локально:
# git checkout -b pmvp/feat-006-security-2.0 origin/develop
```

## Быстро меняющиеся инструменты — verification (inspect/MCP/firecrawl)

Tasklist post-mvp не дублирует таблицу; применяется таблица из [tasklist-agent.md §Быстро меняющиеся инструменты](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-006-security-2.0/doc/tasks/tasklist-agent.md) + специфичные для Sec 2.0 инструменты. Проверено `uv pip list` и `inspect` в этом worktree:

| Инструмент | Версия | Ключевое API (проверено) | Вывод для плана |
|---|---|---|---|
| `langgraph` 1.1.3, `langgraph-prebuilt` 1.0.8 | inspect | `StateGraph`, `MessagesState`, `ToolNode`, `tools_condition` — как в текущем `graph.py`. `CompiledStateGraph.aupdate_state(config, values, as_node=...)` существует, сигнатура совпадает с §6.5 brief'а | Inline-интеграция через `add_messages` reducer (replace-by-id) + `graph.aupdate_state(..., as_node="agent")` для mid-stream/end-of-stream — **работает без изменения топологии графа**. `Command`, `interrupt_before/after` не вводим. |
| `langgraph-checkpoint-postgres` 3.0.4 | inspect | checkpointer уже используется через `AsyncPostgresSaver` (`app/infra/langgraph.py`) | Чтение audit-данных через существующий путь `checkpointer.aget_tuple()`; флаг `security_redacted` живёт в `additional_kwargs` (как `created_at` сегодня). |
| `langchain-core` 1.2.18 | inspect | `BaseMessage.additional_kwargs` — dict[str, Any]; `AIMessage`/`ToolMessage` поддерживают `id` для replace-by-id через reducer | Используется как есть — никаких новых subclass'ов. |
| `langchain-openai` 1.1.11 | inspect | `ChatOpenAI` + custom `ReasoningChatOpenAI` (subclass в `app/infra/llm.py:14–63`) уже вытягивает `reasoning` из `message.additional_kwargs["reasoning"]` для invoke и streaming | Используется для guard + summarizer (§6.11 brief'а). |
| `langchain-mcp-adapters` 0.2.1 | inspect / firecrawl on demand | Обёртка MCP-инструментов уже реализована через `app/infra/mcp.py` + `app/services/mcp_tool_resolver.py` | Источник для `AgentContext.user_installed_tool_names` (§3.9 brief'а). |
| `langfuse` 4.0.1 | inspect (`langfuse.model.TemplateParser.compile_template`) | Поддерживает **только `{{ variable }}` string substitution**; `{% if %}`, `{% for %}` не поддерживаются | Подтверждение §3.7 / §6.14 brief'а: условная логика и циклы — в Python (`prompt_builder.py`), Langfuse получает готовые секции строкой. Jinja system-шаблон удаляется. |
| `langfuse` 4.0.1 — observations | Уже используется: `start_as_current_observation(as_type="guardrail"|"generation"|"span")`, `propagate_attributes`, `create_event`, `score_trace`. `obs.update(usage=...)` — supported | Используется для `GuardObserver` в двух режимах (§6.6) и usage fix (§6.11 / §8.3). |
| `structlog` 25.5.0 | inspect | `Processor = Callable[[logger, method, event_dict], ...]` — стандартный hook-интерфейс; текущая `shared_processors` list в `app/infra/logging.py:35` | Добавление `security_event` processor'а — вставка в начало `shared_processors`. Processor читает `event_dict.get("security_event") is True`, нормализует метаданные, записывает метку. Таблица `security_events` и её питание — feat-005 (§6.13). |
| `sqlalchemy` 2.0.48 + `alembic` 1.18.4 | inspect | Стандартная schema migration | Phase 2 migration для `thread_views.security_blocked BOOLEAN NOT NULL DEFAULT FALSE`. |
| `pydantic` 2.12.5 | inspect | `BaseModel`, enum validation — без специфики | `SecurityConfig`, `GuardResult`, `ClassifierResult`. |
| langgraph-patterns, uv-package-manager скиллы | справочно | — | Используем при реализации для swap патернов и команд. |

Промежуточные similarity-метрики (Levenshtein/embedding/cross-encoder) из §4.2 отчёта R2 — не принимаются (multi-pattern substring + LLM classifier достаточны). Никаких новых ML-зависимостей в pyproject не вводится.

## Архитектурные инварианты (сжато, источник истины — design-brief)

- **Топология графа не меняется.** `START → agent → tools_condition → tools → agent ↺`, встроенный `tools_condition` сохраняется. Security-вызовы inline в `agent_node` + runner, без нод / Command / interrupt_*.
- **Один фасад** `SecurityGuard.check()` — внутренняя структура `{Checkpoint: [DeterministicDetector]}` + один `LLMClassifier` + `GuardObserver`. Отдельные `DetectorPipeline`/`StreamGuardSession` не вводим.
- **Taxonomy:** три ортогональные оси — `Verdict (CLEAN|SUSPICIOUS|INJECTION)`, `Direction (INBOUND|OUTBOUND, производное от Checkpoint)`, `Checkpoint (7 значений)`, плюс `DetectionLayer` и `details: dict`. Source of truth — §6.1.
- **Classifier Isolation (§3.3):** composite `security-classifier` prompt ничего не знает про детерминированные детекторы, про «другие слои» или «fail-open». Trade-off FP/FN формулируется в калибровке, не через апелляцию к слоям.
- **Бинарная граница (§3.2):** PROTECTED (наш internal non-MCP код) vs DISCLOSABLE (MCP built-in/user-installed, user-owned content). Правило «no echo» только для PROTECTED.
- **Fail-open сохраняется** из Sec 1.0: guard LLM exception / invalid response после retries → `graceful_degradation → CLEAN` + WARNING log.
- **Short-circuit + единое действие:** любой детерминированный hit → не вызываем classifier; любой verdict INJECTION → единая механика redaction по checkpoint'у (§5 таблица).
- **Пассивный слой (§3.8) — trust boundary tagging:** оборачиваем USER_DATA / UNTRUSTED активы в XML-теги при composition для LLM. Stored messages в checkpointer — чистые.

## Архитектурные уточнения (pre-Phase 1)

Решения, не покрытые design-brief'ом напрямую и зафиксированные по итогам ревью плана с архитектором. ADR не пишем — при существенных отклонениях по итогам реализации фиксируем в summary.md.

### A1. Thread-level mark_security_blocked — runner owns the side effect

При INJECTION на in-graph checkpoint'ах (`TOOL_RESULT`, `TOOL_CALL_ARG`) `agent_node` **не ходит в БД**. Вместо этого:

- Нода возвращает message с `additional_kwargs["security_redacted"]=True` и `additional_kwargs["original_detection_layer"]=<layer>` (replace-by-id через `add_messages` reducer).
- После `graph.astream` runner делает `graph.aget_state(config)` и инспектирует state. Если среди сообщений последнего turn'а есть AIMessage / ToolMessage с `security_redacted=True` и `original_detection_layer in {tool_call_arg, tool_result}` — runner вызывает `thread_view_repo.mark_security_blocked(thread_id)` и эмитит `security_block` SSE event.
- Тот же runner уже владеет `FINAL_OUTPUT` mid/end-of-stream INJECTION (прямой вызов `aupdate_state` + `mark_security_blocked`) — единый owner всех thread-level side effects.

Обоснование: (i) graph-ноды остаются чистыми функциями без session-dependency; (ii) `GraphFactory.build` не раздувается `session_maker`; (iii) один owner — проще тестировать и прослеживать. Альтернатива с инжекцией `session_maker` через `AgentContext`/`GraphFactory` смазывает разделение concerns.

### A2. MCP_METADATA — минимальный McpServerService

CRUD MCP-серверов сейчас **полностью в роутере** `app/api/routes/mcp_servers.py` через `MCPServerRepository` напрямую (`create_user_server:177`, `create_project_server:284`, `create_thread_server:422`), service layer для MCP отсутствует.

- Поднимаем **минимальный** `app/services/mcp_server.py:McpServerService` с одним публичным методом `async def guard_and_persist(self, scope: Literal["user","project","thread"], owner_id: uuid.UUID, payload: McpServerCreateIn) -> MCPServer` — инкапсулирует `SecurityGuard.check(Checkpoint.MCP_METADATA)` + SSRF-валидацию + encryption + persist.
- Остальная логика роутера (маппинг payload'а, response-схема) остаётся на месте. Все три endpoint'а вызывают этот единственный метод сервиса.
- Полного рефакторинга MCP CRUD в service layer не делаем — отдельная активность за рамками security-итерации.

### A3. Frontend scope в этой итерации — минимальная redaction UI

Без frontend-части защита результата неполная (mid-stream утечка видна в UI до рефетча истории; brief §5 явно специфицирует замену). Минимум в scope:

- **Phase 1 (FINAL_OUTPUT):** SSE event `security_block` пришедший **после** начала `text_chunk`'ов — заменяет накопленный контент ассистентского сообщения на заглушку `"[Сообщение скрыто в целях безопасности]"`. Отличается от текущего error-flow (`doc/tech/frontend.md:232`), требует правки SSE-reducer'а и сообщения в chat store'е.
- **Phase 2 (history):** при GET истории `Message.redacted === true` → рендерить ту же заглушку вместо `content`.

Визуальный дизайн (цвет, иконка, tooltip, анимация) не прорабатывается — текстовая заглушка достаточна для закрытия функционального требования.

## Phase 1 — Foundation (Track A)

**Цель:** новая taxonomy + фасад + composite classifier + FINAL_OUTPUT + USER_INPUT fragment backport + ReasoningChatOpenAI повсеместно + `security.yaml` вынос + system prompt со структурой `<tools>` + trust-обёртки.

### 1.1 Taxonomy и типы (§6.1)

- Расширить `app/agent/security/types.py`:
  - `class Checkpoint(str, Enum)` — 7 значений: `USER_INPUT`, `TOOL_RESULT`, `TOOL_CALL_ARG`, `FINAL_OUTPUT`, `MCP_METADATA`, `CUSTOM_INSTRUCTIONS_WRITE`, `KS_WRITE_REST`.
  - `class Direction(str, Enum)` — `INBOUND`, `OUTBOUND`. Helper `direction_of(checkpoint) -> Direction` (compile-time таблица).
  - `class DetectionLayer(str, Enum)` — `canary`, `unicode`, `fragment`, `paired`, `llm_classifier`, `graceful_degradation`.
  - Переименовать `SecurityVerdict` → `Verdict` (совместимость через алиас на Phase 1, убираем после Phase 2 когда все call-sites переехали).
  - `class GuardResult(BaseModel)` — добавить `checkpoint: Checkpoint`, `direction: Direction`, `detection_layer: DetectionLayer | None`, `details: dict[str, Any] | None`. `reason` убираем — replaces by `detection_layer` + `details`.
  - `class ClassifierResult(BaseModel)` — `verdict: Verdict`, `reasoning: str | None`, `retries: int`.

### 1.2 Детекторы (§6.3)

- Новый модуль `app/agent/security/detectors/` (package; текущий `detectors.py` раскладываем):
  - `base.py` — `class DeterministicDetector(Protocol)`: `name: str`, `applies_to: set[Checkpoint]`, `def inspect(buffer: str, ctx: dict) -> Hit | None`.
  - `canary.py` — `CanaryDetector` (перенос `check_canary_in_text` под интерфейс; порог 1 hit; `applies_to =` все 7).
  - `unicode.py` — `UnicodeDetector` (перенос `detect_invisible_chars`; `applies_to = {USER_INPUT, TOOL_RESULT, MCP_METADATA, CUSTOM_INSTRUCTIONS_WRITE, KS_WRITE_REST}`).
  - `fragment.py` — `FragmentDetector` (sliding windows 60 chars, stride 30, threshold `|unique| ≥ 2`). Corpus: hardening preamble + security instructions + base system prompt prose + skills content + descriptions internal non-MCP tools. **Исключены:** MCP descriptions, user-owned content. `applies_to = {USER_INPUT, TOOL_RESULT, FINAL_OUTPUT, TOOL_CALL_ARG}`. Corpus собирается при старте и кэшируется на инстансе детектора.
  - `paired.py` — `PairedToolIdentifierDetector` (registry `{tool: [params]}`, tool compromised при совпадении имени И ≥1 параметра; threshold `|compromised tools| ≥ 3`). Registry читает только internal non-MCP (из `app/agent/tools/`), MCP-имена не добавляем (§3.2). `applies_to = {FINAL_OUTPUT, TOOL_CALL_ARG}`.
  - `normalize.py` — единый helper `normalize(text) -> str` (lowercase + `_-` → `_` + whitespace collapse). Применяется в `fragment` и `paired`.

### 1.3 SecurityGuard facade (§6.2, §6.4)

- Переписать `app/agent/security/guard.py`:
  - В конструктор: `detectors_by_checkpoint: dict[Checkpoint, list[DeterministicDetector]]`, `classifier: LLMClassifier`, `observer: GuardObserver`, `config: SecurityConfig`.
  - При инициализации собрать `detectors_by_checkpoint` из списка инстансов детекторов по их `applies_to` (compile-time инвариант, без конфигурации). Порядок внутри checkpoint'а: `canary → unicode → paired → fragment` (короткая проверка сначала).
  - Новая сигнатура: `async def check(self, content: str, checkpoint: Checkpoint, *, history: list[BaseMessage] | None = None, canary_token: str | None = None, skip_classifier: bool = False, trace_ctx: dict | None = None) -> GuardResult`.
  - Семантика (§6.2 `check()`):
    1. Прогнать детерминированные детекторы из `detectors_by_checkpoint[checkpoint]`, short-circuit на первом hit → `GuardResult(INJECTION, checkpoint, direction, detection_layer=<hit>, details=<layer-specific>)`.
    2. `skip_classifier=True` и детерминированный слой чист → `GuardResult(CLEAN, checkpoint, direction, detection_layer=None)` (mid-stream FINAL_OUTPUT).
    3. Иначе — `await classifier.classify(content, checkpoint, history)` → `GuardResult(verdict, checkpoint, direction, detection_layer=llm_classifier, details={reasoning, raw_response, retries})`.
    4. Exception от guard LLM → `graceful_degradation → CLEAN + WARNING log` (`exc_info=True`).
  - Все вызовы оборачиваются в `async with self._observer.observe(checkpoint, content, trace_ctx=trace_ctx) as obs:` — GuardObserver пишет guardrail observation, classifier generation, cost tracking (`obs.update_usage(...)` после classifier'а).
- `LLMClassifier` (`app/agent/security/classifier.py` — новый модуль):
  - Поля: `prompt_provider`, `llm: BaseChatModel`, `security_config`, `checkpoint_configs: dict[Checkpoint, CheckpointConfig]` (из `security.yaml`).
  - Метод `classify(content, checkpoint, history)`: компилирует composite Langfuse-prompt `security-classifier` (один промпт, label `--{env_label}`) со слотами `{{ checkpoint_description }}`, `{{ checkpoint_specifics_section }}`, `{{ history_section }}`, `{{ content }}` (§6.14.4). `specifics` и `history` пустая строка → секция не рендерится (logic в Python, промпт только подставляет строку).
  - Retry цикл: `for attempt in range(max_retries)`: `ainvoke` → parse один из `CLEAN|SUSPICIOUS|INJECTION`, иначе retry; исчерпан → `graceful_degradation → CLEAN`. Reasoning извлекается из `response.additional_kwargs["reasoning"]`, кладётся в `ClassifierResult.reasoning`.

### 1.4 GuardObserver (§6.6)

- `app/agent/security/observer.py` (новый модуль) — один класс `GuardObserver`. **Форма API: async context manager**, не method-wrapper.
  - `@asynccontextmanager async def observe(self, checkpoint: Checkpoint, content: str, *, trace_ctx: dict | None = None) -> AsyncIterator[ObservationHandle]` — yield'ит handle с методами `record_classifier_generation(input, model, params, ...)`, `finalize(result: GuardResult)`, `update_usage(token_usage)`.
  - Эта форма согласована с архитектором (brief §6.2 class-diagram `observe(guard_call, ctx)` зафиксирована как формальная запись той же семантики; Pythonic with-block — удобнее и уже используется в Sec 1.0, см. `_run_guard_with_observability` `runner.py:340`).
  - **Два режима работы** — выбираются по `trace_ctx`:
    - **Agent runtime (вложенный):** parent span'ом выступает уже открытый `agent-run`. Метод открывает `start_as_current_observation(as_type="guardrail", name=f"guard-{checkpoint}")`.
    - **REST add-time (top-level):** `trace_ctx` содержит `{"top_level": True, "user_id": ..., "scope": ...}` → создаётся top-level trace `security.<checkpoint>` через `get_client().start_as_current_observation(as_type="span")` + `propagate_attributes(user_id=..., trace_name=f"security.{checkpoint}")`.
  - Classifier generation внутри: `start_as_current_observation(as_type="generation", name="llm-classifier", model=..., input=classifier_input, model_parameters=...)`, после ответа `obs.update(output=raw, usage=response.response_metadata["token_usage"])`. Закрытие §8.3 cost gap.
  - Fail-safe: все Langfuse-вызовы в `contextlib.suppress(Exception)`; degradation → WARNING log с `exc_info=True`.
- Переиспользуем pattern из `app/agent/runner.py:340-397` (`_run_guard_with_observability`) — извлекаем и обобщаем в `GuardObserver`, существующий метод в runner'е удаляем.

### 1.5 ReasoningChatOpenAI + usage fix + security.yaml (§6.11, §6.12, §8.3)

- **`configs/security.yaml`** — новый файл (коммитится в репо; значения — безопасные defaults, секреты остаются в `.env`), Pydantic `SecurityConfig` (расширяем из `app/agent/security/types.py`):
  ```yaml
  guard_model: <model_id>             # перенести из agent.yaml
  guard_extra_body:
    include_reasoning: true            # новое default в Sec 2.0
  max_retries: 3
  temperature: 0.0
  guard_model_pricing:
    input_token: ...
    output_token: ...
    output_reasoning: ...
  detectors:
    paired:
      min_compromised_tools: 3
      min_params_per_tool: 1
    fragment:
      window_size: 60
      stride: 30
      min_unique_matches: 2
  checkpoints:
    user_input:
      description: "..."
      classifier_enabled: true
    # ... 6 остальных; final_output + mcp_metadata имеют specifics
  ```
  - Двухуровневый merge `detectors.*` → `checkpoints.<name>.detectors.*` (override). Applicability matrix остаётся compile-time инвариантом в коде (через `applies_to` у Detector'ов), не меняется конфигом.
  - Загрузчик `app/agent/security/config.py` (новый): `load_security_config(path) -> SecurityConfig`. DI через FastAPI `Depends` (новая фабрика в `app/api/deps.py`). Секция `security:` из `agent.yaml` удаляется (вместе с Pydantic-моделью внутри `app/agent/config.py`).
- **`create_guard_llm` (`app/infra/llm.py:124`) — мигрируем на ReasoningChatOpenAI:**
  - По аналогии с `create_llm` (строки 66–79): `use_reasoning = extra_body.get("include_reasoning", False)`; при true используем `ReasoningChatOpenAI`.
  - Default в Sec 2.0 — `include_reasoning: true` (значение в `security.yaml`).
- **`create_summarization_llm` + `create_summarization_llm_from_prompt_config`** — тот же паттерн: условно `ReasoningChatOpenAI` по `extra_body.include_reasoning` (сейчас extra_body не прокидывается — добавить в `SummarizationConfig` и в Langfuse prompt config). Backlog P2 «Reasoning ChatOpenAI everywhere» — закрывается в этой итерации (подтверждено архитектором).
- **Usage tracking в Langfuse:** `obs.update(usage=response.response_metadata["token_usage"])` после каждого guard LLM call (ликвидирует gap §8.3 — costs = 0). Pricing для guard модели в `security.yaml → guard_model_pricing`.
- **Convention в `doc/tech/conventions.md`** — новая секция «Reasoning LLMs»: когда применяется `ReasoningChatOpenAI`, как конфигурируется через `extra_body.include_reasoning`, где видно в Langfuse (`additional_kwargs.reasoning`).

### 1.6 structlog security_event processor (§6.13)

- `app/infra/logging.py` — добавить в `shared_processors` (перед `JSONRenderer`) новый processor `_security_event_processor`:
  - `def _security_event_processor(logger, method_name, event_dict) -> event_dict`: если `event_dict.get("security_event") is True` — нормализовать, дополнить ключами `severity` (из уровня лога), `security_event_type`, сохранить как есть (запись в обычный JSON log). Подготовка под feat-005 SIEM Core, где этот processor начнёт писать в `security_events` таблицу.
- Существующие WARNING/ERROR log-вызовы в SecurityGuard / LLMClassifier / GuardObserver дополняются `security_event=True, checkpoint=..., verdict=..., identifiers={...}, metadata={...}`.

### 1.7 FINAL_OUTPUT в runner (§5, §6.5 — mid/end-of-stream)

- `app/agent/runner.py` — правки `LangGraphAgentRunner.stream`:
  - **Mid-stream (per-chunk):** вместо существующего canary-check на строках 270–289 (переинтегрируется), каждый чанк обновляет `full_response` буфер, после чего:
    ```
    mid_result = await guard.check(full_response, Checkpoint.FINAL_OUTPUT, canary_token=canary_token, skip_classifier=True)
    ```
    INJECTION → выход из chunk-loop; `await graph.aupdate_state(config, {"messages": [AIMessage(id=current_id, content=full_response, additional_kwargs={"security_redacted": True, ...})]}, as_node="agent")` (replace-by-id через `add_messages` reducer); `await thread_view_repo.mark_security_blocked(thread_id)` (метод появляется в Phase 2 миграции; в Phase 1 FINAL_OUTPUT INJECTION пока работает без thread-level блокировки — отмечено TODO, закрывается с Phase 2); yield `StreamEvent(type="security_block", data={"reason": mid_result.detection_layer.value})`.
    CLEAN → yield `text_chunk` как сейчас.
  - **Tail-only scan оптимизация:** детерминированные детекторы в mid-stream сканируют не весь `full_response`, а хвост `full_response[-(overlap + chunk_len):]`, где `overlap = max(canary_token_length, fragment.window_size, len(longest_tool_name_or_param))`. Ранее совпавшие windows уже дали бы hit на предыдущем чанке (short-circuit). Это снимает O(N²) риск на длинных ответах (brief §8.1 декларирует <1 ms per chunk — выдерживается только при tail scan). Fallback на полный буфер — если в ходе верификации обнаружится cross-chunk match, теряемый хвостом (маловероятно, но зафиксировать метрику latency в test-cases и ревью).
  - **End-of-stream (classifier):** после успешного завершения astream:
    ```
    final_result = await guard.check(full_response, Checkpoint.FINAL_OUTPUT, canary_token=canary_token)   # skip_classifier=False
    ```
    INJECTION → `graph.aupdate_state(..., additional_kwargs={"security_redacted": True}, as_node="agent")` (перезаписывает финализированный AIMessage), `thread_view_repo.mark_security_blocked(thread_id)` (с Phase 2), yield `security_block`.
    Между концом astream и ответом classifier'а (1–3 с) — frontend пока держит последний chunk; flag об ожидании не вводим (UX trade-off §5 — видимая задержка, не буферизация).
  - Canary-check оставляем как один из детекторов CanaryDetector в `FINAL_OUTPUT` pipeline (через `SecurityGuard.check`), отдельный код в runner'е удаляется. `_record_canary_leak` логика уезжает в `GuardObserver.observe` + `security_event` лог.
- `AgentContext` (`app/agent/graph.py:33`) — без изменений в Phase 1 (расширение в Phase 2 для `user_installed_tool_names`).

### 1.8 USER_INPUT — fragment backport

- Уже в Phase 1 `SecurityGuard.check(content, Checkpoint.USER_INPUT, history=..., canary_token=...)` автоматически подхватит `FragmentDetector` через `applies_to`. Runner (`_run_guard_with_observability`) передаёт `Checkpoint.USER_INPUT` вместо строки `"user_input"`; остальная обработка INJECTION остаётся как сейчас (pre-graph reject + SSE security_block).

### 1.9 Composite classifier в Langfuse (§6.14.4)

- Обновить `configs/prompts/guard-classifier.txt` — переписать под composite-prompt (шаблон §6.14.4 brief'а):
  - Слоты `{{ checkpoint_description }}`, `{{ checkpoint_specifics_section }}`, `{{ history_section }}`, `{{ content }}`.
  - Удалить упоминания «additional defense layers» (Sec 1.0 текст).
  - Семь `description` + `final_output` / `mcp_metadata` `specifics` — заливаются в `security.yaml` (§6.14.5, §6.14.6).
- Startup seed (`app/main.py` через существующий механизм feat-003): prompt `security-classifier` засидить из файла с label `production`. Имя по convention `security-classifier--{label}` (Prompt Naming, conventions.md).

### 1.10 System prompt — трёхсекционная структура + trust-обёртки (§3.7, §3.8, §6.7, §6.14)

- **Удалить `SYSTEM_MESSAGE_TEMPLATE` (Jinja) в `app/agent/prompt_builder.py`.** Langfuse поддерживает только string substitution (подтверждено inspect'ом `TemplateParser`). Условная логика — в Python.
- Новые section-renderers в `app/agent/prompt_builder.py` (плоские функции, каждая возвращает готовую строку секции или `""`):
  - `render_canary_section(token)` — `"\nInternal verification token: {token}"` или `""`.
  - `render_custom_instructions_section(content)` — обёртка `<custom_instructions>...</custom_instructions>` + маркер «cannot override system»; `""` при пустом.
  - `render_user_memory_section(index)` — `<user_memory>...</user_memory>`; `""` при пустом index.
  - `render_knowledge_sphere_section(index)` — `<knowledge_sphere>...</knowledge_sphere>` (всегда, даже при пустом — KS архитектурная сущность, §6.14.2).
  - `render_skills_section(index)` — `<available_skills>...</available_skills>`; `""` при пустом.
  - `render_user_installed_mcp_section(tools)` — `<user_installed_mcp_tools>` + преамбула «external services the user connected...» + для каждого: `<untrusted_tool_description>{description}</untrusted_tool_description>`; `""` при пустом списке.
- Новая функция `build_system_message(...)` — просто передаёт отрендеренные строки в `prompt_provider.get_prompt("system", canary_section=..., custom_instructions_section=..., ...)`. Langfuse-промпт получает готовые строки-слоты.
- **Полный текст system-промпта (§6.14.1)** — засиживаем в Langfuse `system--{label}` (уже существующий пайплайн через PromptProvider). В `configs/prompts/system.txt` — обновить до нового текста (fallback). Ключевые изменения vs Sec 1.0:
  - `<confidentiality>` (запретительный блок из Iteration 1) удалён.
  - Новая `<tools>` секция с трёхсекционной структурой `<internal_tools>` (PROTECTED) / `<builtin_mcp_tools>` (DISCLOSABLE, TRUSTED) / `<user_installed_mcp_tools>` (DISCLOSABLE, UNTRUSTED — обёртка `<untrusted_tool_description>`).
  - `<interaction>` впитывает «sources» пункт.
  - `<error_handling>` и `<boundaries>` свёрнуты.
  - `<system_instructions>` содержит capability-vs-implementation принцип + confidentiality preamble.
- **Message-composition helpers (§6.14.3):** `wrap_user_message(text)` и `wrap_tool_output(text)` — plain string helpers в `prompt_builder.py`. Применяются **только на LLM composition** (перед отправкой `ainvoke`), не при сохранении в checkpointer. Stored messages остаются чистыми — DTO-mapper, UI и audit не нужно правку unwrap.
- **Централизованный helper `compose_for_llm(messages: list[BaseMessage]) -> list[BaseMessage]`** в `prompt_builder.py` — **единственная** точка обёртывания. Гарантирует immutability исходных messages:
  ```python
  def compose_for_llm(messages):
      result = []
      for m in messages:
          if isinstance(m, HumanMessage):
              result.append(HumanMessage(content=wrap_user_message(m.content), id=m.id, additional_kwargs=m.additional_kwargs))
          elif isinstance(m, ToolMessage):
              result.append(ToolMessage(content=wrap_tool_output(m.content), id=m.id, tool_call_id=m.tool_call_id, name=m.name, additional_kwargs=m.additional_kwargs))
          else:  # AIMessage, SystemMessage — не оборачиваем (§3.8 brief)
              result.append(m)
      return result
  ```
  - Возвращает новый list с **новыми instances** для оборачиваемых типов. Исходный list + элементы не мутируются. `id` сохраняется — чтобы `add_messages` reducer не дублировал.
  - Интеграция в `agent_node` (`app/agent/graph.py:151`): после `trim_messages(...)` → `llm_messages = compose_for_llm(trimmed)` → `bound_model.ainvoke([system, *llm_messages])`. `messages`/`trimmed` в state — чистые, checkpointer получает необ wrapped.
- **Unit-test требуется (в этой итерации, несмотря на MVP-политику отсутствия тестов для нового кода):** `tests/unit/agent/test_compose_for_llm.py` — проверяет (i) `result[i] is not messages[i]` для HumanMessage/ToolMessage; (ii) `messages[i].content == original_raw_content` после compose (immutability); (iii) wrap идемпотентен — `compose(compose(m))` не даёт двойной обёртки (защита от случайного второго прогона). Это единственное место, где скрытая мутация ломает `stored messages чистые`-инвариант — стоит explicit unit-test.

### 1.11 Error message normalization (§6.10)

- Новый helper `normalize_error_message(exc: Exception) -> str` в `app/agent/runner.py` (или отдельный `app/agent/error_mapper.py`, если получается длинный mapping). Маппит класс исключения в user-safe формулировку без технических деталей (paths, tool names, stack traces).
- В `except Exception as e:` блоке (`runner.py:300-307`) вместо `str(e)` — `normalize_error_message(e)`.
- Не guard-компонент, но закрывает SSE `error` канал, минующий classifier.

### 1.11bis Frontend — FINAL_OUTPUT redaction (§A3 Phase 1)

- `frontend/src/features/chat/` (точная локация SSE-reducer'а — при реализации): `security_block` SSE event, пришедший **после** первого `text_chunk`, заменяет накопленный `content` ассистентского сообщения на `"[Сообщение скрыто в целях безопасности]"`. Сейчас (`doc/tech/frontend.md:232`) `security_block` обрабатывается как generic error — нужна явная ветка «если уже есть text_chunk'и → заменяем content, не открываем error-модалку».
- `redacted: boolean` поле добавляется в chat-store при этом event'е (same-session), чтобы UI не перерисовывал старый текст при последующих обновлениях.
- Визуальный дизайн (иконка, цвет) — не прорабатывается, plain-text заглушка.

### 1.12 Phase 1 verification gate

- `make check` + `make check-fe` (последний затрагивается — правка SSE-reducer'а).
- `make test` — существующие тесты не падают. Новый unit-тест `test_compose_for_llm.py` (§1.10) проходит.
- **Backend стартует на чистом checkout:** `configs/security.yaml` в репо, `configs/agent.yaml` без `security:`, Langfuse пустой — file fallback `configs/prompts/{system,guard-classifier}.txt` работает, seed создаёт `system--production` и `security-classifier--production`.
- Ручная проверка: Langfuse trace содержит `guardrail` observation с `usage` + `reasoning` в generation; system prompt рендерится с новыми секциями; canary в final_output блокирует (переинтегрированный детектор); frontend заменяет текст на заглушку.
- Test cases (partial): TC-0.1, TC-0.2, TC-0.4, блок «1. Foundation» из test-cases.md (TC-1.1.* taxonomy, TC-1.2.* detectors, TC-1.3.* classifier, TC-1.4.* FINAL_OUTPUT, TC-1.5.* USER_INPUT fragment, TC-1.6.* system prompt).

## Phase 2 — In-graph inline (Track A)

**Цель:** `TOOL_CALL_ARG` + `TOOL_RESULT` inline в `agent_node` + thread-level блокировка + message-level redaction в DTO-mapper + MCP trust разделение.

### 2.1 Migration — thread_views.security_blocked (§6.8)

- Alembic migration `<next_rev>_add_security_blocked_to_thread_views.py`:
  - `op.add_column("thread_views", sa.Column("security_blocked", sa.Boolean(), nullable=False, server_default=sa.false()))`.
  - Downgrade: `op.drop_column(...)`.
- `app/models/thread_view.py:ThreadView` — новое поле `security_blocked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))`.
- `app/repositories/thread_view.py` (уже существует, расширить) — метод `async def mark_security_blocked(self, thread_id: uuid.UUID) -> None:` (atomic UPDATE). Read-метод `async def is_security_blocked(self, thread_id) -> bool`.

### 2.2 FastAPI Depends — require_unblocked_thread (§6.8)

- `app/api/deps.py` (существует) — новая зависимость `async def require_unblocked_thread(thread_id: uuid.UUID, repo: ThreadViewRepository = Depends(...)) -> None`: один SELECT; `security_blocked=True` → `raise HTTPException(403, detail="Thread blocked by security policy")`.
- Применяется к `POST /api/chats/{thread_id}/messages` (`app/api/routes/messages.py`) — добавить в `Depends` chain.
- GET истории (`GET /api/chats/{thread_id}/messages`, `GET /api/chats/{thread_id}`) **без** этой зависимости — пользователь видит свои сообщения + заглушку вместо утекшего ответа.

### 2.3 Message-level redaction в API DTO-mapper (§6.9)

- `app/agent/runner.py:get_history` и `app/api/schemas/messages.py` (или где формируются DTO из `BaseMessage`):
  - Если `m.additional_kwargs.get("security_redacted") is True` → content заменяется на `"[Сообщение скрыто в целях безопасности]"` (или подобное), DTO получает поле `redacted: bool = True`.
  - Оригинальный content в checkpointer **сохраняется** (audit-источник), НЕ мутируется.
- `Message` pydantic-модель (`app/services/agent_runner.py`) — добавить поле `redacted: bool = False`.
- **Frontend (§A3 Phase 2) — в scope итерации:** `frontend/src/features/chat/` (модель сообщения + рендеринг в списке истории) — если `message.redacted === true` → отрисовать `"[Сообщение скрыто в целях безопасности]"` вместо `message.content`. Единая строка-константа с Phase 1 (§1.11bis) заглушкой. Плашка/иконка не прорабатывается.

### 2.4 TOOL_RESULT inline в agent_node (§6.5)

- `app/agent/graph.py:agent_node` — добавить блок ДО compaction + system-build:
  ```
  # 0. Pre-guard: TOOL_RESULT (ToolMessages с прошлой итерации)
  recent_tool_messages = [m for m in messages[-K:] if isinstance(m, ToolMessage) and not m.additional_kwargs.get("security_redacted")]
  for tm in recent_tool_messages:
      result = await security_guard.check(
          tm.content,
          Checkpoint.TOOL_RESULT,
          history=messages[:-1],
          canary_token=runtime.context.canary_token,  # §A1 / brief §6.3 — canary applies_to TOOL_RESULT
      )
      if result.verdict == Verdict.INJECTION:
          # replace-by-id: заменяем на заглушку с флагом (см. §2.5 — runner подхватит флаг)
          stub = ToolMessage(id=tm.id, tool_call_id=tm.tool_call_id, name=tm.name,
                             content="[Tool result blocked by security policy]",
                             additional_kwargs={"security_redacted": True, "original_detection_layer": result.detection_layer.value})
          result_prefix.append(stub)
          # Никаких DB-вызовов из ноды — §A1: runner владеет mark_security_blocked
  ```
  Где `K` — диапазон «непроверенных ToolMessage'ей» с прошлой итерации. На практике: все ToolMessage'и **после последнего AIMessage без tool_calls** (то есть, всё что пришло в ответ на предыдущий tool_calls). Это текущий batch; более ранние уже были проверены на прошлой итерации.
- **Open question из brief §11:** форма return'а при INJECTION. **Базовый вариант плана:** заглушка → LLM получает её → генерирует нейтральный ответ. Если на практике UX плохой — ранний return с фиксированным AIMessage; переключение без рефакторинга (§11 brief).

### 2.5 SecurityGuard в agent_node + runner owns mark_security_blocked (§A1)

- `build_graph` (`app/agent/graph.py:136`) принимает `security_guard: SecurityGuard | None` (optional для backward-compat на Phase 1, обязателен после Phase 2).
- `GraphFactory.build(...)` (`app/agent/graph_factory.py`) — пробрасывает security_guard из конструктора.
- `agent_node` closure захватывает `security_guard` из `build_graph` scope. **DB-зависимостей в ноде нет** — `session_maker` / `thread_view_repository_factory` через `AgentContext` / `build_graph` **не инжектируется** (§A1).
- **Runner post-stream inspection (§A1):** после завершения `graph.astream`:
  ```python
  state = await self._graph_factory._checkpointer.aget_tuple(config)  # уже используется в get_history
  if state is not None:
      messages_final = state.checkpoint.get("channel_values", {}).get("messages", [])
      # инспектируем turn, завершившийся в этом stream'е — обычно хвост списка
      for m in reversed(messages_final):
          if isinstance(m, (AIMessage, ToolMessage)) and m.additional_kwargs.get("security_redacted"):
              layer = m.additional_kwargs.get("original_detection_layer")
              if layer in {"tool_call_arg", "tool_result", "canary", "unicode", "paired", "fragment", "llm_classifier"}:
                  await thread_view_repo.mark_security_blocked(thread_id)
                  yield StreamEvent(type="security_block", data={"reason": layer})
              break  # только последний INJECTION; раньше уже были обработаны
  ```
  Runner получает `ThreadViewRepository` через существующую DI-цепочку (session резолвится в роутере и пробрасывается в `runner.stream(..., session=...)` — уже есть, см. `runner.py:139`).
- Тот же путь работает для `FINAL_OUTPUT` mid/end-of-stream — runner уже вызывает `mark_security_blocked` напрямую в `_handle_final_output_injection` (§1.7). Единая точка side-effect.

### 2.6 TOOL_CALL_ARG inline в agent_node (§6.5)

- После `bound_model.ainvoke(...)` (строка 221):
  ```
  if response.tool_calls:
      # Сериализовать аргументы в строку: JSON dump всех tool_calls args
      args_payload = json.dumps([tc["args"] for tc in response.tool_calls], ensure_ascii=False)
      result = await security_guard.check(
          args_payload,
          Checkpoint.TOOL_CALL_ARG,
          history=messages,
          canary_token=runtime.context.canary_token,  # §A1 / brief §6.3 — canary applies_to TOOL_CALL_ARG
      )
      if result.verdict == Verdict.INJECTION:
          redacted = AIMessage(id=response.id, content=response.content, tool_calls=[],
                               additional_kwargs={**response.additional_kwargs, "security_redacted": True, "original_detection_layer": result.detection_layer.value})
          # Никаких DB-вызовов из ноды (§A1) — runner post-stream подхватит флаг
          return {"messages": [*result_prefix, redacted]}
          # add_messages reducer: replace-by-id; tools_condition видит tool_calls=[] → END
  ```

### 2.7 MCP trust разделение (§3.9, §6.7)

- `app/agent/graph.py:AgentContext` — добавить поле `user_installed_tool_names: frozenset[str] = frozenset()`.
- `app/agent/runner.py:stream` — перед вызовом `graph.astream` собирать имена user-installed tools из `extra_tools` (возвращаемых `self._tool_resolver.resolve(...)`) и передавать во `AgentContext(user_installed_tool_names=...)`. Global built-in tools из `agent.yaml` (Firecrawl, Tavily) — не добавляем в этот set (они TRUSTED).
- `agent_node` читает `runtime.context.user_installed_tool_names` — пробрасывает в `render_user_installed_mcp_section(...)` из Phase 1.10 (вместо пустого списка по умолчанию).
- `bind_tools` (`app/agent/graph.py:144`) — без изменений; LangChain сам отдельно отдаёт описания через tool calling API.

### 2.8 Phase 2 verification gate

- `make check` + `make test`.
- Ручная: TOOL_CALL_ARG injection (tool arg с системным промптом) → `security_block` SSE + `thread_views.security_blocked=true` + последующий POST отклоняется 403.
- TOOL_RESULT injection через имитированный MCP scrape → тот же эффект на следующей итерации.
- Langfuse trace: два guardrail observation'а (TOOL_RESULT, TOOL_CALL_ARG).
- Test cases: блок «2. In-graph inline» из test-cases.md.

## Phase 3 — Add-time checkpoints (Track A)

**Цель:** guard.check в service-слое REST-эндпоинтов, top-level Langfuse trace через GuardObserver.

### 3.1 MCP_METADATA — минимальный McpServerService (§A2, §5, §6.6)

**Текущее состояние:** CRUD MCP-серверов в `app/api/routes/mcp_servers.py` напрямую через `MCPServerRepository` (endpoints `create_user_server:177`, `create_project_server:284`, `create_thread_server:422`), service layer для MCP отсутствует.

**Реализация:**

- Новый модуль `app/services/mcp_server.py:McpServerService` — **минимальный фасад, инкапсулирующий security-инварианты** (не полный CRUD-рефакторинг):
  ```python
  class McpServerService:
      def __init__(self, repo: MCPServerRepository, guard: SecurityGuard, url_validator: UrlValidator, encryption: EncryptionService) -> None: ...

      async def guard_and_persist(
          self, *, scope: Literal["user","project","thread"],
          owner_id: uuid.UUID, payload: McpServerCreateIn,
      ) -> MCPServer:
          # 1. Сериализовать metadata payload в строку для guard
          meta_blob = f"{payload.name}\n{payload.description or ''}\n{json.dumps(payload.allowed_tools or [])}"
          # 2. guard.check — первым (§11 open question: default guard → SSRF)
          result = await self._guard.check(
              meta_blob, Checkpoint.MCP_METADATA,
              trace_ctx={"top_level": True, "user_id": str(owner_id), "scope": f"mcp.{scope}"},
          )
          if result.verdict == Verdict.INJECTION:
              logger.warning("mcp metadata injection blocked", security_event=True,
                             checkpoint="mcp_metadata", verdict="INJECTION",
                             identifiers={"user_id": str(owner_id), "scope": scope},
                             metadata={"detection_layer": result.detection_layer.value})
              raise HTTPException(422, detail={"error": "security_policy_violation", "reason": result.detection_layer.value})
          # 3. SSRF + encryption + persist (логика перенесена из роутера)
          ...
  ```
- Все три endpoint'а `create_user_server` / `create_project_server` / `create_thread_server` **вызывают только `McpServerService.guard_and_persist(scope=..., owner_id=..., payload=...)`**. Логика SSRF/encryption/persist из роутера уезжает внутрь сервиса; маппинг request/response остаётся в роутере. Полный рефакторинг update/delete/test — **вне scope** этой итерации (не требуется для security-инвариантов; остаётся в backlog как tech debt).
- DI: `McpServerService` инжектируется через `Depends(get_mcp_server_service)` в `app/api/deps.py` (новая фабрика).

### 3.2 CUSTOM_INSTRUCTIONS_WRITE — UserMemoryService

- `app/services/user_memory.py:UserMemoryService.update_instructions(...)` (точное имя метода — `update_instructions`, не `update_custom_instructions`; строки 18, 32 в существующем коде):
  - В начале метода: `result = await self._guard.check(content, Checkpoint.CUSTOM_INSTRUCTIONS_WRITE, trace_ctx={"top_level": True, "user_id": str(user_id), "scope": "custom_instructions"})`.
  - INJECTION → 422, не сохраняется, `security_event=True` лог.
- Конструктор `UserMemoryService` расширяется параметром `guard: SecurityGuard`; DI через `app/api/deps.py` (существующий `get_user_memory_service` — расширить).
- Endpoint: `PUT /api/users/me/instructions` — путь уже существует, правок в роутере не требуется (только в сервисе).

### 3.3 KS_WRITE_REST — SphereService (условно, §11)

- `app/services/sphere.py:SphereService.update(*, project_id, content)` (фактическая сигнатура — update всей сферы целиком, не per-section; `section_id` в API нет — это одно поле content уровня проекта, строки 22–95):
  - В начале метода: `result = await self._guard.check(content, Checkpoint.KS_WRITE_REST, trace_ctx={"top_level": True, "user_id": str(user_id), "project_id": str(project_id), "scope": "ks"})`.
  - INJECTION → 422, не сохраняется (update не применяется), `security_event=True` лог.
- Конструктор `SphereService` расширяется параметром `guard: SecurityGuard`; DI через `app/api/deps.py`.
- **Переоценка §11 open question:** поскольку `update(*, project_id, content)` — единственная mutation-точка REST KS-write, guard обёртывается одним вызовом без рефакторинга KS-абстракций (fuzzy patch, section-level logic — на агент-path через tools, не затрагивается). **Включаем в scope Phase 3 безусловно** (риск «капитального рефакторинга» из §11 не материализовался при проверке реального API).
- KS writes через **agent path** (tool calls, fuzzy patch, section CRUD) проходят через Phase 2 `TOOL_CALL_ARG` — дубликат проверки на агент-пути не нужен.

### 3.4 GuardObserver REST-режим (§6.6)

- В Phase 1.4 уже реализован двурежимный `GuardObserver`. Для add-time: `trace_ctx` не имеет parent span → создаётся top-level Langfuse trace `security.<checkpoint>` с `propagate_attributes(user_id=..., trace_name=...)`. Reasoning видно для калибровки.
- Верификация: add-time INJECTION → в Langfuse появляется отдельный trace (не вложенный в agent-run).

### 3.5 Thread-level блок не ставится

- `thread_views.security_blocked` — **не** обновляется при add-time INJECTION (§5 brief: «add-time операции вне thread message flow»). Rate limiting / ban повторов — feat-007.

### 3.6 Phase 3 verification gate

- `make check` + `make test`.
- Ручная: POST /api/users/me/mcp-servers с описанием-injection → 422 + security_event лог + Langfuse top-level trace. PUT /api/users/me/instructions с injection-content → 422. PUT KS section с injection → 422 (если реализовали).
- Test cases: блок «3. Add-time» из test-cases.md.

## Критические файлы — сводка

### Модифицируются

| Файл | Phase | Что |
|---|---|---|
| `backend/app/agent/security/types.py` | 1 | Новая taxonomy: Checkpoint, Direction, DetectionLayer, GuardResult, ClassifierResult |
| `backend/app/agent/security/guard.py` | 1 | Переписать фасад под dict-based detectors registry, новая сигнатура check() |
| `backend/app/agent/security/canary.py` | 1 | Оставить generate_canary_token; detection-логика переезжает в CanaryDetector |
| `backend/app/agent/security/detectors.py` | 1 | Удалить, заменить на package detectors/ |
| `backend/app/agent/security/history_formatter.py` | 1 | Использовать по-прежнему из LLMClassifier |
| `backend/app/agent/prompt_builder.py` | 1 | Удалить Jinja, заменить на section-renderers + wrap_* helpers |
| `backend/app/agent/graph.py` | 1, 2 | _build_system_content под новые section-renderers; agent_node — TOOL_RESULT + TOOL_CALL_ARG inline; AgentContext — user_installed_tool_names |
| `backend/app/agent/runner.py` | 1, 2 | FINAL_OUTPUT mid/end-of-stream guard; normalize_error_message; user_installed_tool_names; mark_security_blocked |
| `backend/app/agent/graph_factory.py` | 2 | Проброс security_guard в build_graph |
| `backend/app/infra/llm.py` | 1 | create_guard_llm + create_summarization_llm* под ReasoningChatOpenAI по extra_body.include_reasoning |
| `backend/app/infra/logging.py` | 1 | Добавить security_event processor в shared_processors |
| `backend/app/models/thread_view.py` | 2 | security_blocked: Mapped[bool] |
| `backend/app/repositories/thread_view.py` | 2 | mark_security_blocked + is_security_blocked |
| `backend/app/services/agent_runner.py` | 2 | Message.redacted: bool = False |
| `backend/app/services/user_memory.py` | 3 | Метод `update_instructions` (фактическое имя) — добавить guard CUSTOM_INSTRUCTIONS_WRITE; конструктор принимает `guard: SecurityGuard` |
| `backend/app/services/sphere.py` | 3 | Метод `update(*, project_id, content)` — добавить guard KS_WRITE_REST; конструктор принимает `guard: SecurityGuard` |
| `backend/app/api/deps.py` | 1, 2, 3 | Новые Depends: SecurityGuard, SecurityConfig, require_unblocked_thread, get_mcp_server_service; расширить get_user_memory_service / get_sphere_service |
| `backend/app/api/routes/messages.py` | 2 | Depends(require_unblocked_thread) на POST |
| `backend/app/api/routes/mcp_servers.py` | 3 | Три endpoint'а (`create_user_server:177`, `create_project_server:284`, `create_thread_server:422`) делегируют в `McpServerService.guard_and_persist(scope=..., owner_id=..., payload=...)`; логика SSRF/encryption/persist переезжает в сервис |
| `frontend/src/features/chat/` | 1, 2 | §A3: (Phase 1) SSE-reducer заменяет content на заглушку при `security_block` после `text_chunk`; (Phase 2) рендерить заглушку при `message.redacted === true` в истории |
| `configs/agent.yaml` | 1 | Удалить секцию `security:` (мигрировала в security.yaml) |
| `configs/prompts/system.txt` | 1 | Полный текст из §6.14.1 (file fallback) |
| `configs/prompts/guard-classifier.txt` | 1 | Composite classifier из §6.14.4 (file fallback) |
| `doc/tech/conventions.md` | 1 | Новая секция «Reasoning LLMs» |

### Создаются

| Файл | Phase |
|---|---|
| `backend/app/agent/security/detectors/__init__.py` | 1 |
| `backend/app/agent/security/detectors/base.py` | 1 |
| `backend/app/agent/security/detectors/canary.py` | 1 |
| `backend/app/agent/security/detectors/unicode.py` | 1 |
| `backend/app/agent/security/detectors/fragment.py` | 1 |
| `backend/app/agent/security/detectors/paired.py` | 1 |
| `backend/app/agent/security/detectors/normalize.py` | 1 |
| `backend/app/agent/security/classifier.py` | 1 |
| `backend/app/agent/security/observer.py` | 1 |
| `backend/app/agent/security/config.py` | 1 |
| `configs/security.yaml` | 1 |
| `backend/app/services/mcp_server.py` (`McpServerService` — минимальный фасад, §A2) | 3 |
| `backend/tests/unit/agent/test_compose_for_llm.py` (§1.10 immutability + idempotency) | 1 |
| `backend/alembic/versions/<rev>_add_security_blocked_to_thread_views.py` | 2 |

Langfuse prompts (`system--{label}`, `security-classifier--{label}`) — сидятся при старте backend'а, версионируются в Langfuse, не в git.

## Переиспользуемые сущности (не дублировать)

| Компонент | Файл | Зачем |
|---|---|---|
| `PromptProvider` | `app/infra/prompt_provider.py` | Fetch prompts + file fallback. Используем как есть, `get_prompt("security-classifier", **slots)`, `get_prompt("system", **slots)` |
| `ReasoningChatOpenAI` | `app/infra/llm.py:14` | Reasoning extraction для OpenRouter — расширяем применение, не пишем свой |
| `_langfuse_observation` контекст | `app/agent/runner.py:51` | Существующая обёртка agent-run span — GuardObserver работает под ним |
| `_run_guard_with_observability` | `app/agent/runner.py:340` | Pattern для guardrail observation — обобщаем в GuardObserver, не переписываем |
| `check_canary_in_text`, `generate_canary_token` | `app/agent/security/canary.py`, `detectors.py` | Переносим под DeterministicDetector интерфейс |
| `detect_invisible_chars` | `app/agent/security/detectors.py` | Переносим в UnicodeDetector |
| `format_for_classifier` | `app/agent/security/history_formatter.py` | Используем как есть в LLMClassifier |
| `SettingsRepository`, `ModelConfigResolver` | `app/repositories/settings.py`, `app/services/model_config_resolver.py` | Не трогаем |
| `GraphFactory` | `app/agent/graph_factory.py` | Расширяем сигнатурой `security_guard` — не переписываем |
| `add_messages` reducer (`MessagesState`) | `langgraph.graph.MessagesState` | Replace-by-id — используем для synthetic AIMessage/ToolMessage с тем же id |
| `graph.aupdate_state(as_node="agent")` | LangGraph API | Для mid/end-of-stream FINAL_OUTPUT INJECTION — §6.5 brief |
| `BaseMessage.additional_kwargs` | LangChain Core | Хранение `security_redacted`, `original_detection_layer` — как `created_at` сегодня |
| `ThreadView` модель / репо | `app/models/thread_view.py`, `app/repositories/thread_view.py` | Расширяем поле + методы |

## End-to-end verification

**Инфраструктура (перед прогоном):**

```bash
make docker-up-db
make migrate                         # применяет новую миграцию thread_views.security_blocked
make dev                             # запускает backend (триггерит seed Langfuse prompts: system--production, security-classifier--production)
```

**Автоматический gate:**

```bash
make check                           # ruff + mypy: 0 errors
make check-fe                        # eslint + prettier + tsc (если был trouched, обычно не затрагивается)
make test                            # pytest: существующие тесты не регрессируют
```

**Ручная верификация по фазам — выборка ключевых кейсов из test-cases.md (полный прогон — отдельная итерация агент-исполнителя после ревью):**

| Сценарий | Phase | Ожидание |
|---|---|---|
| Легитимное сообщение | 1 | CLEAN verdict в Langfuse trace, `usage` и `reasoning` заполнены в generation, `system_redacted=false` на AIMessage |
| Injection в USER_INPUT | 1 | 200 + SSE `security_block` + `security_verdict=INJECTION` в trace; paired detector не триггерится (inbound), fragment может (backport) |
| Canary leak в FINAL_OUTPUT | 1 | mid-stream CanaryDetector hit → `security_block` + synthetic AIMessage с `security_redacted=true` в checkpointer; canary НЕ попадает в SSE-стрим дальше |
| Парафраз системного промпта в выводе | 1 | end-of-stream classifier → INJECTION; `security_redacted=true`; frontend заменяет текст на заглушку |
| Tool arg с системным промптом | 2 | agent_node TOOL_CALL_ARG guard → INJECTION; response.tool_calls очищен; `tools_condition → END`; `thread_views.security_blocked=true`; последующий POST /api/chats/{id}/messages → 403 |
| GET истории после thread-level block | 2 | 200; в DTO сообщение с `redacted=true` вместо утекшего content |
| Indirect injection через MCP scrape | 2 | TOOL_RESULT guard на следующей итерации → заглушка ToolMessage; LLM нейтрализует turn |
| MCP metadata с tool poisoning | 3 | POST /api/users/me/mcp-servers → 422; запись в БД нет; top-level Langfuse trace `security.mcp_metadata` |
| Custom instructions с override-prompt'ом | 3 | PUT /api/users/me/instructions → 422; security_event лог |
| Reasoning LLMs convention (§6.11) | 1 | Langfuse generation'ы от guard + summarizer содержат `additional_kwargs.reasoning`; cost по guard-модели ≠ 0 |

**Документы тестов:**
- Полный чек-лист — [test-cases.md](../../dev/my_pet_projects/learnflow-ai/.claude/worktrees/feat-006-security-2.0/doc/tasks/iterations/post-mvp/feat-006-security-2.0/test-cases.md) (82 кейса). Прогон — отдельная активность **после** архитекторского ревью реализации, выполняется агентом-тестировщиком по п. 7 workflow.md (верификация).

## Out of scope (этого плана)

- **Phase 4 — Eval infra (Track B):** harvest из Langfuse, `cases.jsonl`, HTTP runner, отчёт. Отдельный план, параллельно с Track A.
- ADR-018 — не в scope (согласовано с архитектором; архитектурные уточнения зафиксированы в §A1–A3 plan'а). Если по итогам реализации всплывут существенные отклонения — фиксируются в summary.md; ADR пишется при завершении только при существенных отклонениях.
- SUSPICIOUS → graduated response, automated ban — feat-007.
- File upload guard, async guard, SecurityObserver extraction — backlog.
- Полный рефакторинг MCP CRUD в service layer (update/delete/test endpoints) — в scope только минимальный `McpServerService.guard_and_persist` (§A2); остальное — tech debt, отдельная активность.
- Визуальный дизайн redaction-заглушки (цвет, иконка, tooltip, анимация) — plain-text заглушка достаточна (§A3); полноценное UI-решение — отдельная frontend-итерация при необходимости.

## Финальный шаг — review gate

**После прохождения `make check` / `make check-fe` / `make test` + ручной верификации выборки сценариев выше:**

1. Зафиксировать diff `git status` / `git diff --stat` — пройтись по списку изменённых файлов, убедиться что нет неожиданных правок вне scope Phases 1–3.
2. Подготовить короткий сводный пост для архитектора:
   - Что реализовано по фазам (ссылки на ключевые файлы).
   - Какие open questions §11 закрыты и как (форма return'а TOOL_RESULT INJECTION, порядок guard vs endpoint-валидации, судьба KS_WRITE_REST, формат `<untrusted_tool_description>`).
   - Обнаруженные отклонения от brief'а — если есть.
   - Langfuse trace-ссылки на репрезентативные сценарии.
3. **Дождаться прогона test-cases.md архитектором совместно с агентом-эвалюатором** (по §п.3 workflow.md «Верификация»). Агент-имплементатор на этом этапе **не двигается** к коммиту / push'у / актуализации доки — пока архитектор и эвалюатор не прошлись по чек-листу из [test-cases.md](test-cases.md) (82 кейса) и не зафиксировали результат. Обратная связь может включать:
   - Ранее незамеченные failing кейсы → правки в коде/конфиге.
   - Отклонения от ожидаемого поведения, требующие доработки.
   - Запросы уточнения в логах/трейсах/метаданных.
4. **Применить обратную связь** — итеративно, каждый раунд правок остаётся несоcommitted (чтобы архитектор видел полный текущий diff). Повторный прогон затронутых test-cases после каждой правки.
5. **После явного approve** от архитектора (все test-cases либо ✅ PASS, либо явно ⚠️ DEFERRED с фиксацией причины; критичных FAIL нет):
   - `git add` → `git commit` (Conventional Commits: `feat(agent): sec 2.0 universal io guard` — по conventions.md, scope `agent`).
   - `git push -u origin pmvp/feat-006-security-2.0`.
   - PR в `develop` (gh pr create) — **только после одобрения архитектором**; в body — ссылки на design-brief, plan, test-cases, заполненный чек-лист.
6. summary.md и обновления документации (`doc/security/architecture.md` — добавить новые checkpoints + coverage map; `doc/index.md` — навигация, если появились новые документы) — **после merge PR в develop**, в рамках шага «4. Завершение» workflow.md.

**Ключевой инвариант:** коммит и push **не происходят** до совместного прогона test-cases архитектором + эвалюатором. Агент-имплементатор отвечает за готовность к прогону (инфраструктура поднята, сценарии воспроизводимы), не за самостоятельную сдачу итерации.

**Контрольная точка:** до явного approve — никаких коммитов и push'ей. Правки применяются поверх несоcommitted changes, чтобы архитектор видел полный текущий diff при каждом раунде ревью.
