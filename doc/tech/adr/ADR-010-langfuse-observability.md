# ADR-010: Langfuse Observability Strategy

## Статус

Принято

## Контекст

Текущее состояние: zero observability. Нет трейсинга вызовов агента, нет учёта стоимости и токенов, нет механизма сбора обратной связи от пользователей. При проблемах с агентом — только логи uvicorn и structlog (feat-001), без видимости того, что происходит внутри LangGraph.

Потребность: видимость работы агента (трейсы, стоимость, латенси), structured feedback от пользователей (thumbs up/down). Агент — LangGraph StateGraph, streaming через `astream()`, FastAPI + SSE.

## Решения

### Langfuse как observability-платформа

Специализированная платформа для LLM-приложений. Трейсы, generations, tool calls — first-class entities с нативным отображением, а не generic spans.

Аргументы за выбор:
- Специализация на LLM-агентах: трейсинг, cost tracking, feedback scoring — всё из коробки под один use case
- Опыт разработчика с инструментом (production-использование в других проектах)
- Активное развитие: за последний год — v4 с observation-centric моделью, OTel-фундамент, MCP-сервер, agent graph visualization, LLM-as-a-Judge evaluators
- Нативная интеграция с LangChain/LangGraph через CallbackHandler — автоматический перехват нод, LLM-вызовов, tool calls

Формальное сравнение с альтернативами (LangSmith, Arize, custom) не проводилось — выбор основан на практическом опыте и соответствии стеку.

### Cloud-first deployment

Langfuse Cloud (EU region) вместо self-hosted.

- Нет требований к on-premise размещению данных
- Hobby tier (50k observations/мес) покрывает текущие объёмы
- Автообновления — всегда актуальная версия без миграций инфраструктуры. Self-hosted с v3 требует ClickHouse + MinIO + Redis — существенное усложнение
- Self-hosted потребовал бы 4+ дополнительных контейнера и минимум 16GB RAM на VM, где уже развёрнуто приложение
- Миграция на self-hosted возможна в любой момент: SDK не меняется, меняется только `LANGFUSE_BASE_URL`

### SDK v4 (Python)

Актуальная версия SDK, нет причин начинать на v3.

- Observation-centric data model — запросы быстрее, нет JOIN trace↔observation
- `propagate_attributes()` вместо deprecated `update_current_trace()` — атрибуты (`user_id`, `session_id`, `tags`) пробрасываются на каждое наблюдение
- OTel-фундамент — стандартный context propagation через OpenTelemetry, совместимость с экосистемой (на практике абстрагируемся от OTel, работаем через Langfuse SDK)

### Инструментация: context manager + CallbackHandler

Два механизма в связке:

- **`start_as_current_observation()`** (context manager) — корневой span с ручным контролем input/output/metadata. Необходим для streaming-сценария, где результат формируется по чанкам и нужно обновлять span по ходу выполнения
- **`CallbackHandler`** — передаётся в `astream()` config, автоматически перехватывает все LangGraph ноды, LLM generations, tool calls

`@observe()` декоратор не используем — недостаточно гибкий: не позволяет обновлять span по ходу выполнения, input/output фиксируются только на границах функции.

## Следствия

- `langfuse` — новая Python-зависимость (SDK v4)
- Набор env variables: `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL`, `LANGFUSE_RELEASE`, `LANGFUSE_TRACING_ENVIRONMENT`
- `trace_id` нужно пробрасывать на фронтенд для feedback scoring
- Зависимость от внешнего сервиса (Langfuse Cloud) — при недоступности SDK буферизует данные асинхронно, приложение не блокируется
- Фундамент для будущих возможностей: LLM-as-a-Judge, Prompt Management, Experiments — подключаются без изменения инструментации
