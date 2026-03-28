# Implementation Plan: feat-003 Langfuse Integration

## Context

Zero observability для LLM-агента. Нет трейсинга, учёта стоимости/токенов, механизма сбора обратной связи. feat-003 добавляет: Langfuse tracing агента (трейсы, cost, latency) + structured feedback (thumbs up/down). Это фундамент для дальнейшего анализа качества ответов.

**Blocked by:** feat-001 (logging) — done.
**Ветка:** `prod/feat-003-langfuse` (уже создана, worktree активен).

## Референсы

| Документ | Путь |
|----------|------|
| Tasklist | `doc/tasks/tasklist-production.md` (feat-003) |
| ADR-010 | `doc/tech/adr/ADR-010-langfuse-observability.md` |
| Design Brief | `doc/tasks/iterations/production/feat-003-langfuse/design-brief.md` |
| Reference: Feedback | `doc/tasks/iterations/production/feat-003-langfuse/reference-feedback-system.md` |
| Conventions | `doc/tech/conventions.md` |
| Workflow | `doc/workflow.md` |

## Верификация API (быстро меняющиеся инструменты)

Проверено через: Langfuse docs (langfuse.com), langfuse-cli (`npx langfuse-cli api`), search API.

### Langfuse SDK v4 Python — подтверждённый API

```python
# Explicit init с передачей из Settings (singleton — get_client() далее возвращает этот экземпляр)
from langfuse import Langfuse, get_client, propagate_attributes
from langfuse.langchain import CallbackHandler

# Инициализация (один раз в lifespan)
Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    host=settings.langfuse_base_url,
)

# Далее в любом месте приложения
langfuse = get_client()

# LANGFUSE_TRACING_ENVIRONMENT, LANGFUSE_RELEASE — читаются SDK автоматически из env

# Root span
with langfuse.start_as_current_observation(as_type="span", name="agent-run", input=...) as span:
    trace_id = span.trace_id  # или langfuse.get_current_trace_id()
    with propagate_attributes(user_id=..., session_id=..., trace_name=..., metadata=...):
        handler = CallbackHandler()
        # ВАЖНО: CallbackHandler НЕ вкладывается автоматически. Нужны metadata:
        config = {
            "callbacks": [handler],
            "metadata": {
                "langfuse_trace_id": span.trace_id,
                "langfuse_parent_observation_id": span.id,
            },
        }
    span.update(output=...)

# Scores
langfuse.create_score(trace_id=..., name="user-feedback", value=1, data_type="BOOLEAN", score_id="...")
langfuse.api.score.delete(id="<score_id>")

# Score configs
configs = langfuse.score_configs.get(limit=100)  # .data → list
langfuse.score_configs.create(name=..., data_type=..., description=...)

# Lifecycle
langfuse.flush()
langfuse.shutdown()
```

### Расхождения с design brief (согласовано с архитектором)

| Тема | Design brief / Reference | Актуальный API v4 | Решение |
|------|--------------------------|-------------------|---------|
| Score delete | `api.legacy.score_v1.delete(score_id)` | `api.score.delete(id=score_id)` | v4 API (confirmed) |
| CallbackHandler nesting | Подразумевает автоматическое вложение | Не вкладывается автоматически | metadata-подход (confirmed) |
| httpx для delete | Reference: нужен httpx клиент | v4 SDK имеет нативный delete | httpx не нужен |
| Config | auto-read из env | — | Explicit через Settings (confirmed) |

## Согласованные решения

1. **CallbackHandler nesting** → metadata-подход: `langfuse_trace_id` + `langfuse_parent_observation_id` в config
2. **Score delete** → `api.score.delete(id=score_id)` (нативный v4)
3. **Config** → explicit через Settings: `Langfuse()` конструктор в lifespan, `get_client()` далее как singleton
4. **Score Config** → keyword-args: `langfuse.score_configs.create(name=..., data_type="BOOLEAN", ...)`

## Шаги реализации

### Шаг 0: Установка зависимости + inspect-верификация

- `uv add langfuse` в `backend/`
- Verify: `python -c "from langfuse import Langfuse, get_client, propagate_attributes; from langfuse.langchain import CallbackHandler"`
- Inspect ключевых методов: `start_as_current_observation`, `propagate_attributes`, `create_score`, `api.score.delete`
- Подтвердить что `Langfuse()` конструктор регистрирует singleton для `get_client()`
- Скорректировать план по результатам inspect при необходимости

### Шаг 1: Конфигурация

