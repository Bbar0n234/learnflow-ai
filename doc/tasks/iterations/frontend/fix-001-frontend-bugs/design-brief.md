# Design Brief: Feedback Persistence (fix-001, bug #1)

## Context

Feedback иконки (like/dislike) пропадают при перезагрузке страницы. Причина — три уровня данных живут только в памяти текущей сессии:

1. **trace_id** (маппинг message → Langfuse trace) — хранится в `ChatView` useState, теряется при reload
2. **feedback score** (текущее состояние кнопки) — хранится в `FeedbackButtons` useState, теряется при reload
3. **Backend не возвращает trace_id** при загрузке истории чата (`MessageOut` не содержит поля)

Паттерн решения адаптирован из проекта Telegram-бота, где аналогичная задача решена через Redis.

## Решение: Redis для trace_id + Redis для feedback score

> **Update (post-implementation):** исходный план предполагал localStorage для feedback state. По результатам тестирования решение изменено на Redis — подробности в [summary.md](summary.md).

### Redis (аналог бот-проекта)

В бот-проекте Redis хранит маппинг `msg:{chat_id}:{msg_id} → trace_id` с TTL 7 дней. Адаптация для web-приложения:

```
┌──────────────────────────────┬───────────┬────────┐
│             Ключ             │ Значение  │  TTL   │
├──────────────────────────────┼───────────┼────────┤
│ trace:{thread_id}:{msg_id}   │ trace_id  │ 30 дн  │
└──────────────────────────────┴───────────┴────────┘
```

**Отличия от бот-проекта:**
- Один ключ вместо двух — reaction state хранится на клиенте (localStorage), не в Redis
- TTL 30 дней вместо 7 — web-приложение имеет более длинный жизненный цикл сессий
- Нет retry/rollback логики — web-клиент проще бота, оптимистичный UI достаточен

**Почему Redis, а не PostgreSQL:**
- Легковесное key-value хранилище, не смешиваем с данными приложения
- PostgreSQL используется для LangGraph checkpointer и бизнес-данных — разные зоны ответственности
- Подобных обращений (feedback, в будущем другие метрики) будет много — Redis оптимален для этого класса задач

### localStorage (frontend)

Feedback score (like/dislike/neutral) хранится в localStorage:

```
Ключ: feedback:{traceId}
Значение: "true" | "false" | удалён
```

**Почему не Redis для score:**
- Feedback уже хранится в Langfuse (source of truth)
- Дублировать в Redis = два источника правды
- localStorage решает задачу "показать состояние кнопки" для single-user MVP
- При необходимости cross-device sync — можно добавить GET из Langfuse API позже

## Точки интеграции

### 1. Инфраструктура: Redis в Docker

**docker-compose.yml** — новый сервис:

```yaml
redis:
  image: redis:7-alpine
  restart: unless-stopped
  ports:
    - "${REDIS_PORT:-6379}:6379"
  volumes:
    - redisdata:/data
  healthcheck:
    test: ["CMD", "redis-cli", "ping"]
    interval: 5s
    timeout: 5s
    retries: 5
```

Volume `redisdata` для persistence (AOF/RDB по дефолту Redis).

**Makefile** — добавить `docker-up-redis` target (аналогично `docker-up-db`).

### 2. Backend: Settings + Redis client

**config.py** — новое поле:

```python
redis_url: str = "redis://localhost:6379/0"
```

**Инфра-модуль** `app/infra/redis.py`:

```
create_redis(settings) → redis.asyncio.Redis
```

Используется `redis.asyncio` (aioredis merged в redis-py 5+). Клиент создаётся в lifespan, хранится в `app.state.redis`.

**Graceful degradation:** Redis недоступен → feedback кнопки не рендерятся (trace_id = None), но приложение работает. Аналогично Langfuse — опциональный сервис.

### 3. Backend: TraceStore (repository layer)

**Файл:** `app/repositories/trace_store.py`

```
TraceStore
├── save(thread_id, message_id, trace_id) → None     # SET trace:{thread_id}:{msg_id} {trace_id} EX ttl
├── get_by_thread(thread_id) → dict[str, str]         # SCAN trace:{thread_id}:* → {msg_id: trace_id}
└── TTL = 30 дней
```

**Паттерн DI:** Аналогично остальным сервисам — фабрика в deps.py, `Annotated[TraceStore, Depends(get_trace_store)]`.

Клиент Redis берётся из `request.app.state.redis`.

### 4. Backend: ChatService — post-hoc сохранение trace_id

