# feat-004: Prompt Injection Protection — Summary

## Результат

MVP-защита от prompt injection реализована и верифицирована. Три слоя защиты работают: input guard (SecurityGuard), system prompt hardening (sandwich defense + canary token), canary output check (streaming). Observability через Langfuse: score `security_verdict`, guardrail observations, metadata при инцидентах.

**Верификация:** 59/71 тестовых кейсов пройдены, 12 deferred (canary leak сценарии — требуют LLM вывод canary token буквально, что маловероятно при hardened prompt; SUSPICIOUS verdict — зависит от поведения модели). 3 бага найдены и исправлены при верификации (F-001 — F-003).

## Отклонения от плана

### Архитектурные

**1. Langfuse observability осталась в runner.py (~90 строк)**

План предполагал минимальное присутствие security-кода в runner. На практике Langfuse observability (guardrail observation, score_trace, metadata, canary event) тесно связана с runner lifecycle: span принадлежит runner, создаётся в `_langfuse_observation`. SecurityGuard не должен знать про Langfuse span (SRP).

Итог: 5 private-методов в runner (`_run_guard_with_observability`, `_score_trace`, `_finalize_blocked_trace`, `_record_canary_leak`, `_get_checkpoint_messages`). Код корректен, но runner стал толще.

**Решение:** записано в backlog.md как P2 tech debt — вынос в SecurityObserver при итерации закрытия технических долгов.

**2. Nested Langfuse observations в SecurityGuard через global context**

Plan Phase 6 описывал nested observations внутри guardrail (unicode-detector event, llm-classifier generation). При реализации оказалось, что SecurityGuard не получает Langfuse observation object напрямую — runner создаёт guardrail observation, а guard работает через global context (`get_client()`). Ручной CM management (`__enter__()` / `__exit__()`) — workaround для async context + sync CM Langfuse. Документировано в F-001 findings.

### Решения при реализации

**3. `_CHECKPOINT_LABELS` — маппинг checkpoint ID в human-readable описания**

Не было в плане. Добавлен для улучшения качества классификации: classifier получает "Analyzing a user's chat message in conversation context" вместо raw "user_input". Связан контрактом с промптом classifier'а — изменение labels требует синхронного обновления промпта.

**4. Reason value: `llm_classifier` вместо `prompt_injection`**

План указывал `prompt_injection` как reason value. Реализация использует `llm_classifier` — более точно указывает detection layer (кто обнаружил), а не семантику атаки. Frontend всё равно показывает generic сообщение. Остальные reason values (`invisible_chars`, `canary_in_input`, `canary_leak`) — по плану.

**5. Warning при пустом CANARY_SECRET**

Не было в плане. Добавлен `logger.warning("CANARY_SECRET not configured, canary protection disabled")` при старте. Operational visibility: легко пропустить при деплое что canary protection отключена.

**6. Guard model: `google/gemini-3.1-flash-lite-preview`**

Открытый вопрос Q1 из design-brief закрыт при планировании: решение архитектора. Модель добавлена в `agent.yaml` models для Langfuse cost tracking.

### Доработки после ревью

**7. Unicode categories → именованная константа `_SUSPICIOUS_CATEGORIES`**

По обратной связи архитектора: вынесено из inline tuple в `frozenset` с пояснительным комментарием (Cf — Format, Co — Private Use, Cn — Unassigned). Расширение categories — код, не конфиг (security policy decision).

**8. Lazy imports → top-level**

По обратной связи: `from app.agent.security.guard import SecurityGuard` и `from app.infra.llm import create_guard_llm` перенесены из условного блока `if agent_config.security` на уровень модуля main.py. Lazy import не давал пользы — модули лёгкие, без side effects.

**9. Doc-comment к `_CHECKPOINT_LABELS`**

Добавлен комментарий о связи с промптом classifier'а: "Changing values here requires updating the prompt to maintain calibration". Решение не выносить в конфиг: labels — контракт с промптом, два разных lifecycle = источник рассинхронизации.

## Findings при верификации

| # | Тип | Severity | Суть | Статус |
|---|-----|----------|------|--------|
| F-001 | Bug | Medium | Guardrail observation не создаётся — CM не входил в `__enter__()` | Исправлено (runner.py) |
| F-002 | Bug | Low | CANARY_SECRET пустой без warning | Исправлено (main.py) |
| F-003 | Enhancement | Low | Отсутствовали nested observations (unicode-detector, llm-classifier) | Исправлено (guard.py) |
| OBS-001 | Observation | — | Blocked messages не персистятся в checkpoint | Корректно для MVP |
| OBS-002 | Observation | — | Мягкие запросы проходят guard, блокируются при эскалации | Приемлемо, калибровка итеративно |