**Файлы:** `backend/app/config.py`, `.env.example`

Добавить в `Settings`:
```python
# Langfuse Observability
langfuse_public_key: str = ""
langfuse_secret_key: str = ""
langfuse_base_url: str = "https://cloud.langfuse.com"
```

Добавить в `.env.example`:
```
# Langfuse Observability
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=production
LANGFUSE_RELEASE=
```

Замечания:
- `LANGFUSE_TRACING_ENVIRONMENT` и `LANGFUSE_RELEASE` НЕ в Settings — SDK читает их из env автоматически, наш код их не потребляет. В Settings только connection params, которые мы явно передаём в `Langfuse()`.
- `docker-compose.yml` — пробрасывает через `env_file: .env` (уже работает, изменений не нужно).

### Шаг 2: Инициализация Langfuse + Score Config auto-init

**Файлы:** `backend/app/infra/langfuse.py` (новый), `backend/app/main.py`

Новый модуль `backend/app/infra/langfuse.py`:
```python
from langfuse import Langfuse, get_client
import structlog

logger = structlog.get_logger()

def init_langfuse(*, public_key: str, secret_key: str, host: str) -> None:
    """Initialize Langfuse singleton and ensure score config exists.

    After this call, get_client() returns the initialized instance.
    """
    if not public_key or not secret_key:
        logger.info("langfuse disabled, keys not configured")
        return

    Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    langfuse = get_client()

    if not langfuse.auth_check():
        logger.warning("langfuse auth check failed, tracing disabled")
        return

    _ensure_score_config(langfuse)
    logger.info("langfuse initialized")

def _ensure_score_config(langfuse) -> None:
    """Idempotently create user-feedback score config."""
    configs = langfuse.score_configs.get(limit=100)
    exists = any(
        c.name == "user-feedback" and c.data_type == "BOOLEAN"
        for c in configs.data
    )
    if not exists:
        langfuse.score_configs.create(
            name="user-feedback",
            data_type="BOOLEAN",
            description="User feedback (1=like, 0=dislike)",
        )
        logger.info("langfuse score config created", name="user-feedback")

def shutdown_langfuse() -> None:
    """Gracefully shut down Langfuse client."""
    try:
        get_client().shutdown()
    except Exception:
        pass
```

В `main.py` lifespan:
- Вызвать `init_langfuse(public_key=settings.langfuse_public_key, ...)` после setup_logging
- Обернуть в try/except (graceful degradation)
- В cleanup: `shutdown_langfuse()`

### Шаг 3: Инструментация agent runner

**Файл:** `backend/app/agent/runner.py`

Точка интеграции: метод `LangGraphAgentRunner.stream()`. Принцип: **Langfuse — fail-safe обёртка, не контейнер.** Существующая error-handling структура (try/except/finally, cancel events, duration logging) сохраняется полностью.

**Fail-safe helper с ExitStack + NoOpSpan:**

```python
from contextlib import contextmanager, ExitStack

class _NoOpSpan:
    """No-op span when Langfuse is unavailable."""
    trace_id = None
    id = None
    def update(self, **kwargs): pass

@contextmanager
def _langfuse_observation(content, user_id, thread_id, project_id):
    """Fail-safe Langfuse instrumentation. Returns (span, handler) or no-ops."""
    span = _NoOpSpan()
    handler = None
    stack = ExitStack()

    try:
        langfuse = get_client()
        actual_span = stack.enter_context(
            langfuse.start_as_current_observation(as_type="span", name="agent-run", input=content)
        )
        stack.enter_context(
            propagate_attributes(
                user_id=str(user_id),
                session_id=str(thread_id),
                trace_name="agent-run",
                metadata={"project_id": str(project_id)},
            )
        )
        span = actual_span
        handler = CallbackHandler()
    except Exception:
        logger.warning("langfuse setup failed, proceeding without tracing", exc_info=True)

    try:
        yield span, handler
    finally:
        try:
            stack.close()
        except Exception:
            logger.warning("langfuse cleanup failed", exc_info=True)
```

**Интеграция в stream() — existing structure preserved:**

