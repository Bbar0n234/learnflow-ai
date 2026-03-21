# Система обратной связи (User Feedback) — технический референс

> Snapshot из проекта itone-agent-consultant. Контекст: Langfuse SDK v3, Python бэкенд + React/Telegram фронтенды. Применимые паттерны адаптированы в [design-brief.md](design-brief.md). Ключевое отличие нашего проекта: SDK v4 имеет `api.legacy.score_v1.delete()` — голый httpx вызов для удаления не нужен.

Референс по реализации системы пользовательской обратной связи (like/dislike) для LLM-приложения. Оценки сохраняются в Langfuse и используются для анализа качества ответов.

## Содержание

- [Архитектура](#архитектура)
- [API контракт](#api-контракт)
- [Langfuse: хранение оценок](#langfuse-хранение-оценок)
- [Идемпотентность и Score ID](#идемпотентность-и-score-id)
- [Модель toggle: удаление оценки повторным нажатием](#модель-toggle-удаление-оценки-повторным-нажатием)
- [Удаление оценки на уровне Langfuse](#удаление-оценки-на-уровне-langfuse)
- [Score Config: автоматическая инициализация](#score-config-автоматическая-инициализация)
- [Привязка оценки к trace](#привязка-оценки-к-trace)
- [Клиентская интеграция](#клиентская-интеграция)
- [Async delivery с retry и rollback](#async-delivery-с-retry-и-rollback)
- [Связь с evaluation и аналитикой](#связь-с-evaluation-и-аналитикой)

---

## Архитектура

Ключевое решение — **Backend API полностью абстрагирован от клиентов**. Один эндпоинт работает только с `trace_id` и `score`. Клиент (фронтенд, бот, что угодно) сам решает, как хранить маппинг "элемент UI → trace_id".

```
┌─────────────────────────────────────────────────────────────┐
│                       Backend API                            │
│              POST /feedback {trace_id, score}                 │
└───────────────────────────┬─────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                        Langfuse                              │
│                   user-feedback scores                        │
└─────────────────────────────────────────────────────────────┘
                            ▲
            ┌───────────────┼───────────────┐
            │               │               │
      ┌───────────┐  ┌───────────┐  ┌───────────┐
      │  Frontend  │  │  Telegram │  │  Другие   │
      │  (state)   │  │  (Redis)  │  │  клиенты  │
      └───────────┘  └───────────┘  └───────────┘
```

Почему так: слабая связность, масштабируемость (новый канал = новый клиент, бэкенд не трогаем), каждый клиент использует оптимальный для себя способ хранения маппинга.

---

## API контракт

### POST /feedback

**Request:**

```json
{
  "trace_id": "string",
  "score": true | false | null
}
```

**Response:**

```json
{
  "status": "success"
}
```

### Семантика значений `score`

| Значение | Действие | Langfuse score |
|----------|----------|----------------|
| `true`   | Like     | `value: 1`     |
| `false`  | Dislike  | `value: 0`     |
| `null`   | **Удаление оценки** | Score удаляется из Langfuse |

### HTTP статусы

| Код | Описание |
|-----|----------|
| 200 | Успешно |
| 400 | Trace не найден в Langfuse |
| 503 | Langfuse недоступен |
| 500 | Внутренняя ошибка |

---

## Langfuse: хранение оценок

Оценки хранятся как **Langfuse Scores** — встроенная сущность платформы, привязанная к trace.

- **Score name**: `"user-feedback"`
- **Data type**: `BOOLEAN`
- **Значения**: `1` (like), `0` (dislike)

Для **создания и обновления** используется Langfuse SDK:

```python
langfuse_client.create_score(
    trace_id=trace_id,
    name="user-feedback",
    value=1 if score else 0,
    data_type="BOOLEAN",
    score_id=f"{trace_id}-user-feedback",  # идемпотентный ID
)
langfuse_client.flush()
```

Для **удаления** — прямой HTTP-вызов, потому что Langfuse SDK **не предоставляет метод удаления score**:

```python
async def _delete_score(self, score_id: str) -> None:
    response = await self._http_client.delete(
        f"{self.langfuse_host}/api/public/scores/{score_id}",
        auth=(self.langfuse_public_key, self.langfuse_secret_key),
    )
    # 202 — queued, 204 — deleted, 404 — already gone
```

> Это критический момент: SDK умеет create/update, но не delete. Для удаления нужен отдельный HTTP-клиент (httpx) с Basic Auth.

---

## Идемпотентность и Score ID

Score ID формируется детерминистически:

```
score_id = f"{trace_id}-user-feedback"
```

Это даёт:

1. **Идемпотентность** — повторный вызов `create_score` с тем же `score_id` обновляет существующий score, а не создаёт дубликат. Безопасно для retry-логики.
2. **Предсказуемость** — при удалении не нужно запрашивать ID из Langfuse, он вычисляется на месте.
3. **Один score на trace** — `score_id` привязан к `trace_id`, что гарантирует ровно одну оценку на ответ.

---

## Модель toggle: удаление оценки повторным нажатием

Пользователь видит две кнопки: `[👍]` и `[👎]`. Логика toggle:

| Текущее состояние | Действие пользователя | Результат | `score` в API |
|---|---|---|---|
| Нет оценки | Нажал 👍 | Like | `true` |
| Нет оценки | Нажал 👎 | Dislike | `false` |
| Like | Нажал 👍 (тот же) | **Оценка удалена** | `null` |
| Like | Нажал 👎 (другой) | Dislike (замена) | `false` |
| Dislike | Нажал 👎 (тот же) | **Оценка удалена** | `null` |
| Dislike | Нажал 👍 (другой) | Like (замена) | `true` |

Визуальные состояния кнопок:

```
Нет оценки:    [👍]   [👎]       — обе neutral
Like:          [✓ 👍]  [👎]      — like highlighted
Dislike:       [👍]   [✓ 👎]     — dislike highlighted
```

### Логика определения действия на клиенте

Критический сниппет — определение, что делать при нажатии:

```python
prev_score = get_current_reaction()  # None | 0 | 1
new_click = clicked_score            # 0 | 1

if prev_score == new_click:
    # Toggle off: повторное нажатие → удалить оценку
    api_score = None
    new_state = None
elif prev_score is None:
    # Новая оценка
    api_score = bool(new_click)
    new_state = new_click
else:
    # Смена оценки (like → dislike или наоборот)
    api_score = bool(new_click)
    new_state = new_click
```

> Клиент хранит `prev_score` (текущее состояние реакции) и сравнивает с нажатой кнопкой. Совпадение = toggle off = `null`. Несовпадение = set/replace.

---

## Удаление оценки на уровне Langfuse

При `score: null` бэкенд выполняет **полное удаление** score из Langfuse, а не обнуление:

```
DELETE /api/public/scores/{score_id}
Authorization: Basic base64(public_key:secret_key)
```

Возможные ответы:
- `202 Accepted` — удаление поставлено в очередь
- `204 No Content` — удалено
- `404 Not Found` — уже удалён (идемпотентно, не ошибка)

Почему удаление, а не `value: null`:
- Чистота данных — trace без оценки ≠ trace с пустой оценкой
- Корректная фильтрация в Langfuse UI — "traces без feedback" работает правильно
- Не засоряет аналитику нулевыми значениями

---

## Score Config: автоматическая инициализация

При старте бэкенда автоматически создаётся **Score Config** в Langfuse — описание типа оценки:

```python
async def ensure_score_config_exists(langfuse_client) -> None:
    """Идемпотентно создаёт конфигурацию score при старте."""
    configs = langfuse_client.api.score_configs.get(limit=100)

    exists = any(
        c.name == "user-feedback" and c.data_type == "BOOLEAN"
        for c in configs.data
    )

    if not exists:
        langfuse_client.api.score_configs.create(
            request=CreateScoreConfigRequest(
                name="user-feedback",
                data_type=ScoreDataType.BOOLEAN,
                description="User feedback (1=like, 0=dislike)",
            )
        )
```

Это даёт:
- Валидацию типов при записи score
- Корректное отображение в Langfuse UI (чекбокс, а не числовое поле)
- Self-documenting: новый разработчик видит конфигурацию в интерфейсе Langfuse

---

## Привязка оценки к trace

Оценка привязывается к **trace целиком**, не к отдельным spans/observations внутри него.

Цепочка:
1. При обработке запроса `AgentProcessor` создаёт trace в Langfuse
2. Извлекает `trace_id` из generation object
3. Возвращает `trace_id` клиенту в ответе:

```python
# Backend: ответ на запрос чата
class ChatResponse(BaseModel):
    answer: str
    trace_id: str  # клиент сохраняет для последующей отправки feedback
```

4. Клиент сохраняет `trace_id` и использует его при отправке feedback

> `trace_id` — единственный "мост" между ответом и оценкой. Если клиент потеряет `trace_id`, отправить feedback будет невозможно.

---

## Клиентская интеграция

### Frontend (React)

Фронтенд хранит `trace_id` в state компонента сообщения — никакого промежуточного хранилища не нужно:

```
Backend response: {answer, trace_id}
       │
       ▼
ChatMessage Component
  props.traceId = "abc-123"
       │
       ▼
FeedbackButtons Component
  traceId, currentFeedback (null | true | false)
  onClick → POST /feedback {trace_id, score}
```

Ключевые решения:
- **Optimistic UI** — кнопка обновляется сразу при нажатии, не дожидаясь ответа бэкенда
- `trace_id` живёт в state → при перезагрузке страницы состояние теряется (trade-off: простота vs persistence)

### Telegram Bot

Telegram не позволяет хранить произвольные данные в сообщении, поэтому используется Redis для маппинга:

```
msg:{chat_id}:{message_id}      → trace_id    (TTL 7 дней)
reaction:{chat_id}:{message_id} → 0 | 1       (TTL 7 дней)
```

Inline keyboard callback data: `fb:{score}:{message_id}` (например `fb:1:12345`).

TTL-expiration: если пользователь нажмёт кнопку после 7 дней — keyboard удаляется, показывается сообщение "Время для оценки истекло".

---

## Async delivery с retry и rollback

Feedback отправляется в **background task**, чтобы не блокировать UI. При неудаче — retry с exponential backoff:

| Попытка | Задержка | Накопительно |
|---------|----------|--------------|
| 1       | 0s       | 0s           |
| 2       | 2s       | 2s           |
| 3       | 4s       | 6s           |
| 4       | 8s       | 14s          |
| 5       | 16s      | 30s          |

Если все 5 попыток провалились — **rollback**:

1. Восстановить UI кнопок в предыдущее состояние
2. Восстановить состояние реакции в хранилище (Redis / state)
3. Без уведомления пользователю об ошибке (silent failure + логирование)

Обоснование silent failure: feedback — некритичная операция. Показать ошибку пользователю за то, что он нажал лайк — хуже, чем молча потерять оценку.

---

## Связь с evaluation и аналитикой

Оценки пользователей используются для:

1. **Фильтрация в Langfuse UI** — быстрый доступ к trace с dislike для анализа проблемных ответов
2. **Курация датасетов** — trace с dislike → кандидаты для добавления в evaluation-датасет
3. **Метрики качества** — доля положительных оценок как high-level индикатор
4. **Приоритизация улучшений** — паттерны в dislike-ответах указывают на системные проблемы (промпт, retrieval, модель)

> Feedback — это **входной сигнал** для evaluation pipeline, а не замена автоматическим метрикам. Автоматические оценки (Ragas и пр.) запускаются на каждый trace независимо от наличия feedback.
