# Implementation Plan: feat-004 — Prompt Injection Protection

## Context

LearnFlowAI не имеет защиты от prompt injection. Threat model, research и design brief проработаны (`doc/security/`, `doc/tasks/iterations/post-mvp/feat-004-security/`). Этот план покрывает реализацию MVP-защиты: input guard (SecurityGuard), system prompt hardening, canary token output check, Langfuse observability.

Проект участвует в Red Team / Blue Team формате. Репозиторий open-source — безопасность через качество механизмов (принцип Кирхгоффа).

## References

- **Tasklist:** `doc/tasks/tasklist-post-mvp.md` — feat-004, Definition of Done
- **Design brief:** `doc/tasks/iterations/post-mvp/feat-004-security/design-brief.md` — архитектура, интерфейсы, 20 decisions
- **Langfuse decisions:** `doc/tasks/iterations/post-mvp/feat-004-security/langfuse-observability-decisions.md`
- **Test cases:** `doc/tasks/iterations/post-mvp/feat-004-security/test-cases.md` — 71 кейс, 4 layers
- **Workflow:** `doc/workflow.md` — итерация, верификация, summary
- **Conventions:** `doc/tech/conventions.md` — git, naming, logging, code quality
- **Langfuse experiment:** `doc/tasks/iterations/post-mvp/feat-004-security/langfuse_security_experiment.py` — проверенная референсная реализация Langfuse v4 observability (score, guardrail, metadata)
- **Security research:** `doc/security/` — threat-model, defense architecture, hardening techniques, guard reference

## API Verification (быстро меняющиеся инструменты)

| Инструмент | Версия | Верификация | Результат |
|-----------|--------|-------------|-----------|
| Langfuse SDK | 4.0.1 | inspect пакета + эксперимент (`langfuse_security_experiment.py`) | `start_as_current_observation(as_type="guardrail")` — ✅. `LangfuseGuardrail` → `create_event`, `start_as_current_observation`, `update`, `score_trace`. `TextPromptClient.compile(**kwargs)` — ✅. **Паттерны из эксперимента:** `root_span.score_trace(name, value, data_type="CATEGORICAL")` для score; явное создание nested observations (event, generation) внутри guardrail; `root_span.update(metadata=...)` для trace metadata |
| LangGraph | 1.1.3 | inspect пакета | `AsyncPostgresSaver.aget_tuple(config) -> CheckpointTuple | None` — ✅, без изменений. CheckpointTuple: config, checkpoint, metadata, parent_config, pending_writes |
| langchain-core | 1.2.18 | inspect пакета | `BaseChatModel.ainvoke(input, config) -> AIMessage` — ✅. Message types (HumanMessage, AIMessage, ToolMessage, BaseMessage) — ✅ |
| langchain-openai | 1.1.11 | inspect пакета | `ChatOpenAI` — ✅, конструктор через Pydantic (model, api_key, base_url, temperature — в model_fields) |

## Decisions (при планировании)

**Q1: Guard model** → `google/gemini-3.1-flash-lite-preview` (решение архитектора). Pricing: input $0.25/1M, output $1.50/1M, cache read $0.025/1M. Добавить в `agent.yaml` секцию `security.guard_model` и в список `models` для Langfuse cost tracking.

---

## Phases

### Phase 0: Подготовка ветки

Cherry-pick коммита с Langfuse экспериментом из develop:
```
git cherry-pick cfb3e11
```
Этот коммит добавляет `langfuse_security_experiment.py` в директорию итерации — референсная реализация для Phase 6.

### Phase 1: Foundation — Types, Config, Environment

**Новые файлы:**
- `backend/app/agent/security/__init__.py` — re-export публичных имён
- `backend/app/agent/security/types.py` — `SecurityVerdict` (enum), `GuardResult` (Pydantic), `SecurityConfig` (Pydantic)

