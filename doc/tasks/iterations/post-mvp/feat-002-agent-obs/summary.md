# Post-Implementation Summary: feat-002 — Agent Observability & Tooling

## Результат

Все три задачи реализованы и верифицированы:

1. **Reasoning tokens -> Langfuse** — reasoning text извлекается из OpenRouter-ответов (invoke + streaming), попадает в `additional_kwargs["reasoning"]`, автоматически отображается в Langfuse generation observation
2. **OpenRouter pricing -> Langfuse** — программная инициализация model definitions с per-category pricing при старте приложения
3. **MCP Firecrawl tool filtering** — allowlist инструментов per MCP-сервер, 13 -> 2 инструмента

## Отклонения от плана

### 1. Миграция на `pricing_tiers` (вместо `input_price`/`output_price`)

**План:** использовать `input_price`/`output_price` в `models.create()`.

**Факт:** эти поля deprecated в Langfuse SDK v4. Кроме того, flat pricing не учитывал token subcategories — `input_cache_read` и `output_reasoning` считались как $0.

**Решение:** `ModelDefinitionConfig.prices: dict[str, float]` вместо отдельных `input_price`/`output_price`/`total_price`. Создание через `PricingTierInput` с default tier. Конфиг содержит 4 категории цен на модель: `input`, `output`, `output_reasoning`, `input_cache_read`.

**Верификация:** ручной расчёт cost по всем 4 категориям совпал с Langfuse до 7 знаков ($0.0054244).

### 2. Try/create вместо check-then-create для model definitions

**План:** `models.list(limit=100)` -> отфильтровать существующие -> создать отсутствующие.

**Факт:** Langfuse содержит 160+ built-in моделей, `limit=100` не покрывает все страницы. Наши custom-модели оказывались на второй странице -> не находились -> повторное создание -> 400 error.

**Решение:** try/create per model. `models.create()` -> если 400 "already exists" -> no-op (debug log). Проще и надёжнее пагинации, один API call на модель.

### 3. Pricing для token subcategories

**Не в исходном плане.** Обнаружено при ручной верификации: Langfuse считал cost только по base `input`/`output` полям, игнорируя `input_cache_read` (кэшированные токены) и `output_reasoning` (reasoning токены). Решено в рамках миграции на `pricing_tiers`.

Приближение по ценам:
- `output_reasoning` = output price (OpenRouter тарифицирует reasoning по output rate)
- `input_cache_read` = input price / 4 (среднее по провайдерам OpenRouter)

## Принятые решения

| Решение | Обоснование |
|---------|-------------|
| `ReasoningChatOpenAI` наследует `ChatOpenAI` с двумя override | Минимальное вмешательство: `super()` делает основную работу, мы добираем `reasoning` из raw response |
| `extra_body` как `dict[str, Any]` в `LLMConfig` | Провайдер-агностичное решение — передаётся как есть в OpenAI client |
| Per-server MCP tool filtering | `get_tools(server_name=)` + allowlist per config — масштабируется на N серверов без конфликтов имён |
| `pricing_tiers` вместо deprecated flat pricing | Единственный способ учесть `input_cache_read` и `output_reasoning` в cost calculation |

## Scope boundaries (соблюдены)

Не реализовывалось (как и заявлено в design brief):
- Стриминг reasoning text на фронтенд
- Кэширование reasoning в БД
- Автоматическая синхронизация pricing с OpenRouter API
- Prompt-based фильтрация MCP-инструментов

## Актуализация документации

Проектная документация (ADR-010, backend.md) написана на уровне архитектуры и контрактов — наши изменения implementation-level, актуализация не требуется. Детали реализации зафиксированы в design-brief и данном summary.
