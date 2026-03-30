# Post-Implementation Summary: fix-001 — Feedback Persistence

## Результат

Feedback buttons (like/dislike) сохраняют состояние при перезагрузке страницы, смене вкладки, очистке localStorage и между сессиями браузера. Graceful degradation при недоступности Redis.

## Отклонения от плана

### 1. Feedback score — Redis вместо localStorage (расширение scope)

**План:** feedback UI state хранится в localStorage (`feedback:{traceId}` = `"true"/"false"`).

**Факт:** при тестировании (Group 4, кейс 4.1) архитектор принял решение хранить feedback scores в Redis. Причина: очистка localStorage или смена браузера приводит к потере реакций, что неприемлемо даже для MVP.

**Реализация (Variant A):**
- `SET feedback:{trace_id} "1"/"0"` с TTL 30 дней — простые ключи по trace_id
- Feedback route (POST /api/feedback) пишет в Redis рядом с Langfuse-вызовом
- GET /chats/{id} читает feedback scores через `MGET` и возвращает `feedback_score: bool | null` в `MessageOut`
- Frontend: `FeedbackButtons` принимает `initialScore` из API response, localStorage полностью убран

**Почему Variant A, а не B/C:**
- Ноль breaking changes в feedback API (route уже получает trace_id)
- MGET на N trace_ids — микросекунды для типичного чата (< 50 сообщений)
- Разделение ответственностей: trace mapping и feedback scores — независимые ключи

### 2. Redis URL убран из логов

**План:** `logger.info("redis connected", url=settings.redis_url)`.

**Факт:** по замечанию архитектора убран `url=` параметр из лога — превентивная мера против утечки credentials, если Redis URL когда-либо будет содержать пароль.

### 3. TraceStore — HASH вместо SCAN

Предусмотрено в плане как уточнение к design brief. `HSET/HGETALL trace:{thread_id}` вместо отдельных ключей с SCAN. Реализовано как запланировано.

## Новые файлы

| Файл | Назначение |
|------|-----------|
| `backend/app/infra/redis.py` | Фабрика async Redis client с graceful degradation |
| `backend/app/repositories/trace_store.py` | Redis HASH для trace mapping + simple keys для feedback scores |

## Изменённые файлы

### Backend
- `backend/pyproject.toml`, `uv.lock` — зависимость `redis[hiredis]`
- `backend/app/config.py` — поле `redis_url`
- `backend/app/main.py` — Redis в lifespan (init + shutdown)
- `backend/app/repositories/__init__.py` — экспорт TraceStore
- `backend/app/api/deps.py` — TraceStore создаётся в get_chat_service
- `backend/app/services/chat.py` — ChatDetail.trace_ids/feedback_scores, save в send_message, read в get_chat
- `backend/app/api/schemas/chats.py` — MessageOut: trace_id, feedback_score
- `backend/app/api/routes/chats.py` — проброс trace_id и feedback_score в MessageOut
- `backend/app/api/routes/feedback.py` — Redis-запись feedback score

### Frontend
- `frontend/src/shared/api/types.ts` — Message: trace_id, feedback_score
- `frontend/src/features/chat/components/FeedbackButtons.tsx` — initialScore из API, localStorage убран
- `frontend/src/features/chat/components/ChatView.tsx` — убран traceIds useState
- `frontend/src/features/chat/components/MessageList.tsx` — убран проп traceIds
- `frontend/src/features/chat/components/MessageItem.tsx` — message.trace_id + message.feedback_score

### Infrastructure
- `docker-compose.yml` — Redis сервис + depends_on в app
- `.env.example`, `.env.local.example` — REDIS_URL, REDIS_PORT
- `Makefile` — target docker-up-redis

## Тестирование

Ручное тестирование по 4 группам:

| Группа | Кейсы | Результат |
|--------|-------|-----------|
| Backend API (curl) | trace_id в response, Redis HASH, restart persistence, старые чаты | PASS |
| Frontend E2E (browser) | Кнопки появляются, persist при reload, toggle, chat switch | PASS |
| Graceful Degradation | Redis down → app works, restore → feedback works | PASS |
| Edge Cases | localStorage clear → feedback сохранён (Redis), multiple msgs, toggle | PASS |

## Нерешённое

- **Баг #2 (P1):** Артефакт-карточки пропадают из истории чата — требует отдельной проработки, вне scope текущей итерации