**Модификации:**
- `backend/app/agent/config.py` — добавить `SecurityConfig` в `AgentConfig` как опциональное поле `security: SecurityConfig | None = None`
- `backend/app/config.py` (Settings) — добавить `canary_secret: str = ""`
- `configs/agent.yaml` — добавить секцию `security` (`guard_model: google/gemini-3.1-flash-lite-preview`, `guard_extra_body: {}`, `max_retries: 3`, `temperature: 0.0`). Добавить модель в `models` для cost tracking
- `.env.example` — добавить `CANARY_SECRET=`

### Phase 2: Pure Functions (leaf, без зависимостей)

**Новые файлы:**
- `backend/app/agent/security/detectors.py`:
  - `detect_invisible_chars(text: str) -> bool` — Unicode categories Cf, Co, Cn; fast path `ord(char) > 127`
  - `check_canary_in_text(text: str, canary_token: str) -> bool` — `canary_token in text`
- `backend/app/agent/security/canary.py`:
  - `generate_canary_token(thread_id: str, secret: str) -> str` — `HMAC-SHA256(secret, thread_id).hex()[:16]`
- `backend/app/agent/security/history_formatter.py`:
  - `format_for_classifier(messages: list[BaseMessage], current_content: str) -> str` — XML-обёртка `<conversation_history>`, ролевые префиксы `[USER]`/`[ASSISTANT]`/`[TOOL:{name}]`

### Phase 3: Classifier Prompt + PromptProvider

**Новый файл:**
- `configs/prompts/guard-classifier.txt` — текст промпта из design-brief (с `{{ checkpoint }}` переменной)

**Модификации:**
- `backend/app/infra/prompt_provider.py` — расширить `get_prompt(name, **variables)` для поддержки переменных:
  - Langfuse path: `prompt.compile(**variables)` (уже поддерживается `TextPromptClient`)
  - File fallback path: `Template(text).render(**variables)` через Jinja2 (уже в зависимостях)
  - Backwards compatible: существующие вызовы без kwargs продолжают работать
- `backend/app/main.py`:
  - `_seed_prompts` — добавить `"guard-classifier"` в список промптов для seed
  - `_load_prompt_config` — добавить ветку для `"guard-classifier"`: `{"model": agent_config.security.guard_model}` (аналогично system/summarization, строки 64-75)
- `backend/scripts/sync_prompts.py`:
  - Добавить `"guard-classifier"` в `PROMPT_NAMES`
  - Добавить обработку `"guard-classifier"` в `_update_agent_yaml()`: синхронизация `security.guard_model` из Langfuse config (аналогично llm.model и summarization.model)

### Phase 4: SecurityGuard Orchestrator

**Новый файл:**
- `backend/app/agent/security/guard.py` — класс `SecurityGuard`:
  - `__init__(guard_llm, prompt_provider, config: SecurityConfig)`
  - `async check(content, *, history, checkpoint, canary_token) -> GuardResult`
  - Pipeline: canary-in-input → unicode detector → LLM classify (с retry + graceful degradation)
  - Graceful degradation: exception при LLM call → CLEAN + warning log
  - Retry: невалидный ответ classifier → retry до max_retries, все исчерпаны → CLEAN

**Модификация:**
- `backend/app/infra/llm.py` — добавить `create_guard_llm(settings, security_config) -> BaseChatModel` — plain ChatOpenAI (без reasoning), temperature=0.0

### Phase 5: System Prompt Hardening

**Модификации:**
- `backend/app/agent/prompt_builder.py` — заменить `SYSTEM_MESSAGE_TEMPLATE` на hardened template из design-brief:
  - `<system_instructions>` с instruction hierarchy, confidentiality, canary token
  - `<instruction_reminder>` sandwich defense после untrusted секций
  - `system.txt` (based_prompt) включается как есть (D18)
  - Новый параметр `canary_token: str = ""` в `build_system_message()`
