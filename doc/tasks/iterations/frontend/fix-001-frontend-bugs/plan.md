# Implementation Plan: fix-001 — Feedback Persistence

## Context

Feedback-иконки (like/dislike) пропадают при перезагрузке страницы. Три причины: (1) trace_id живёт в useState и теряется при reload, (2) feedback score живёт в useState, (3) backend не возвращает trace_id при загрузке истории. Решение: Redis для маппинга message -> trace_id, localStorage для состояния кнопок.

**Scope итерации fix-001**: 4 бага, из которых 2 (P2) уже пофикшены (uncommitted), 1 (P1 artifact cards) на паузе. Этот план — на оставшийся P1 баг: feedback persistence.

## Референсы

| Документ | Назначение |
|----------|-----------|
| [design-brief.md](doc/tasks/iterations/frontend/fix-001-frontend-bugs/design-brief.md) | Архитектура решения, 9 точек интеграции |
| [tasklist-post-mvp.md](doc/tasks/tasklist-post-mvp.md) | Исходный таск-лист |
| [conventions.md](doc/tech/conventions.md) | Git flow, именование, logging |
| [workflow.md](doc/workflow.md) | Жизненный цикл итерации |

## Быстро меняющиеся инструменты

| Инструмент | Актуален для | Верификация |
|-----------|-------------|-------------|
| redis-py (async) | Новая зависимость — TraceStore | `uv add` + `inspect` модуля `redis.asyncio` (Step 0) |
| pydantic-settings | Добавление `redis_url` в Settings | Существующий паттерн в `config.py`, нового API нет |
| TanStack Query v5 | `invalidateQueries` при done event | Существующий паттерн в `useAgentStream.ts`, нового API нет |
| Docker Compose | Новый Redis-сервис | Существующий паттерн (аналог `db` service) |

**redis-py** — единственный новый инструмент. Верификация на шаге 0: install + inspect `redis.asyncio.Redis` (методы `set`, `get`, `scan`, `close`, `from_url`).

## Решения из design brief

- **Вариант (B)** для trace_id текущей сессии: feedback buttons появляются после refetch (done event -> invalidateQueries -> refetch -> message.trace_id из API), без fallback useState. Проще, задержка < 1 сек.
- **TraceStore** в `repositories/` — следуем design brief, несмотря на то что Redis-backed (не SQLAlchemy). Это repository-layer по ответственности.
- **Graceful degradation**: Redis недоступен -> `app.state.redis = None`, приложение работает без feedback persistence.

## Уточнения к design brief (по итогам ревью)

- **HASH вместо SCAN**: design brief описывает SCAN `trace:{thread_id}:*` для чтения. Используем Redis HASH — `HSET trace:{thread_id} {message_id} {trace_id}` / `HGETALL trace:{thread_id}`. O(1) запись, O(n messages in thread) чтение, TTL через `EXPIRE` на весь hash. Строго лучше SCAN (O(N) по всем ключам Redis).
- **TraceStore инжектится только в ChatService** (Variant A): сервис отвечает за запись (send_message) и чтение (get_chat). Роут не знает про TraceStore — получает trace_ids через `ChatDetail`.

## План реализации

### Step 0: Установка зависимости + верификация API

1. `uv add --package learnflow-backend "redis[hiredis]"`
2. Верификация через Python inspect:
   ```python
   import redis.asyncio
   # Проверить: Redis.from_url(), set(name, value, ex=), get(name), scan(cursor, match=), aclose()
   ```
3. Добавить `types-redis` в dev dependency-group (если нужно для mypy)

**Файлы:** `backend/pyproject.toml`, `uv.lock`

### Step 1: Инфраструктура — Redis в Docker + конфигурация

**docker-compose.yml** — новый сервис `redis` (аналог `db`):
- `image: redis:7-alpine`, порт `${REDIS_PORT:-6379}:6379`
- Volume `redisdata:/data`, healthcheck `redis-cli ping`
- `app.depends_on` — добавить `redis: condition: service_healthy`

**backend/app/config.py** — новое поле:
- `redis_url: str = "redis://localhost:6379/0"`

**.env.example** — добавить:
- `REDIS_URL=redis://redis:6379/0` (Docker service name)
- `REDIS_PORT=6379`

**.env.local.example** — добавить:
- `REDIS_URL=redis://localhost:6379/0`

**Makefile** — новый target:
- `docker-up-redis`: `docker compose up -d redis` (аналог `docker-up-db`)

**Файлы:** `docker-compose.yml`, `backend/app/config.py`, `.env.example`, `.env.local.example`, `Makefile`

### Step 2: Backend — Redis client (infra layer)

**backend/app/infra/redis.py** — фабрика:
```python
async def create_redis(settings: Settings) -> redis.asyncio.Redis | None
```
- Подключение через `Redis.from_url(settings.redis_url)`
- `PING` для проверки связи
- При ошибке: логирование warning, возврат `None` (graceful degradation, аналог Langfuse)

**backend/app/main.py** — lifespan:
- После DB init: `app.state.redis = await create_redis(settings)`
- При shutdown: `if app.state.redis: await app.state.redis.aclose()`

**Файлы:** `backend/app/infra/redis.py` (новый), `backend/app/main.py`

### Step 3: Backend — TraceStore (repository layer)

**backend/app/repositories/trace_store.py** — новый модуль:
```python
class TraceStore:
    TTL = 30 * 24 * 3600  # 30 дней

    def __init__(self, redis: redis.asyncio.Redis) -> None: ...

    async def save(self, thread_id: UUID, message_id: str, trace_id: str) -> None:
        # HSET trace:{thread_id} {message_id} {trace_id}
        # EXPIRE trace:{thread_id} self.TTL (обновляет TTL при каждой записи)

    async def get_by_thread(self, thread_id: UUID) -> dict[str, str]:
        # HGETALL trace:{thread_id} -> {message_id: trace_id}
```