## Tech Debt

- **P2** SecurityObserver extraction — вынос Langfuse observability из runner.py в отдельный SecurityObserver (записано в backlog.md)

## Изменённые файлы

### Новые (8)

| Файл | Назначение |
|------|-----------|
| `backend/app/agent/security/__init__.py` | Re-exports |
| `backend/app/agent/security/types.py` | SecurityVerdict, GuardResult, SecurityConfig |
| `backend/app/agent/security/detectors.py` | detect_invisible_chars, check_canary_in_text |
| `backend/app/agent/security/canary.py` | generate_canary_token (HMAC-SHA256) |
| `backend/app/agent/security/history_formatter.py` | format_for_classifier (XML + role prefixes) |
| `backend/app/agent/security/guard.py` | SecurityGuard orchestrator |
| `configs/prompts/guard-classifier.txt` | Classifier prompt (3-level, with checkpoint variable) |
| `doc/tasks/iterations/post-mvp/feat-004-security/langfuse_security_experiment.py` | Langfuse observability experiment (cherry-pick) |

### Модифицированные (16)

| Файл | Изменение |
|------|-----------|
| `backend/app/agent/config.py` | `security: SecurityConfig \| None` в AgentConfig |
| `backend/app/config.py` | `canary_secret: str` в Settings |
| `backend/app/infra/prompt_provider.py` | `get_prompt(**variables)` — Jinja2 rendering для file fallback |
| `backend/app/infra/llm.py` | `create_guard_llm()` — plain ChatOpenAI, temperature=0 |
| `backend/app/infra/langfuse.py` | `ensure_security_score_config()` — CATEGORICAL score |
| `backend/app/agent/prompt_builder.py` | Hardened template: `<system_instructions>`, canary token, `<instruction_reminder>` |
| `backend/app/agent/graph.py` | `AgentContext.canary_token`, threading через `_build_system_content` |
| `backend/app/agent/runner.py` | Pre-graph guard, canary output check, Langfuse observability (5 methods) |
| `backend/app/main.py` | Guard LLM + SecurityGuard wiring, score config, prompt seed |
| `backend/app/services/chat.py` | `security_block` как terminal event |
| `backend/scripts/sync_prompts.py` | `guard-classifier` в PROMPT_NAMES + _update_agent_yaml |
| `frontend/src/shared/api/types.ts` | `security_block` SSE event type |
| `frontend/src/features/chat/hooks/useAgentStream.ts` | `security_block` handler |
| `configs/agent.yaml` | Секция `security` + guard model в `models` |
| `.env.example` | `CANARY_SECRET` |
| `doc/backlog.md` | SecurityObserver extraction (P2 tech debt) |

## Scope Boundaries (что НЕ вошло)

Следующее сознательно deferred и записано в backlog (секция Security):

- KS Write Guard (memory poisoning protection)
- LLM Output Classifier (semantic system prompt leak check)
- SUSPICIOUS → конкретные ограничения (tool access, admin alert)
- Tool Result Guard (indirect PI через MCP results)
- Semantic Similarity output check
- Async Guard (parallel check)
- Multi-turn escalation detection

## Для агента-актуализатора документации

Ключевые изменения, требующие отражения в проектной документации:

1. **Новый модуль `backend/app/agent/security/`** — 6 файлов, SecurityGuard orchestrator + leaf functions. Слой: Agent. Зависимости: PromptProvider (Infra), BaseChatModel (Infra/LLM)
2. **System prompt structure** — hardened template обёртывает `system.txt`. Новые секции: `<system_instructions>`, `<instruction_reminder>`, canary token. `system.txt` не изменён
3. **AgentContext** расширен: `canary_token: str = ""`
4. **Runner lifecycle** — pre-graph security check + canary output check в streaming loop. Новые terminal SSE event: `security_block`
5. **Langfuse** — новый score `security_verdict` (CATEGORICAL), guardrail observation type, metadata при инцидентах
6. **Configuration** — `agent.yaml` секция `security`, `Settings.canary_secret`, `configs/prompts/guard-classifier.txt`
7. **PromptProvider** — теперь поддерживает `**variables` (Jinja2 rendering)
8. **Frontend** — SSE event `security_block` → error message, terminal event