- `backend/app/agent/graph.py`:
  - Добавить `canary_token: str = ""` в `AgentContext`
  - `_build_system_content()` → добавить параметр `canary_token`, передать в `build_system_message()`
  - `agent_node` → передать `runtime.context.canary_token` в `_build_system_content()`

### Phase 6: Runner Integration — Security Flow + Langfuse

**Модификация `backend/app/agent/runner.py`:**

1. **Constructor** — добавить `security_guard: SecurityGuard | None = None` и `canary_secret: str = ""`

2. **stream() — pre-graph check:**
   - Генерация canary: `generate_canary_token(str(thread_id), canary_secret)`
   - Получение history из checkpointer (для classifier context)
   - `guard_result = await security_guard.check(content, history=history, checkpoint="user_input", canary_token=canary_token)`
   - INJECTION → yield `security_block` event + return
   - SUSPICIOUS → log prominently, продолжить
   - Передача canary_token в AgentContext

3. **stream() — streaming loop (canary output check):**
   - В цикле `mode == "messages"`: после `full_response += chunk`, проверить `check_canary_in_text(full_response, canary_token)`
   - Canary found → yield `security_block(reason="canary_leak")` + return

4. **Langfuse observability** (внутри `_langfuse_observation` context):
   Референс: `langfuse_security_experiment.py` — проверенные паттерны Langfuse v4.

   **Guardrail observation** (runner создаёт контекст):
   - `root_span.start_as_current_observation(as_type="guardrail", name="input-guard", input=content)`
   - Внутри guardrail context: SecurityGuard создаёт nested observations через Langfuse global context (fail-safe):
     - `guard_obs.create_event(name="unicode-detector", input=..., output=...)`
     - `guard_obs.start_as_current_observation(as_type="generation", name="llm-classifier", model=..., input=..., model_parameters=...)` — явное создание, НЕ через auto-instrumentation
   - После check: `guard_obs.update(metadata={guard_model, verdict_raw, unicode_chars_found, degraded?, error?}, level=verdict_to_level)`

   **Score** (на trace):
   - `root_span.score_trace(name="security_verdict", value=verdict, data_type="CATEGORICAL", comment=block_reason)`
   - Canary leak → перезаписать: `root_span.score_trace(name="security_verdict", value="INJECTION", data_type="CATEGORICAL", comment="canary_leak")`

   **Trace metadata** (при инцидентах):
   - `root_span.update(metadata={"blocked": True, "detection_layer": ..., "block_reason": ...}, level="ERROR")`

   **Canary leak event**:
   - `root_span.create_event(name="canary-detected", input=..., output=..., level="ERROR")`

   **Output на span:**
   - Blocked by guard: `"Запрос заблокирован из соображений безопасности."`
   - Canary leak: `"Ответ заблокирован: обнаружена потенциальная утечка системной информации."`
   - Normal: `full_response`

   **Level mapping**: CLEAN → DEFAULT, SUSPICIOUS → WARNING, INJECTION → ERROR, degradation → WARNING

   **Важно**: SecurityGuard получает implicit dependency на Langfuse через global context (аналогично эксперименту). Nested observations создаются внутри SecurityGuard, обёрнутые в try/except. Если Langfuse недоступен — pipeline работает без observability.

5. **SSE event:**
   ```python
   StreamEvent(type="security_block", data={"reason": "..."})
   ```
   reason values: `invisible_chars`, `prompt_injection`, `canary_in_input`, `canary_leak`

### Phase 7: Startup Wiring (main.py)

**Модификация `backend/app/main.py` (lifespan):**

1. **Guard LLM** — `create_guard_llm(settings, agent_config.security)` (только если security секция есть в config)
2. **SecurityGuard** — `SecurityGuard(guard_llm, prompt_provider, agent_config.security)`
3. **LangGraphAgentRunner** — передать `security_guard=security_guard, canary_secret=settings.canary_secret`
4. **Score config** — `_ensure_score_config` в `backend/app/infra/langfuse.py` (строки 46-58): добавить `security_verdict` (CATEGORICAL) аналогично `user-feedback`
5. **Seed prompt** — guard-classifier добавлен в Phase 3

