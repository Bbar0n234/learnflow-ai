# feat-003: Langfuse — Design Brief

Контекст реализации для implementation plan. Архитектурные решения: [ADR-010](../../../tech/adr/ADR-010-langfuse-observability.md). Референс по системе обратной связи: [reference-feedback-system.md](reference-feedback-system.md).

## Граница трассировки

Langfuse = LLM-логика. Бэкенд-обвязка = structlog (feat-001).

| Что | Куда | Почему |
|-----|------|--------|
| Agent runner (LangGraph stream) | Langfuse: root span | Ядро observability |
| LLM generations | Langfuse: автоматически | CallbackHandler |
| Tool calls (включая MCP) | Langfuse: автоматически | CallbackHandler |
| Message compaction (summarization) | Langfuse: автоматически | Это LLM call внутри agent node |
| FastAPI endpoints | structlog | HTTP-обвязка, не LLM-логика |
| БД операции (CRUD) | structlog | Инфраструктура |
| SSE streaming механика | structlog | Транспорт |
| Аутентификация | structlog | Инфраструктура |

## Паттерн инструментации

### Иерархия трейса

Каждый вызов агента порождает один трейс:

```
Langfuse Session (= chat_id)
│
├── Trace "agent-run"
│   input: "Что такое фотосинтез?"
│   output: "Фотосинтез — это процесс..."
│   user_id, metadata: {project_id}
│   │
│   └── root span (context manager)
│       └── LangGraph internals (CallbackHandler, автоматически)
│           ├── generation "ChatOpenAI" — system prompt + messages → response
│           ├── tool "search_knowledge" — input → result
│           ├── generation "ChatOpenAI" — messages + tool result → response
│           └── ...
│
├── Trace "agent-run"
│   input: "А как это связано с хлорофиллом?"
│   output: "Хлорофилл — ключевой пигмент..."
│   ...
```

Группировка по `session_id` = `chat_id` даёт навигацию как по истории сообщений: каждый трейс = "пользователь спросил X → агент ответил Y".

### Атрибуты root span

| Поле | Значение | Зачем |
|------|----------|-------|
| `name` | `"agent-run"` (статичное) | Фильтрация по trace name. Input виден рядом — динамическое имя не нужно |
| `input` | Чистый текст сообщения пользователя | Читаемый input в списке трейсов |
| `output` | Чистый текст ответа агента | Видно без открытия трейса |
| `user_id` | UUID пользователя из БД | Per-user аналитика |
| `session_id` | `chat_id` (UUID) | Группировка = чат |
| `metadata` | `{"project_id": "..."}` | Фильтрация по learning project |

В metadata — только то, по чему фильтруем. Содержимое сообщений, system prompt, контекст knowledge sphere — уже есть внутри трейса в observations.

### Что CallbackHandler делает автоматически

Без дополнительного кода:
- LLM generations — полный промпт, ответ, model name, token usage, cost
- Tool calls — имя, input, output, время выполнения
- Message compaction — summarization LLM call
- MCP tool calls — как LangGraph tools
- Вложенность — иерархия agent node → LLM → tool → LLM
- TTFT (Time to First Token) — `completion_start_time` при первом токене

### Точки интеграции

- **Root span** — уровень agent runner (streaming). `start_as_current_observation`, input при создании, output после завершения
- **CallbackHandler** — инжектится в config для `astream()`
- **propagate_attributes** — `user_id`, `session_id` (= `chat_id`), `trace_name`
- **Связь с feat-001** — `request_id` из structlog contextvars может быть добавлен в metadata трейса

### Получение trace_id

`span.trace_id` — для передачи на фронтенд через SSE event `done`.

## Streaming и error handling

### Output при streaming

Ответ агента формируется по чанкам. Паттерн: аккумуляция `full_response` + запись в `output` при завершении.

Agent runner уже итерирует чанки для SSE — добавляется одна переменная и один вызов `update()`. Внутренние observations (LLM, tools) обрабатываются автоматически: LangChain аккумулирует полный ответ внутренне и отдаёт CallbackHandler в `on_llm_end`.

### Error handling

