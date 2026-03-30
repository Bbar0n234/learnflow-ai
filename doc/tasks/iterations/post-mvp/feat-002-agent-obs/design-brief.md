# Design Brief: feat-002 — Agent Observability & Tooling

## Scope

Три задачи из backlog:

1. **[P1] Reasoning tokens → Langfuse** — reasoning token count + reasoning text в Langfuse
2. **[P2] OpenRouter pricing → Langfuse** — программная инициализация моделей с pricing
3. **[P2] MCP Firecrawl tool filtering** — allowlist инструментов по MCP-серверам

## Задача 1: Reasoning tokens → Langfuse

### Проблема

Стандартный `ChatOpenAI` из `langchain-openai` не парсит поле `reasoning` из ответов OpenRouter. Это нестандартное поле, которое возвращают провайдеры для reasoning-моделей. Без перехвата reasoning text теряется — невозможно отлаживать и улучшать поведение модели.

### Экспериментальные данные

#### Формат ответа OpenRouter (единый для всех протестированных моделей)

**Non-streaming** (`choices[].message`):

```json
{
  "message": {
    "role": "assistant",
    "content": "925",
    "reasoning": "Текст рассуждений модели..."
  }
}
```

**Streaming** (`choices[].delta`):

```json
{
  "delta": {
    "role": "assistant",
    "content": "",
    "reasoning": "Часть рассуждений...",
    "reasoning_details": [
      {"type": "reasoning.text", "text": "...", "format": "google-gemini-v1"},
      {"type": "reasoning.encrypted", "data": "base64..."}
    ]
  }
}
```

Порядок chunks: сначала reasoning (content пустой), потом content (reasoning отсутствует).

#### Reasoning token count

Доступен в стандартном `ChatOpenAI` без каких-либо модификаций:

- `usage_metadata["output_token_details"]["reasoning"]` — int
- `response_metadata["token_usage"]["completion_tokens_details"]["reasoning_tokens"]` — int

Работает и в invoke(), и в astream(). Дополнительных действий не требуется.

#### Reasoning text

Стандартный `ChatOpenAI` теряет reasoning text — поле просто не парсится.

В docstring `langchain-openai` прямо сказано:
> Non-standard response fields added by third-party providers (e.g., `reasoning_content`, `reasoning_details`) are **not** extracted or preserved.

#### Протестированные модели

| Модель | Reasoning token count | Reasoning text (invoke) | Reasoning text (stream) | Cost от OpenRouter |
|--------|----------------------|------------------------|------------------------|-------------------|
| google/gemini-3.1-pro-preview | да | да (wrapper) | да (wrapper) | $0.002–0.018 |
| z-ai/glm-5 | да | да (wrapper) | да (wrapper) | $0.002 |
| z-ai/glm-4.7-flash | да | да (wrapper) | да (wrapper) | $0.0003–0.0006 |

Формат единый для всех трёх моделей. Model-specific хаки не нужны.

#### Активация reasoning через extra_body

```yaml
# agent.yaml
llm:
  model: "google/gemini-3.1-pro-preview"
  extra_body:
    include_reasoning: true
    reasoning:
      effort: low  # low | medium | high
```

- `include_reasoning: true` — флаг для фабрики, чтобы выбрать ReasoningChatOpenAI
- `reasoning.enabled` / `reasoning.effort` — передаётся провайдеру в теле запроса

Без `include_reasoning: true` reasoning token count всё равно приходит, но reasoning text — нет.

### Решение: ReasoningChatOpenAI

Наследник `ChatOpenAI` с двумя override:

**Non-streaming** — `_create_chat_result()`:
- `super()` парсит content, tool_calls → создаёт `AIMessage`
- Override берёт raw response, находит `choices[].message.reasoning`
- Дописывает в `AIMessage.additional_kwargs["reasoning"]`

**Streaming** — `_convert_chunk_to_generation_chunk()`:
- `super()` создаёт `AIMessageChunk` с content
- Override берёт raw chunk dict, находит `delta.reasoning`
- Дописывает в `AIMessageChunk.additional_kwargs["reasoning"]`

Агрегация при стриминге: `AIMessageChunk.__add__` конкатенирует строковые значения в `additional_kwargs`, поэтому reasoning из нескольких chunks склеивается автоматически.

### Проверенная реализация ReasoningChatOpenAI

Код ниже — полная рабочая компонента, проверенная экспериментально на трёх моделях в обоих режимах (invoke + astream):

