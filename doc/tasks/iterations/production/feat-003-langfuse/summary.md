# Post-Implementation Summary: feat-003 Langfuse Integration

## Результат

Langfuse observability интегрирован: трейсинг агента (input/output, LLM generations, tool calls, tokens), structured feedback (thumbs up/down) через UI чата, graceful degradation при отсутствии Langfuse. Все критерии приёмки из tasklist выполнены.

## Отклонения от design brief

### Осознанные решения (зафиксированы в implementation plan)

| Design Brief | Реализация | Обоснование |
|---|---|---|
| `api.legacy.score_v1.delete(score_id)` для удаления score | `httpx.delete()` через REST API | SDK v4 не имеет метода delete для scores. Нативный REST endpoint работает |
| CallbackHandler nesting через metadata (`langfuse_trace_id`, `langfuse_parent_observation_id`) | Автоматическое nesting через OTel context | SDK v4 CallbackHandler вкладывается в текущий `start_as_current_observation` context автоматически |
| Config через `langfuse.score_configs.create()` | `langfuse.api.score_configs.create()` | В SDK v4 score configs доступны через `api` property, не напрямую |

### Адаптации при реализации

| Design Brief / Plan | Реализация | Обоснование |
|---|---|---|
| `message_id` получается только при наличии артефактов | Всегда получаем `message_id` из графа | Без `message_id` в done event frontend не мог привязать `trace_id` к сообщению → feedback кнопки не появлялись |
| OTel context detach — не рассмотрен в плане | ExitStack + suppression `opentelemetry.context` logger | CPython by design (PEP 525): async generator finally выполняется в другом `contextvars.Context`. Detach error безвреден, но создаёт ERROR спам |
| `langfuse` зависимость | `langfuse` + `langchain` | CallbackHandler из `langfuse.langchain` требует `langchain` package (не только `langchain_core`) |
| Graceful degradation через try/except на `get_client()` | Module-level `langfuse_enabled` flag | `get_client()` без ключей не бросает exception, а возвращает disabled клиент с warning. Explicit flag надёжнее |

### Дополнения (не в design brief / plan)

| Что | Причина |
|---|---|
| `LOG_FILE` env variable + file handler в logging setup | Необходимость читать логи backend при локальной разработке с агентом. File handler включается только если `LOG_FILE` задан |
| `langfuse_enabled` flag в `app.infra.langfuse` | Explicit проверка вместо exception-based flow. `get_client()` без ключей не бросает, а возвращает disabled client |
| OTel context logger suppression в `init_langfuse()` | Подавление безвредного ERROR от `context.detach()` в async generators. Глобально для `opentelemetry.context` — этот logger генерирует только detach errors |

## Что не вошло в scope

- **Cost tracking** — требует настройки model definition в Langfuse UI (цены per token для конкретной модели). Конфигурация, не код
- **Автотесты** — по conventions, добавляются после MVP
- **Persistence feedback state** — trace_id хранится в React state, теряется при перезагрузке. Trade-off MVP: простота > persistence

## Нюансы

- **OTel + async generators** — фундаментальная несовместимость CPython ContextVar tokens с async generator finalization (PEP 525). OTel issue [#2606](https://github.com/open-telemetry/opentelemetry-python/issues/2606) открыт с 2022, upstream фикса нет. Langfuse SDK v4 фиксит свой CallbackHandler (PR [#1317](https://github.com/langfuse/langfuse-python/pull/1317)), но `start_as_current_observation` использует стандартный OTel `use_span` → detach error остаётся. Решение: suppression через `logging.getLogger("opentelemetry.context").setLevel(CRITICAL)`
- **Score delete через REST** — Langfuse SDK v4 не предоставляет метод удаления score. Используется `httpx.delete()` к REST API `DELETE /api/public/scores/{id}` с basic auth
- **`langchain` как зависимость** — добавлен из-за требования `langfuse.langchain.CallbackHandler`. Проект использует raw LangGraph + `langchain_core`, но callback handler требует полный `langchain`