Внутренние observations: CallbackHandler автоматически ловит ошибки, ставит `level="ERROR"`, обнуляет cost, завершает observation. LangGraph control flow exceptions не считаются ошибками.

Root span: `try/finally` — при ошибке или обрыве соединения записываем partial output и error status. Трейс не теряется, можно дебажить.

## Feedback Flow

Архитектура: **backend proxy** — фронт шлёт feedback в наш API, бэкенд пишет score в Langfuse. Не direct frontend → Langfuse, потому что:
- Deletion требует `secret_key` (нельзя на клиент)
- Абстракция: бэкенд не зависит от клиента, клиент не зависит от Langfuse

### Цепочка

1. Бэкенд завершает streaming → SSE event `done` содержит `trace_id`
2. Фронтенд сохраняет `trace_id` в state компонента сообщения
3. Thumbs up/down → `POST /api/feedback {trace_id, score}`
4. Бэкенд → Langfuse Score (create/update/delete)

### API контракт

`POST /api/feedback` — `{trace_id: string, score: true | false | null}`

| `score` | Действие | Langfuse |
|---------|----------|----------|
| `true` | Like | `create_score(value=1)` |
| `false` | Dislike | `create_score(value=0)` |
| `null` | Удалить оценку | `api.legacy.score_v1.delete(score_id)` |

### Идемпотентность

Score ID формируется детерминистически: `{trace_id}-user-feedback`. Повторный вызов `create_score` с тем же ID обновляет, а не дублирует. При удалении ID вычисляется на месте.

### Toggle model (UX)

| Текущее | Нажал | Результат | `score` |
|---------|-------|-----------|---------|
| Нет оценки | 👍 | Like | `true` |
| Нет оценки | 👎 | Dislike | `false` |
| Like | 👍 | Оценка удалена | `null` |
| Like | 👎 | Dislike (замена) | `false` |
| Dislike | 👎 | Оценка удалена | `null` |
| Dislike | 👍 | Like (замена) | `true` |

### Score Config

При старте бэкенда — идемпотентное создание Score Config в Langfuse (`name: "user-feedback"`, `data_type: BOOLEAN`). Даёт валидацию типов и корректное отображение в UI.

### Клиентская часть

- `trace_id` хранится в React state компонента сообщения
- Optimistic UI — кнопка обновляется сразу, не ждёт ответ бэкенда
- Silent failure — ошибка feedback логируется, не показывается пользователю (feedback — некритичная операция)

## Token & Cost Tracking

**Автоматически** через CallbackHandler + LangChain OpenAI:
- Token count (input/output) — из `usage` в API response (не из подсчёта чанков, поэтому streaming не влияет на точность)
- Model name — из конфига `ChatOpenAI`
- Cost calculation — Langfuse ищет модель в таблице цен

**Чеклист верификации после интеграции:**
- [ ] На каждой generation в трейсе показываются токены (input/output)
- [ ] Стоимость (cost) рассчитана и отображается
- [ ] Если cost = 0 при наличии токенов — добавить кастомную модель в Settings → Models
- [ ] При streaming — usage корректно аккумулируется

## Конфигурация

Env variables:

| Variable | Назначение | Пример |
|----------|-----------|--------|
| `LANGFUSE_PUBLIC_KEY` | Аутентификация SDK (read) | `pk-lf-...` |
| `LANGFUSE_SECRET_KEY` | Аутентификация SDK (write) | `sk-lf-...` |
| `LANGFUSE_BASE_URL` | Endpoint | `https://cloud.langfuse.com` |
| `LANGFUSE_TRACING_ENVIRONMENT` | Разделение трейсов по средам | `production` / `development` |
| `LANGFUSE_RELEASE` | Версия приложения | git SHA или тег |

Добавляются в `.env.example` и `docker-compose.yml`.

## Scope boundaries (не feat-003)

- LLM-as-a-Judge, automated evaluation
- Prompt Management (промпты остаются в коде)
- Experiments & Datasets
- Custom Dashboards (используем built-in)
- Sampling, Masking
- Annotation Queues
- Security/Guardrails мониторинг (заложен как возможность: `as_type="guardrail"`)
- Async retry с exponential backoff для feedback (рассмотреть при необходимости)