```python
async def stream(self, *, thread_id, content, project_id, user_id):
    cancel_event = asyncio.Event()
    self._cancel_events[thread_id] = cancel_event
    # ... existing cancel setup ...

    logger.info("agent invoked", ...)
    stream_start = time.monotonic()
    stream_error = False
    full_response = ""

    with _langfuse_observation(content, user_id, thread_id, project_id) as (span, lf_handler):
        config = {"configurable": {"thread_id": str(thread_id)}}
        if lf_handler:  # Langfuse доступен
            config["callbacks"] = [lf_handler]
            config["metadata"] = {
                "langfuse_trace_id": span.trace_id,
                "langfuse_parent_observation_id": span.id,
            }

        try:                                          # ← existing structure
            async for mode, data in self._graph.astream(
                input_msg, config, stream_mode=["messages", "updates"], context=context,
            ):
                if cancel_event.is_set():             # ← existing
                    yield StreamEvent(type="error", data={"detail": "Cancelled"})
                    return
                if mode == "messages":                # ← existing + аккумуляция
                    msg_chunk, _metadata = data
                    if isinstance(msg_chunk, AIMessageChunk) and isinstance(msg_chunk.content, str) and msg_chunk.content:
                        full_response += msg_chunk.content
                        yield StreamEvent(type="text_chunk", data={"content": msg_chunk.content})
                elif mode == "updates":               # ← existing
                    for event in self._process_updates(data):
                        yield event

        except Exception as e:                        # ← existing
            stream_error = True
            logger.warning("agent stream error", thread_id=str(thread_id), error=str(e))
            yield StreamEvent(type="error", data={"detail": str(e)})
        finally:                                      # ← existing
            duration_ms = int((time.monotonic() - stream_start) * 1000)
            logger.info("agent completed", thread_id=str(thread_id), duration_ms=duration_ms, status="error" if stream_error else "ok")
            self._cancel_events.pop(thread_id, None)
            self._pending_cancels.discard(thread_id)

        span.update(output=full_response)  # no-op если Langfuse failed

    # После выхода из Langfuse CM — emit trace_id для ChatService
    if span.trace_id:
        yield StreamEvent(type="trace_id", data={"trace_id": span.trace_id})
```

**Что обеспечивает этот подход:**
- Langfuse setup fails → `handler=None`, `span=_NoOpSpan()` → стрим работает как раньше
- existing try/except/finally — на месте (cancel, error events, duration, cleanup)
- `span.update()` — no-op при отказе Langfuse
- `ExitStack` — корректно закрывает context managers даже при ошибках

**Передача trace_id наружу:** runner yield-ит `StreamEvent(type="trace_id", data={"trace_id": ...})` после Langfuse CM. ChatService ловит его и включает в done event.

### Шаг 4: trace_id в SSE event `done`

**Файлы:** `backend/app/services/chat.py`

В `ChatService.send_message()`:
```python
trace_id = ""
async for event in self._agent_runner.stream(...):
    if event.type == "trace_id":
        trace_id = event.data.get("trace_id", "")
        continue  # не yield-им — внутренний event
    # ... existing logic ...
    yield event

yield StreamEvent(type="done", data={"message_id": message_id or "", "trace_id": trace_id})
```

SSE wire format (`messages.py`) уже обрабатывает любые data-поля автоматически — изменений не нужно.

### Шаг 5: Feedback endpoint

**Файлы:** `backend/app/api/routes/feedback.py` (новый), `backend/app/api/schemas/feedback.py` (новый), `backend/app/main.py`, `backend/app/api/routes/__init__.py`

Schema (`feedback.py`):
```python
from pydantic import BaseModel

class FeedbackRequest(BaseModel):
    trace_id: str
    score: bool | None  # true=like, false=dislike, null=delete

class FeedbackResponse(BaseModel):
    status: str
```

Router (`feedback.py`):
```python
SCORE_NAME = "user-feedback"

def _score_id(trace_id: str) -> str:
    return f"{trace_id}-user-feedback"

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(body: FeedbackRequest, user: CurrentUser) -> FeedbackResponse:
    langfuse = get_client()

    if body.score is None:
        langfuse.api.score.delete(id=_score_id(body.trace_id))
    else:
        langfuse.create_score(
            trace_id=body.trace_id,
            name=SCORE_NAME,
            value=1 if body.score else 0,
            data_type="BOOLEAN",
            score_id=_score_id(body.trace_id),
        )
    langfuse.flush()
    return FeedbackResponse(status="success")
```

- Зарегистрировать router в `main.py` и `__init__.py`
- Error handling: try/except → 503 если Langfuse недоступен, structlog warning

### Шаг 6: Frontend — trace_id в state сообщения

**Файлы:** `frontend/src/shared/api/types.ts`, `frontend/src/features/chat/hooks/useAgentStream.ts`, `frontend/src/stores/stream-store.ts`, `frontend/src/features/chat/components/ChatView.tsx`

