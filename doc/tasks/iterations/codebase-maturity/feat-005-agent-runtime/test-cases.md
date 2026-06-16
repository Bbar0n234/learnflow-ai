# feat-005 Agent Runtime — тест-кейсы

Страховка рефакторинга agent runtime. Две части: **точечные автотесты** (юнит,
прогоняются `make test`) и **ручные smoke-кейсы** (агентный поток на стенде).

## Что менялось (затронутые участки)

- `infra/llm.py` — фабрики LLM свёрнуты в `_build_chat_model`, `ReasoningChatOpenAI` безусловно, удалены 2 мёртвые функции.
- `model_config_resolver.py` — публичный `default()`.
- `tools/user_memory.py` — `ToolRuntime` + `RuntimeError` при отсутствии store/context.
- Runner расщеплён: `AgentRunTracer`, `RuntimeSecurityEnforcer`, `CheckpointHistory`, `StreamEventMapper`.
- `infra/langfuse.py` — `init_langfuse() -> bool`, module-global `langfuse_enabled` удалён, флаг через DI.

## Часть 1. Точечные автотесты (выполнено, 46 PASS)

Прогон: `make test`. Файлы (`backend/tests/`):

| Файл | Покрывает |
|------|-----------|
| `test_llm_factories.py` | безусловный `ReasoningChatOpenAI` (флаг true/false/нет), max_tokens/temperature, проброс settings, удаление мёртвых фабрик |
| `test_model_config_resolver.py` | `default()` ← agent.yaml, пустой extra_body → None |
| `test_user_memory_tools.py` | aput/adelete + namespace, `RuntimeError` без store/context |
| `test_stream_event_mapper.py` | tool_start / tool_end / artifact_created (+ pop `type`) |
| `test_agent_run_tracer.py` | enabled=False no-op, degrade при сбое клиента, сборка mid-stream observation |
| `test_checkpoint_history.py` | raw_messages, history (+редакция), last_ai_message_id, latest_redaction (+граница по HumanMessage) |
| `test_runtime_security_enforcer.py` | 4 чекпоинта: verdict→outcome, payload редакции (content/id/флаги/layer), block_reason |
| `test_langfuse_init.py` | `init_langfuse()` → bool (нет ключей / auth fail / success), `ensure_*` skip при disabled |

## Часть 2. Ручные smoke-кейсы (агентный поток, docker-стенд)

Предусловие: `make docker-up` (или `make docker-up-db` + `make dev`), валидный LLM-ключ. Кейсы без ключа помечаются SKIP.

| ID | Сценарий | Шаги | Ожидаемо |
|----|----------|------|----------|
| SM-1 | Обычный чат | Отправить сообщение в чат | SSE: серия `text_chunk` → `final_output_review_started`/`_complete`; ответ сохранён в истории |
| SM-2 | Ход с инструментом | Запрос, провоцирующий tool call (например, создать артефакт) | SSE: `tool_start` → `tool_end`; при create_artifact — `artifact_created` с `artifact_type`; артефакт в БД |
| SM-3 | Инъекция на входе | Отправить prompt-injection как user input | SSE: `security_block`; thread помечен blocked; в истории — redacted-плейсхолдер (исходный prompt + заглушка) |
| SM-4 | Инъекция в финальном выводе | Спровоцировать injection в ответе модели (через tool result / canary) | SSE: `security_block`; ответ в истории заменён на redacted-заглушку (тот же message id) |
| SM-5 | Compaction | Длинный тред > порога суммаризации | старые сообщения суммаризированы (summarizer на `ReasoningChatOpenAI`); диалог продолжается; история не теряется |
| SM-6 | Langfuse off | Поднять стенд без `LANGFUSE_*` ключей | приложение стартует, чат работает, в логах нет ошибок трейсинга; `trace_id` в SSE отсутствует |
| SM-7 | Langfuse on + reasoning | Стенд с Langfuse + reasoning-моделью | трейс `agent-run` появляется; `additional_kwargs.reasoning` в generation; security_verdict score проставлен |
| SM-8 | KS + user memory | Через чат вызвать сохранение секции KS и user memory | секции/память сохраняются в Store; видны в системном промпте следующего хода; REST KS/memory отдают данные |

### Регрессионный фокус (что не должно сломаться)

- Порядок security-чекпоинтов: USER_INPUT → mid-stream → FINAL_OUTPUT → in-graph inspection.
- `get_history` / `get_last_ai_message_id` отдают то же, что до рефактора (redacted-флаг, created_at, исключение tool-call ходов).
- Отмена генерации (`cancel`) по-прежнему прерывает стрим с `error`-событием.
- Cascade `ModelConfigResolver.resolve` (thread→project→user→langfuse→config) не затронут.

## Результаты прогона

**Часть 1 (автотесты):** 46 PASS (см. выше), независимо отревьюены, заархивированы.

**Часть 2 (ручной smoke):** прогнан на изолированном стенде (PG :5440 + backend :8080,
без конфликта со стеком feat-006).
- **SM-1 — PASS.** `text_chunk`-стрим → `final_output_review_started/complete` → `done`.
- **SM-6 — PASS.** Langfuse off → `trace_id:""`, ошибок нет, трейсер no-op.
- **SM-3 — PASS (после фикса).** Первый прогон вскрыл пред-существующий дедлок
  (`touch` в request-сессии держит row-lock `thread_views`, `_mark_blocked` открывал вторую
  сессию → взаимоблокировка ≈120с). Фикс: метить blocked через сессию запроса (вариант A).
  После фикса: `security_block` за ~6.6с, `security_blocked=true`, redacted-плейсхолдер в истории.
- **SM-2 / SM-4 / SM-5 / SM-7 / SM-8 — не прогонялись** в этой сессии (ядро ценности — wiring +
  guard — закрыто SM-1/SM-3/SM-6). Кандидаты на добивку при наличии стенда.

Стенд после прогона убран (контейнер `feat005-smoke-pg` удалён, временный `.env.local` с ключом удалён).