```python
from typing import Any

import openai
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI


class ReasoningChatOpenAI(ChatOpenAI):
    """ChatOpenAI with reasoning extraction for OpenRouter-compatible providers.

    Extracts `reasoning` from non-standard response fields into
    AIMessage.additional_kwargs["reasoning"] for both invoke and streaming.
    """

    # --- Non-streaming path ---
    def _create_chat_result(
        self,
        response: dict[str, Any] | openai.BaseModel,
        generation_info: dict[str, Any] | None = None,
    ) -> ChatResult:
        result = super()._create_chat_result(response, generation_info)
        response_dict = (
            response
            if isinstance(response, dict)
            else response.model_dump(exclude_none=True)
        )
        choices = response_dict.get("choices") or []
        for gen, choice in zip(result.generations, choices, strict=False):
            if not isinstance(gen.message, AIMessage):
                continue
            msg_payload = choice.get("message") or {}
            reasoning = msg_payload.get("reasoning")
            if reasoning is not None:
                gen.message.additional_kwargs["reasoning"] = reasoning
        return result

    # --- Streaming path ---
    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict,
        default_chunk_class: type,
        base_generation_info: dict | None,
    ) -> ChatGenerationChunk | None:
        gen_chunk = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if gen_chunk is None:
            return None

        choices = chunk.get("choices") or []
        if choices:
            delta = choices[0].get("delta") or {}
            reasoning = delta.get("reasoning")
            if reasoning and isinstance(gen_chunk.message, AIMessageChunk):
                gen_chunk.message.additional_kwargs["reasoning"] = reasoning

        return gen_chunk
```

Фабрика выбирает класс по наличию `include_reasoning` в `extra_body`:

```python
def create_llm(settings: Settings, agent_config: AgentConfig) -> BaseChatModel:
    extra_body = agent_config.llm.extra_body
    use_reasoning = extra_body.get("include_reasoning", False) if extra_body else False
    llm_class = ReasoningChatOpenAI if use_reasoning else ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": agent_config.llm.model,
        "api_key": settings.llm_api_key,
        "base_url": settings.llm_base_url,
    }
    if extra_body:
        kwargs["extra_body"] = extra_body

    return llm_class(**kwargs)  # type: ignore[call-arg]
```

### Интеграция с Langfuse

`CallbackHandler` v4 автоматически видит `additional_kwargs` на `AIMessage`/`AIMessageChunk` и пишет их в generation observation. Reasoning text попадёт в Langfuse без дополнительных действий.

**Требует верификации на этапе реализации:** убедиться, что CallbackHandler действительно пробрасывает `additional_kwargs["reasoning"]` в observation metadata.

### Точки изменения

| Файл | Изменение |
|------|-----------|
| `backend/app/infra/llm.py` | Добавить класс `ReasoningChatOpenAI`, обновить `create_llm()` |
| `backend/app/agent/config.py` | Расширить `LLMConfig` полем `extra_body: dict[str, Any] = {}` |
| `configs/agent.yaml` | Добавить `extra_body` секцию в `llm` |

### Ограничения и риски

1. **`delta.reasoning`** — нестандартное поле OpenRouter. При смене формата сломается. Неизбежно при работе с нестандартными API.
2. **`_convert_chunk_to_generation_chunk`** — internal API LangChain. Стабилен, но может измениться при major-обновлении `langchain-openai`. Минимизируем риск через `super()` + `**kwargs`.
3. **`reasoning_details`** содержит как `reasoning.text`, так и `reasoning.encrypted` блоки. Сейчас берём только `delta.reasoning` (plaintext). Encrypted блоки игнорируем — они не несут пользы для отладки.

---

## Задача 2: OpenRouter pricing → Langfuse

### Проблема

Langfuse считает cost по своей внутренней таблице моделей. OpenRouter-модели (z-ai/glm-5, и т.д.) могут отсутствовать в таблице → cost = 0. Сейчас pricing настроен вручную через UI — нужно Infrastructure as Code.

### Экспериментальные данные

#### Langfuse Models API

**Endpoint:** `POST /api/public/models` (через SDK: `langfuse.api.models.create(...)`)

**Обязательные поля:**

| Поле | Тип | Описание |
|------|-----|----------|
| `model_name` | str | Имя модели. При дубликатах: (1) custom > built-in, (2) newer startTime wins |
| `match_pattern` | str | Regex для матчинга с `generation.model`. Для exact match: `(?i)^modelname$` |