### Phase 8: Frontend + ChatService

**Модификации:**
- `frontend/src/shared/api/types.ts` — добавить `security_block` в `SSEEvent` union:
  ```typescript
  | { type: "security_block"; reason: string }
  ```
- `frontend/src/features/chat/hooks/useAgentStream.ts` — handler для `security_block`:
  - `terminated = true`
  - `endStream()`
  - Вызвать `onError` с понятным сообщением (или отдельный callback `onSecurityBlock`)
- `backend/app/services/chat.py` — добавить `security_block` как terminal event:
  ```python
  if event.type in ("error", "security_block"):
      had_error = True
  ```

### Phase 9: Quality Gates + Финализация

1. `make check` (ruff + mypy) — 0 errors
2. `make check-fe` (ESLint + Prettier + tsc) — 0 errors
3. Проверить миграции (если есть) — feat-004 не добавляет таблицы, миграций быть не должно
4. Smoke test: `make dev`, отправить сообщение → ответ приходит (security guard не блокирует легитимные запросы)

### Phase 10: Verification (test-cases.md)

Верификация по `test-cases.md` (71 кейс, 4 layers) проводится **отдельным агентом-evaluator** совместно с архитектором — не агентом-реализатором. Агент-реализатор получает обратную связь и при необходимости вносит доработки.

Агент-реализатор отвечает за:
- Прохождение quality gates (Phase 9: `make check`, `make check-fe`)
- Базовый smoke test: `make dev` → отправить сообщение → ответ приходит
- Передача готовой реализации на верификацию

### Phase 11: Завершение

1. Дождаться ревью и обратной связи от архитектора
2. Post-implementation summary (`summary.md`): отклонения, решения
3. Актуализация документации (затронутые doc/tech/ файлы)
4. Коммит и пуш — только после апрува архитектора

---

## File Change Summary

### New files (7)
| File | Purpose |
|------|---------|
| `backend/app/agent/security/__init__.py` | Module exports |
| `backend/app/agent/security/types.py` | SecurityVerdict, GuardResult, SecurityConfig |
| `backend/app/agent/security/detectors.py` | detect_invisible_chars, check_canary_in_text |
| `backend/app/agent/security/canary.py` | generate_canary_token (HMAC) |
| `backend/app/agent/security/history_formatter.py` | format_for_classifier (XML + role prefixes) |
| `backend/app/agent/security/guard.py` | SecurityGuard orchestrator |
| `configs/prompts/guard-classifier.txt` | Classifier prompt file fallback |

### Modified files (15)
| File | Change |
|------|--------|
| `backend/app/agent/config.py` | SecurityConfig + AgentConfig.security field |
| `backend/app/config.py` | Settings.canary_secret |
| `backend/app/infra/prompt_provider.py` | get_prompt(**variables) support |
| `backend/app/infra/llm.py` | create_guard_llm() |
| `backend/app/agent/prompt_builder.py` | Hardened template + canary_token param |
| `backend/app/agent/graph.py` | AgentContext.canary_token + threading |
| `backend/app/agent/runner.py` | SecurityGuard integration, canary output check, Langfuse observability |
| `backend/app/infra/langfuse.py` | _ensure_score_config: security_verdict (CATEGORICAL) |
| `backend/app/main.py` | Guard LLM, SecurityGuard wiring, _load_prompt_config, prompt seed |
| `backend/app/services/chat.py` | security_block terminal event |
| `frontend/src/shared/api/types.ts` | security_block SSE event type |
| `frontend/src/features/chat/hooks/useAgentStream.ts` | security_block handler |
| `configs/agent.yaml` | security section |
| `.env.example` | CANARY_SECRET |
| `backend/scripts/sync_prompts.py` | guard-classifier in PROMPT_NAMES |