**backend/app/repositories/__init__.py** — добавить экспорт `TraceStore`.

**Файлы:** `backend/app/repositories/trace_store.py` (новый), `backend/app/repositories/__init__.py`

### Step 4: Backend — Schema update + ChatDetail extension

**backend/app/api/schemas/chats.py** — `MessageOut`:
- Добавить `trace_id: str | None = None`

**backend/app/services/chat.py** — `ChatDetail`:
- Добавить поле `trace_ids: dict[str, str] = field(default_factory=dict)`

**Файлы:** `backend/app/api/schemas/chats.py`, `backend/app/services/chat.py`

### Step 5: Backend — DI + ChatService integration

**backend/app/api/deps.py**:
- Новая фабрика `get_trace_store(request) -> TraceStore | None` — берёт `request.app.state.redis`, если `None` -> возвращает `None`
- Обновить `get_chat_service` — добавить `trace_store` параметр
- TraceStoreDep в роуте **не нужен** — TraceStore инжектится только в ChatService

**backend/app/services/chat.py** — `ChatService`:
- Конструктор: добавить `trace_store: TraceStore | None = None`
- `send_message()`: после post-hoc блока (строки 110-126), перед yield done:
  ```python
  if self._trace_store and trace_id and message_id:
      await self._trace_store.save(thread_id, message_id, trace_id)
  ```
- `get_chat()`: заполнить `trace_ids` из TraceStore (если доступен):
  ```python
  trace_ids = {}
  if self._trace_store:
      trace_ids = await self._trace_store.get_by_thread(thread_id)
  return ChatDetail(thread_view=thread_view, messages=messages, trace_ids=trace_ids)
  ```

**backend/app/api/routes/chats.py** — `get_chat()`:
- Использовать `chat_detail.trace_ids.get(m.id)` для заполнения `trace_id` в `MessageOut`
- **Никаких новых зависимостей в роуте** — данные приходят от сервиса

**Файлы:** `backend/app/api/deps.py`, `backend/app/services/chat.py`, `backend/app/api/routes/chats.py`

### Step 6: Frontend — Types + FeedbackButtons localStorage

**frontend/src/shared/api/types.ts** — `Message`:
- Добавить `trace_id?: string | null` (optional — API возвращает `null`, но локально сконструированные Message в `handleSend` поля не содержат)

**frontend/src/features/chat/components/FeedbackButtons.tsx**:
- Инициализация `feedback` из localStorage: `localStorage.getItem(\`feedback:${traceId}\`)`
- При клике: сохранение/удаление в localStorage
- Код из design brief (секция 8)

**Файлы:** `frontend/src/shared/api/types.ts`, `frontend/src/features/chat/components/FeedbackButtons.tsx`

### Step 7: Frontend — Убрать traceIds state, упростить компоненты

**frontend/src/features/chat/components/ChatView.tsx**:
- Убрать `const [traceIds, setTraceIds] = useState<Record<string, string>>({})`
- Упростить `handleDone`: убрать setTraceIds, оставить только `setLocalMessages([])`
- Убрать проп `traceIds` из `<MessageList>`

**frontend/src/features/chat/components/MessageList.tsx**:
- Убрать `traceIds` из props interface и деструктуризации
- Убрать `traceId={traceIds?.[msg.id]}` из `<MessageItem>`

**frontend/src/features/chat/components/MessageItem.tsx**:
- Убрать проп `traceId` из interface
- Заменить `traceId` на `message.trace_id` в рендере FeedbackButtons

**Файлы:** `ChatView.tsx`, `MessageList.tsx`, `MessageItem.tsx`

### Step 8: Проверки качества

1. `make check` — backend (ruff + mypy)
2. `make check-fe` — frontend (tsc + eslint + prettier)
3. Исправить все найденные ошибки

### Step 9: End-to-end верификация

1. `make docker-up-redis` + `make docker-up-db` — поднять инфраструктуру
2. `make dev` + `make dev-fe` — запустить backend и frontend
3. Проверить сценарии:
   - Отправить сообщение в чат -> дождаться ответа -> feedback buttons появляются
   - Нажать like/dislike -> reload страницы -> состояние кнопок сохранилось
   - Открыть другой чат -> вернуться -> feedback state на месте
   - Остановить Redis -> приложение работает, кнопки не отображаются (graceful degradation)

### Step 10: Ревью архитектора

Дождаться ревью и обратной связи от архитектора. Коммит и пуш — только после апрува.

## Порядок коммитов (предложение)

Два коммита на ветке `pmvp/fix-001-frontend-bugs`:
1. P2 фиксы (уже сделаны, uncommitted): `fix(frontend): add cursor-pointer to buttons and fix refetch during streaming`
2. P1 feedback persistence: `fix: add feedback persistence with Redis trace mapping and localStorage`

Финальное решение по коммитам — за архитектором.

## Граничные случаи (из design brief)

| Ситуация | Поведение |
|----------|----------|
| Redis недоступен при старте | app.state.redis = None, trace_id не сохраняется |
| Redis недоступен при запросе | trace_id = None в MessageOut, buttons не рендерятся |
| Stream обрывается до done | trace_id не генерируется, кнопки не рендерятся |
| localStorage очищен | Кнопки видны (trace_id из API), состояние = neutral |
| Другой браузер | Кнопки видны, состояние = neutral |