**Pricing поля:**

| Поле | Тип | Описание |
|------|-----|----------|
| `input_price` | float | USD за input unit (deprecated, но работает — создаёт default tier) |
| `output_price` | float | USD за output unit (deprecated, но работает — создаёт default tier) |
| `total_price` | float | USD за total units (нельзя с input/output) |
| `unit` | str | `TOKENS`, `CHARACTERS`, и т.д. |

Новый API поддерживает `pricing_tiers` для tier-based pricing (Anthropic, Gemini large context), но для наших целей `input_price`/`output_price` достаточно.

#### Идемпотентность

**НЕ идемпотентно.** Повторный `create` с тем же `model_name` возвращает `400 InvalidRequestError`:
```
Model name '__test_exp_pricing__' already exists in project
```

Стратегия: **check-then-create** — проверить `models.list()`, создать только отсутствующие.
Обновление: API не предоставляет `update` — только `delete` + `create` заново.

#### Существующие модели в Langfuse

Все три модели проекта (`z-ai/glm-5`, `z-ai/glm-4.7-flash`, `google/gemini-3.1-pro-preview`) **отсутствуют** в списке моделей (0 custom models). Это значит pricing сейчас рассчитывается через built-in таблицу Langfuse (которая может не содержать OpenRouter-специфичные модели).

#### Альтернатива: cost ingestion напрямую из OpenRouter

OpenRouter возвращает точный cost в каждом ответе:

```json
{
  "token_usage": {
    "cost": 0.017442,
    "cost_details": {
      "upstream_inference_cost": 0.017442,
      "upstream_inference_prompt_cost": 3e-05,
      "upstream_inference_completions_cost": 0.017412
    }
  }
}
```

**Два подхода:**

| | Model definitions (per-token pricing) | Cost ingestion (from OpenRouter) |
|---|---|---|
| Точность | Приблизительная (фиксированная цена за токен) | Точная (включает reasoning tokens, tier pricing) |
| Актуальность | Требует обновления при смене pricing | Всегда актуальная |
| Сложность | Простая (конфиг + init при старте) | Требует изменения CallbackHandler или post-processing |
| Зависимость | Нет runtime-зависимости | Зависим от формата OpenRouter response |

**Рекомендация:** model definitions как baseline (простое решение, инфраструктура как код). Cost ingestion — отдельная итерация, если точность станет критичной.

### Решение: программная инициализация model definitions

Аналогично `_ensure_score_config` в `infra/langfuse.py`.

#### Конфигурация: отдельная секция `models` в agent.yaml

Pricing — забота Langfuse observability, а не LLM-вызовов. Поэтому отдельная секция, не inline в `llm`:

```yaml
llm:
  model: "google/gemini-3.1-pro-preview"
  extra_body:
    include_reasoning: true

# Langfuse model definitions for cost tracking
models:
  - name: "google/gemini-3.1-pro-preview"
    match_pattern: "(?i)^google/gemini-3\\.1-pro-preview"
    unit: TOKENS
    input_price: 0.000002
    output_price: 0.000012

  - name: "z-ai/glm-5"
    match_pattern: "(?i)^z-ai/glm-5"
    unit: TOKENS
    input_price: 0.000001
    output_price: 0.0000032

  - name: "z-ai/glm-4.7-flash"
    match_pattern: "(?i)^z-ai/glm-4\\.7-flash"
    unit: TOKENS
    input_price: 0.000000125
    output_price: 0.0000005
```

#### Match pattern: prefix-match (без `$`)

OpenRouter возвращает версионные имена моделей с датой:

- Конфиг: `z-ai/glm-5` → response: `z-ai/glm-5-20260211`
- Конфиг: `google/gemini-3.1-pro-preview` → response: `google/gemini-3.1-pro-preview-20260219`

Langfuse `CallbackHandler` пишет в generation версионное имя из response. Поэтому `match_pattern` должен быть **prefix-match** (без `$` на конце), чтобы матчить и базовое имя, и версионное.

#### Инициализация при старте

1. `models.list()` — получить все существующие модели (один API call)
2. Отфильтровать: какие из конфига уже существуют
3. `models.create()` — создать только отсутствующие

#### Стратегия обновления pricing

**Only create missing.** Если модель уже существует — не трогаем. Для обновления pricing (смена цен у провайдера) — ручной delete через Langfuse UI или отдельный скрипт, затем приложение при следующем старте создаст заново с новыми ценами из конфига. Автоматическое обновление — out of scope.

