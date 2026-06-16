# feat-005 Agent Runtime Slice — Summary

Аудит agent runtime через skill `langgraph-patterns` + общие паттерны чистого
кода; целевой рефакторинг runner'а и закрытие точечных техдолгов.

## Что сделано

### A. ReasoningChatOpenAI everywhere + дедупликация фабрик
Пять почти идентичных фабрик LLM в `infra/llm.py` сведены к одному приватному
билдеру `_build_chat_model`. `ReasoningChatOpenAI` создаётся **безусловно** (это
безопасный надкласс `ChatOpenAI`: извлечение reasoning — no-op без поля
`reasoning`), ветка `... if include_reasoning else ChatOpenAI` убрана. Удалены
две мёртвые функции: `create_llm`, `create_summarization_llm_from_prompt_config`
(не вызывались нигде). Живые: `create_llm_from_config`, `create_summarization_llm`,
`create_guard_llm`. Конвенция обновлена в `conventions.md § Reasoning LLMs`.

### B. langfuse_enabled — убран module-global (DI)
`init_langfuse()` теперь возвращает `bool` вместо мутации module-global
`langfuse_enabled` через `global`. Флагом владеет `lifespan` и инжектит его:
`AgentRunTracer(enabled=...)`, `GuardObserver(enabled=...)`, `ensure_*(enabled=...)`.
Три request-scope-чтения глобала через lazy-import (runner ×2, observer)
устранены. Запись об «известном исключении» из `conventions.md § FastAPI`
заменена описанием DI-подхода. Механика: SDK Langfuse v4 при `tracing_enabled=False`
сам отдаёт no-op-трейсер, но наш флаг несёт сверх этого результат `auth_check()`,
поэтому сохранён — только переехал из модуля в DI.

### C. Декомпозиция runner'а (separation of concerns)
`runner.py` (844 стр., God-object-дрейф) разбит. `LangGraphAgentRunner` оставлен
тонким оркестратором контракта `AgentRunner`; сквозные заботы вынесены в
инжектируемых коллабораторов:
- `tracing.py` — `AgentRunTracer` / `AgentRunSpan` (Langfuse-спан рана; fail-safe).
- `runtime_security.py` — `RuntimeSecurityEnforcer` + `SecurityOutcome` (4 рунтайм-чекпоинта guard'а, редакция, mark-blocked; `check_*` возвращает `SecurityOutcome | None`, runner решает `yield`).
- `checkpoint_history.py` — `CheckpointHistory` (единственное место знания формы `channel_values["messages"]`).
- `stream_events.py` — `StreamEventMapper` (updates → SSE).
Проектное решение зафиксировано в `conventions.md § Agent Runtime`.

### D. Инкапсуляция ModelConfigResolver
Добавлен публичный `default()`; runner больше не лезет в приватные
`_from_llm_config`/`_llm_config`.

### E. user_memory tools
Переведены с `runtime: Any` на `ToolRuntime`; при отсутствии store/context
бросают `RuntimeError` (было — error-строка), выравнивание с KS-тулзами.
*Примечание:* keyword-only `runtime` в `update_section` (KS) оставлен — он
вынужден дефолтными параметрами перед ним, не несогласованность.

### Латентный баг (поймано тестами)
Циклический импорт `app.infra.llm ↔ app.agent` (classifier импортирует
`extract_usage`). Фикс: аннотационные импорты `app.*` в `llm.py` под
`TYPE_CHECKING` + `from __future__ import annotations`.

## Подтверждения по skill (без правок)
ReAct на pre-defined edges (Command API не нужен), shared checkpointer/store
через `async with` в lifespan, multi-mode streaming — соответствуют
`langgraph-patterns`. HITL/Send/operator.add в домене не используются.

## Тесты
- **Точечные автотесты: 46 PASS** (8 файлов). Покрыт критичный путь
  (`RuntimeSecurityEnforcer`), изменённые контракты (`init_langfuse → bool`,
  user_memory RuntimeError, безусловный `ReasoningChatOpenAI`), коллаборáторы.
  Независимо отревьюены агентом-ревьюером; по findings усилены ассершены
  сайд-эффектов редакции, добавлены тесты `init_langfuse`, mid-stream observation,
  граница скана redaction. Тесты заархивированы в `archived-point-tests/` по
  конвенции фазы (живую инфру проектирует feat-009).
- **Ручной smoke прогнан на изолированном стенде** (отдельный PG :5440 + backend :8080,
  чтобы не конфликтовать со стеком параллельного feat-006; LLM-ключ архитектора во
  временном gitignored `.env.local`):
  - **SM-1 (обычный чат) — PASS.** `text_chunk`-стрим → `final_output_review_*` → `done`.
    Подтверждает корректность wiring коллаборáторов в `main.py` и оркестрации `stream()`.
  - **SM-6 (Langfuse off) — PASS.** `trace_id:""`, ошибок трейсинга нет → `AgentRunTracer(enabled=False)` = no-op (DI-флаг работает).
  - **SM-3 (инъекция на входе)** вскрыл **пред-существующий дедлок** (не регрессию): `touch(thread_view)`
    в request-сессии (`chat.py`) держит row-lock на `thread_views` до конца SSE-стрима, а
    `_mark_blocked` открывал отдельную сессию → UPDATE той же строки виснет → взаимоблокировка
    (≈120с). Проверено идентичностью структуры в `HEAD~1`.
    **Фикс (вариант A, реализован отдельным агентом-экспертом):** `_mark_blocked` метит blocked
    через **сессию запроса** (проброшена из `runner.stream` в `check_*`/`inspect_in_graph`), без
    второй транзакции; fallback на `session_factory` сохранён для вызовов вне request-scope.
    После фикса SM-3 — PASS (`security_block` за ~6.6с, `security_blocked=true`, redacted-плейсхолдер),
    SM-1 регрессии нет.

## Гейты
`make check` — ✅ (ruff + ruff format + mypy, 158 files, чисто), включая фикс дедлока.

## Изменённые файлы (код)
`infra/llm.py`, `infra/langfuse.py`, `services/model_config_resolver.py`,
`agent/runner.py`, `agent/tracing.py` (new), `agent/runtime_security.py` (new),
`agent/checkpoint_history.py` (new), `agent/stream_events.py` (new),
`agent/tools/user_memory.py`, `agent/security/observer.py`, `main.py`.
Пост-смоук фикс дедлока: `agent/runtime_security.py` (`_mark_blocked` + `session`-параметр
в `check_*`/`inspect_in_graph`/`_redact_final_output`), `agent/runner.py` (проброс `session`).

## Не делалось / осознанные пропуски
- Дальнейшее дробление `RuntimeSecurityEnforcer` — достаточно текущего.
- `update_section` keyword-only runtime — корректно, не трогалось.
- Каскад `ModelConfigResolver.resolve` юнит-тестами не покрыт (вне скоупа D).