1. `types.ts` — расширить SSEEvent type `done`: `{ type: "done"; message_id?: string; trace_id?: string }`
2. `stream-store.ts` — добавить `lastTraceId: string | null` в state, сбрасывать в `startStream`/`endStream`
3. `useAgentStream.ts` — при `done` event: сохранить `trace_id` в store, передать в `onDone(traceId)`
4. `ChatView.tsx` — хранить Map `messageId → traceId`. При `onDone(traceId)`: привязать к последнему assistant-сообщению. Пробросить в `MessageItem`.

Trade-off (из design brief): trace_id живёт в React state → при перезагрузке страницы теряется. Простота > persistence для MVP.

### Шаг 7: Frontend — Feedback UI

**Файлы:** `frontend/src/features/chat/components/FeedbackButtons.tsx` (новый), `frontend/src/shared/api/feedback.ts` (новый), `frontend/src/features/chat/components/MessageItem.tsx`

API client (`feedback.ts`):
```typescript
import { apiClient } from "./client";

export async function submitFeedback(traceId: string, score: boolean | null) {
  return apiClient.post("/feedback", { trace_id: traceId, score });
}
```

FeedbackButtons component:
- Props: `traceId: string`
- Local state: `currentFeedback: boolean | null`
- Toggle model (из design brief):
  - Нажал то же → null (удаление)
  - Нажал другое → замена
  - Нажал при null → новая оценка
- **Optimistic UI**: state обновляется сразу, API-вызов асинхронно
- **Silent failure**: ошибка → `logger.warn()`, UI не откатываем

MessageItem:
- FeedbackButtons показываем только для assistant-сообщений с traceId
- Расположение: под текстом сообщения, мелкие иконки inline

### Шаг 8: Верификация

Чеклист из design brief + tasklist:
- [ ] Каждый вызов агента → трейс в Langfuse с читаемым input/output
- [ ] В трейсе видны: LLM generations, tool calls, token usage, стоимость
- [ ] Трейсы сгруппированы по session_id (чаты) и user_id
- [ ] Thumbs up/down в UI чата → score привязан к трейсу в Langfuse
- [ ] Toggle: повторное нажатие удаляет оценку, смена — заменяет
- [ ] Environment (dev/production) корректно разделяет трейсы
- [ ] При недоступности Langfuse приложение работает без ошибок
- [ ] Token/cost tracking: на каждой generation видны tokens и cost
- [ ] `make check` + `make lint-fe` проходят

### Шаг 9: Документация и завершение

- Post-implementation summary (`doc/tasks/iterations/production/feat-003-langfuse/summary.md`)
- Обновление статуса в `tasklist-production.md`
- Актуализация связанной документации (по необходимости)

### Шаг 10: Ревью архитектора

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.

## Файлы для изменения

### Новые файлы
| Файл | Назначение |
|------|-----------|
| `backend/app/infra/langfuse.py` | Инициализация клиента, Score Config |
| `backend/app/api/routes/feedback.py` | Feedback endpoint |
| `backend/app/api/schemas/feedback.py` | Pydantic schemas |
| `frontend/src/features/chat/components/FeedbackButtons.tsx` | UI кнопок feedback |
| `frontend/src/shared/api/feedback.ts` | API client для feedback |

### Изменяемые файлы
| Файл | Изменение |
|------|-----------|
| `backend/pyproject.toml` | + langfuse dependency |
| `backend/app/config.py` | + langfuse_public_key, langfuse_secret_key, langfuse_base_url |
| `backend/app/main.py` | init_langfuse() в lifespan, shutdown, feedback router |
| `backend/app/agent/runner.py` | Root span + CallbackHandler + propagate_attributes + trace_id event |
| `backend/app/services/chat.py` | trace_id interception + включение в done event |
| `backend/app/api/routes/__init__.py` | + feedback import |
| `frontend/src/shared/api/types.ts` | trace_id в SSEEvent done |
| `frontend/src/features/chat/hooks/useAgentStream.ts` | Обработка trace_id из done |
| `frontend/src/stores/stream-store.ts` | lastTraceId в state |
| `frontend/src/features/chat/components/ChatView.tsx` | trace_id state management + пробрасывание в MessageItem |
| `frontend/src/features/chat/components/MessageItem.tsx` | + FeedbackButtons |
| `.env.example` | + LANGFUSE_* переменные |