### Точки изменения

| Файл | Изменение |
|------|-----------|
| `backend/app/infra/langfuse.py` | Добавить `_ensure_model_definitions(langfuse, models)` |
| `configs/agent.yaml` (или отдельный файл) | Секция с моделями и их pricing |
| `backend/app/agent/config.py` | Модель конфигурации для pricing (если в agent.yaml) |

### Ограничения

1. **Нет upsert** — при изменении цены нужно удалить старую модель и создать заново. Для init при старте это приемлемо.
2. **Pricing фиксирован** — не обновляется автоматически при смене цен у провайдера. Нужно вручную обновлять конфиг.
3. **Reasoning tokens** — если reasoning tokens стоят иначе чем output tokens, per-token pricing будет неточным. Для точного учёта нужен cost ingestion (out of scope).

---

## Задача 3: MCP Firecrawl tool filtering

### Проблема

`MultiServerMCPClient.get_tools()` возвращает все инструменты Firecrawl MCP-сервера (13+). Агенту реально нужны 2-3. Лишние инструменты — шум в контексте LLM.

### Экспериментальные данные

#### Полный список инструментов Firecrawl MCP (13 шт.)

| # | Имя | Назначение |
|---|-----|-----------|
| 1 | `firecrawl_scrape` | Скрейпинг одной URL |
| 2 | `firecrawl_map` | Карта URL сайта |
| 3 | `firecrawl_search` | Веб-поиск + извлечение контента |
| 4 | `firecrawl_crawl` | Краулинг нескольких страниц |
| 5 | `firecrawl_check_crawl_status` | Статус краулинга |
| 6 | `firecrawl_extract` | Structured extraction через LLM |
| 7 | `firecrawl_agent` | Автономный research agent |
| 8 | `firecrawl_agent_status` | Статус agent job |
| 9 | `firecrawl_browser_create` | **DEPRECATED** — создание browser session |
| 10 | `firecrawl_browser_delete` | **DEPRECATED** — удаление browser session |
| 11 | `firecrawl_browser_list` | **DEPRECATED** — список browser sessions |
| 12 | `firecrawl_interact` | Взаимодействие со scraped страницей |
| 13 | `firecrawl_interact_stop` | Остановка interact сессии |

#### Фильтрация

Проверено: фильтрация по имени (`[t for t in tools if t.name in allowlist]`) работает. 13 → 2 инструмента.

Рекомендуемый allowlist: `firecrawl_scrape`, `firecrawl_search` — покрывает основные потребности агента (получить контент URL, найти информацию в вебе).

### Решение

Allowlist на уровне конфига MCP-сервера:

```yaml
mcp_servers:
  firecrawl:
    transport: http
    url: https://mcp.firecrawl.dev/v2/mcp
    api_key_env: FIRECRAWL_API_KEY
    allowed_tools:
      - firecrawl_scrape
      - firecrawl_search
```

Если `allowed_tools` пуст или не указан — все инструменты проходят (обратная совместимость).

#### Per-server фильтрация

`MultiServerMCPClient.get_tools()` поддерживает `server_name` параметр — можно получить tools одного конкретного сервера. Это позволяет фильтровать per-server вместо глобального списка:

```python
all_mcp_tools = []
for server_name, server_config in agent_config.mcp_servers.items():
    tools = await mcp_client.get_tools(server_name=server_name)
    if server_config.allowed_tools:
        allowed = set(server_config.allowed_tools)
        tools = [t for t in tools if t.name in allowed]
    all_mcp_tools.extend(tools)
```

Каждый сервер фильтруется по своему `allowed_tools`. При добавлении второго MCP-сервера — всё работает автоматически, без конфликтов имён.

### Точки изменения

| Файл | Изменение |
|------|-----------|
| `backend/app/agent/config.py` | Добавить `allowed_tools: list[str] = []` в `MCPServerConfig` |
| `backend/app/main.py` | Фильтрация `mcp_tools` по имени после `get_tools()` |
| `configs/agent.yaml` | Добавить `allowed_tools` для firecrawl |

---

## Scope boundaries

Явно **НЕ входит** в scope feat-002:

- Стриминг reasoning text на фронтенд (отдельная фича, требует изменения SSE протокола)
- Кэширование reasoning в БД (сейчас только в Langfuse)
- Автоматическая синхронизация pricing с OpenRouter API в runtime
- Фильтрация MCP-инструментов на уровне LLM (prompt-based) — только config-based allowlist