**Файл:** `app/services/chat.py` — метод `send_message()`

После существующего post-hoc блока (артефакты, строки 110-126) добавить:

```python
# Post-hoc: save trace_id → Redis
if trace_id and message_id:
    await trace_store.save(thread_id, message_id, trace_id)
```

**Зависимость:** `ChatService` получает `TraceStore` через конструктор (DI в deps.py).

### 5. Backend: get_chat endpoint — trace_id в MessageOut

**Файл:** `app/api/schemas/chats.py`

```python
class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime | None = None
    artifacts: list[ArtifactListItem] = []
    trace_id: str | None = None          # NEW
```

**Файл:** `app/api/routes/chats.py` — endpoint `get_chat()`

```python
# После получения artifacts_by_msg:
traces = await trace_store.get_by_thread(chat_id)

return ChatDetailResponse(
    ...,
    messages=[
        MessageOut(
            ...,
            trace_id=traces.get(m.id),    # NEW
        )
        for m in chat_detail.messages
    ],
)
```

**Зависимость:** endpoint получает `TraceStore` через DI (новый `TraceStoreDep`).

### 6. Frontend: types.ts

```typescript
interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string | null;
  artifacts: Artifact[];
  trace_id: string | null;              // NEW
}
```

### 7. Frontend: ChatView.tsx — убрать traceIds state

Текущий код хранит `traceIds` в useState и передаёт вниз. После фикса:

- Убрать `const [traceIds, setTraceIds] = useState<Record<string, string>>({})`
- Убрать `traceIds` из `handleDone` (trace_id больше не нужен на клиенте — он в API)
- Убрать проп `traceIds` из `MessageList`
- `MessageItem` берёт `trace_id` из `message.trace_id`

**Нюанс:** Для текущей сессии (до query invalidation) trace_id ещё не в API response. Два варианта:
- **(A)** Оставить `traceIds` useState как fallback для текущей сессии, merge с API data
- **(B)** Не показывать feedback buttons до завершения стрима и рефетча

Рекомендация: **(B)** — проще, FeedbackButtons появляются после рефетча (< 1 сек задержка), нет дополнительного состояния.

### 8. Frontend: FeedbackButtons.tsx — localStorage persistence

```typescript
function FeedbackButtons({ traceId }: { traceId: string }) {
  const storageKey = `feedback:${traceId}`;

  const [feedback, setFeedback] = useState<boolean | null>(() => {
    const stored = localStorage.getItem(storageKey);
    if (stored === "true") return true;
    if (stored === "false") return false;
    return null;
  });

  function handleClick(value: boolean) {
    const next = feedback === value ? null : value;
    setFeedback(next);
    if (next === null) {
      localStorage.removeItem(storageKey);
    } else {
      localStorage.setItem(storageKey, String(next));
    }
    submitFeedback(traceId, next).catch(...);
  }
}
```

### 9. Frontend: MessageItem.tsx — упрощение

```typescript
// Было:
{!isUser && traceId && <FeedbackButtons traceId={traceId} />}

// Стало:
{!isUser && message.trace_id && <FeedbackButtons traceId={message.trace_id} />}
```

Проп `traceId` убирается — данные из `message.trace_id` (API response).

## Зависимости (пакеты)

**Backend:**
- `redis[hiredis]` — async Redis client (redis-py 5+ включает aioredis)

**Frontend:**
- Нет новых зависимостей

## Граничные случаи

| Ситуация | Поведение |
|---|---|
| Redis недоступен при старте | Приложение запускается, `app.state.redis = None`, trace_id не сохраняется |
| Redis недоступен при запросе | `trace_id = None` в MessageOut, FeedbackButtons не рендерятся |
| Stream обрывается до done | trace_id не генерируется (Langfuse span не закрыт) → кнопки не рендерятся |
| localStorage очищен | Кнопки видны, состояние сохранено (feedback score из Redis) |
| Другой браузер/устройство | Кнопки видны, состояние сохранено (feedback score из Redis) |

## Scope Boundaries

**В scope:**
- Redis сервис в docker-compose
- Backend: redis client, TraceStore, интеграция в ChatService и get_chat
- Frontend: localStorage для feedback, убрать traceIds state
- Env example: REDIS_URL
- Makefile: docker-up-redis target

**Вне scope:**
- Cross-device sync feedback state (можно добавить позже через Langfuse API GET)
- Retry/rollback логика (достаточна для web, не нужна сложность бота)
- Redis для других данных (будущие итерации)
- Баг #2 (artifact cards) — отдельная проработка
