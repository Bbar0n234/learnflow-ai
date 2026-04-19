# Agent Runtime

Ядро AI-функциональности: LangGraph StateGraph с ReAct-паттерном, context engineering, tools, skills, MCP-интеграция. Инкапсулирован в Agent Layer — наружу выходят только доменные типы (`StreamEvent`, `Message`), не специфичные для LangGraph. Стриминг событий описан в [streaming.md](streaming.md).

## Architecture Overview

```mermaid
graph TD
    SVC["ChatService"]
    RUNNER["AgentRunner (protocol)"]
    FACTORY["GraphFactory"]
    RESOLVER["ModelConfigResolver"]
    PROMPT["PromptProvider"]
    GRAPH["LangGraph StateGraph"]
    TOOLS["Tools"]
    STORE["LangGraph Store (PostgreSQL)"]
    CP["Checkpointer (PostgreSQL)"]

    SVC --> RUNNER
    RUNNER --> FACTORY
    RUNNER --> RESOLVER
    FACTORY --> GRAPH
    FACTORY --> PROMPT
    GRAPH --> TOOLS
    GRAPH --> STORE
    GRAPH --> CP
```

**AgentRunner** — контрактный интерфейс взаимодействия с Service Layer:

| Метод | Назначение |
|-------|------------|
| `stream(thread_id, content, project_id, user_id, session?, model_config?)` | Генерация ответа, поток `StreamEvent` |
| `get_history(thread_id)` | История сообщений (HumanMessage + AIMessage без tool_calls) |
| `get_last_ai_message_id(thread_id)` | ID последнего ответа агента (для привязки артефактов) |
| `cancel(thread_id)` | Отмена генерации через `asyncio.Event` |

Реализация: `LangGraphAgentRunner`. ChatService оркестрирует (thread mapping, artifact linking, trace saving), AgentRunner — генерация.

### Per-Request Flow

```
ChatService
  → ModelConfigResolver.resolve(user_id, project_id, thread_id)
  → GraphFactory.build(model_config, mcp_tools)
  → graph.astream(input, config, context)
```

**GraphFactory** строит и компилирует новый `StateGraph` для каждого запроса с resolved model config и набором tools. Overhead ~1-5ms на компиляцию 2-node графа. Checkpointer и Store — shared, не пересоздаются.

**ModelConfigResolver** — каскадное разрешение модели: thread → project → user → Langfuse prompt config → agent.yaml. Первый non-null уровень побеждает. Whitelist доступных моделей — из `configs/agent.yaml`.

**PromptProvider** — фетчинг системных промптов из Langfuse с file fallback. Подробнее — [prompt-management.md](prompt-management.md).

## Agent Graph

`StateGraph(MessagesState)` — один ключ `messages` с reducer `add_messages`.

```mermaid
graph LR
    START(("START")) --> AGENT["agent node"]
    AGENT --> COND{tool_calls?}
    COND -->|Да| TOOLS["tools (ToolNode)"]
    TOOLS --> AGENT
    COND -->|Нет| END_(("END"))
```

- **agent node** — основной узел: compaction → system message assembly → trimming → LLM call
- **tools** — встроенный `ToolNode`, выполнение tool calls
- **tools_condition** — встроенный router: AIMessage с tool_calls → tools node, иначе → END

**Context schema:** `AgentContext(project_id, user_id, canary_token)` — передаётся через параметр `context=` в `astream()`, доступен в nodes и tools через `runtime.context`. `canary_token` вычисляется для каждого запроса для system prompt hardening (→ [architecture.md](../security/architecture.md)).

**Compilation:** GraphFactory на каждый запрос настраивает:
- `checkpointer=AsyncPostgresSaver` — shared, персистentна история в PostgreSQL
- `store=AsyncPostgresStore` — shared, key-value хранилище для Knowledge Sphere и User Memory

**Invocation:**
```
graph.astream(input_msg, config, stream_mode=["messages", "updates"], context=context)
```
- `stream_mode=["messages"]` — потоковые токены от LLM → `text_chunk` SSE events
- `stream_mode=["updates"]` — результаты узлов → `tool_start`, `tool_end`, `artifact_created` events

## System Message

Собирается из семи частей на каждый вызов agent node. Base prompt обёрнут в hardened Jinja-template с защитными секциями (→ [architecture.md](../security/architecture.md)):

```
┌─────────────────────────────────┐
│ <system_instructions>           │  ← Hardened template
│   Иерархия инструкций,          │     (→ security/architecture.md)
│   confidentiality, canary token │
├─────────────────────────────────┤
│ Base Prompt                     │  ← PromptProvider (→ prompt-management.md)
│ (style, guidelines, boundaries) │
├─────────────────────────────────┤
│ <custom_instructions>           │  ← LangGraph Store, per-user
│                                 │     (→ user-memory.md)
├─────────────────────────────────┤
│ <user_memory>                   │  ← LangGraph Store, per-user
│   (facts about user)            │     (→ user-memory.md)
├─────────────────────────────────┤
│ <knowledge_sphere>               │  ← LangGraph Store, per-project
│   Knowledge Sphere Index        │     (→ knowledge-sphere.md)
├─────────────────────────────────┤
│ <instruction_reminder>          │  ← Hardened template (sandwich defense)
├─────────────────────────────────┤
│ <available_skills>              │  ← Filesystem scan (at startup)
│   Skills Index                  │
└─────────────────────────────────┘
```

| Раздел | Источник | Область | Обновление |
|--------|----------|--------|-----------|
| Security instructions | Hardened template (security/architecture.md) | Global | Canary token per-request |
| Base prompt | PromptProvider (Langfuse → file fallback) | Global | При изменении в Langfuse (SDK cache TTL) |
| Custom instructions | LangGraph Store | Per-user | При сохранении через REST API |
| User memory | LangGraph Store | Per-user | Автономно агентом (tools) |
| Knowledge Sphere Index | LangGraph Store | Per-project | При изменении секций (agent tools / REST API) |
| Instruction reminder | Hardened template (security/architecture.md) | Global | Статический |
| Skills Index | Filesystem scan | Global | При старте приложения |

Пересборка на каждый вызов гарантирует актуальность динамических частей (Knowledge Sphere Index, memories могли измениться между вызовами).

## Context Engineering

Стратегия: **Progressive Disclosure + JIT Loading.**

```mermaid
graph TD
    subgraph "Pre-loaded (always in system message)"
        CI["Custom Instructions"]
        UM["User Memory"]
        KSI["KS Index ~500–1500 tokens"]
        SI["Skills Index"]
    end

    subgraph "JIT (on-demand by agent)"
        KSF["Full KS section"]
        SKL["Full SKILL.md"]
    end

    KSI -.->|"Agent sees index"| KSF
    SI -.->|"Agent sees index"| SKL
```

| Уровень | Содержимое | Когда | Размер |
|---------|-----------|-------|--------|
| Pre-loaded | Custom Instructions, User Memory | Каждый вызов agent node | Variable (user-dependent) |
| Pre-loaded | Knowledge Sphere Index, Skills Index | Каждый вызов agent node | ~500–1500 tokens |
| JIT | Полная секция Knowledge Sphere | `get_section(section_id)` | Variable |
| JIT | Полный SKILL.md | `load_skill(skill_name)` | Variable |
| Managed | Message history | Trimming + compaction | До `max_tokens` budget |

Агент видит индексы в системном промпте и решает, какой контекст подтянуть для текущей задачи. Полные данные загружаются только когда нужны — минимизирует расход контекстного окна.

## Message Compaction

Управление длинными сессиями: суммаризация старых сообщений при превышении порога.

**Trigger:** `total_tokens > max_tokens × compaction_threshold_ratio`

| Параметр | Default | Назначение |
|----------|---------|------------|
| `max_tokens` | 100 000 | Бюджет контекстного окна |
| `compaction_threshold_ratio` | 0.75 | Порог срабатывания (75k tokens) |
| `recent_messages_to_keep` | 10 | Сколько последних сообщений оставить |
| `max_summary_tokens` | 500 | Лимит на summary |

**Два механизма, работающих последовательно:**

```mermaid
flowchart TD
    CHECK["total_tokens > threshold?"] -->|Yes| SPLIT["Split: old / recent last 10"]
    SPLIT --> SUMM["Summarize old (separate model)"]
    SUMM -->|Success| REPLACE["RemoveMessage old + AIMessage summary"]
    SUMM -->|Error| TRIM
    REPLACE --> TRIM
    CHECK -->|No| TRIM
    TRIM["trim_messages strategy=last"]
```

**Compaction** (условный) — умная суммаризация: старые сообщения заменяются summary отдельной моделью. Сохраняет ключевые решения, нерешённые вопросы, текущий фокус; отбрасывает промежуточные tool outputs и reasoning. При ошибке суммаризации — пропускается (graceful degradation).

**Trimming** (обязательный) — safety net после compaction. `trim_messages(strategy="last")` гарантирует, что финальный набор сообщений не превышает `max_tokens`. Если всё влезает — no-op. Нужен потому, что compaction считает только messages, а система сообщения (base prompt + Knowledge Sphere Index + Skills Index) тоже занимает место в контексте.

**Checkpointer хранит полную историю** — оба механизма оптимизируют контекстное окно, не удаляют данные.

## Tools

Четыре категории, объединяются при компиляции графа:

### Internal Tools

**Knowledge Sphere** — CRUD для проектной базы знаний (подробнее — [knowledge-sphere.md](knowledge-sphere.md)):

| Tool | Назначение |
|------|------------|
| `get_section` | Получить полный контент секции |
| `create_section` | Создать новую секцию |
| `update_section` | Обновить секцию (fuzzy patch или overwrite) |
| `delete_section` | Удалить секцию |

**Artifacts:**

| Tool | Назначение |
|------|------------|
| `create_artifact` | Сохранить результат работы агента как артефакт проекта |

`response_format="content_and_artifact"` — tool возвращает текстовый ответ и metadata артефакта (`id`, `title`, `type`). Metadata передаётся через SSE как `artifact_created` event.

**User Memory** — автономное управление фактами о пользователе (подробнее — [user-memory.md](user-memory.md)):

| Tool | Назначение |
|------|------------|
| `save_user_memory` | Сохранить/обновить факт о пользователе |
| `delete_user_memory` | Удалить запись из памяти |

Агент решает самостоятельно, когда сохранять информацию. Память кросс-проектна — доступна во всех чатах пользователя.

**Skills:**

| Tool | Назначение |
|------|------------|
| `load_skill` | Загрузить полный SKILL.md по имени |

### External Tools (MCP)

Загружаются из MCP-серверов через **MCPToolResolver**. Итоговый набор tools для графа:

```
all_tools = internal_tools + mcp_tools(resolved)
```

Подробнее об MCP-архитектуре — раздел [MCP Integration](#mcp-integration).

## Skills System

Skill — модуль специализированных знаний, загружаемый агентом по запросу.

**Формат:** директория с `SKILL.md` (YAML frontmatter `name` + `description`, затем контент). Совместим с Claude Code skill format.

**Lifecycle:**
1. **Discovery** (при старте): `scan_skills_index()` сканирует `skills/`, парсит frontmatter → формирует Skills Index
2. **Index** (в system message): агент видит список `name: description`
3. **Loading** (JIT): агент вызывает `load_skill(skill_name)` → полный контент SKILL.md в контексте

**Безопасность:** валидация имени `^[a-z0-9_-]+$`, проверка `is_relative_to(skills_dir)` — защита от path traversal.

## MCP Integration

Расширение агента внешними инструментами через Model Context Protocol. Двухуровневая архитектура: global + per-user.

### Global MCP Servers

Конфигурируются в `configs/agent.yaml`, секция `mcp_servers`. Доступны всем пользователям.

| Поле | Назначение |
|------|------------|
| `transport` | Тип соединения: `stdio`, `sse`, `streamable_http` |
| `url` | URL для sse/http транспортов |
| `api_key_env` | Имя переменной окружения с API ключом |
| `command` / `args` | Команда запуска для stdio |
| `allowed_tools` | Whitelist инструментов (фильтрация после получения) |
| `enabled` | Включён/выключен без удаления конфигурации |

Client: `MultiServerMCPClient` из `langchain_mcp_adapters`. Создаётся при старте, используется для всех запросов.

### Per-User MCP Servers

Пользователи добавляют собственные MCP-серверы через REST API на трёх уровнях: user → project → thread. Хранятся в БД с шифрованием API-ключей (Fernet).

Ограничения безопасности:
- Только HTTP-транспорты (`streamable_http`, `sse`) — `stdio` запрещён (удалённое выполнение кода)
- Защита от SSRF: DNS resolve + deny list приватных IP-диапазонов
- API-ключи зашифрованы, API возвращает только `has_api_key: bool` + `api_key_hint`

CRUD и каскадная видимость — [backend.md](backend.md).

### MCPToolResolver

Центральный компонент разрешения MCP tools для каждого запроса.

**Additive merge:** thread ∪ project ∪ user ∪ global — tools от всех уровней объединяются.

**Dedup:** при конфликте имён инструментов global выигрывает (security boundary — пользовательский MCP не может подменить системный tool).

**Cache:** TTL-кэш с targeted invalidation по scope tuple `(user_id, project_id, thread_id)`. CRUD-операции над MCP-серверами инвалидируют соответствующий scope (избирательная инвалидация).

**Graceful degradation:** недоступный MCP-сервер → skip + warning в логах, остальные tools работают.

## Security

Pre-graph input guard, system prompt hardening, canary token output check. SecurityGuard — dependency runner'а, проверяет user input до запуска графа. При verdict INJECTION — `security_block` SSE event, запрос не доходит до графа. Подробнее — [architecture.md](../security/architecture.md), обоснование — [ADR-017](adr/ADR-017-prompt-injection-defense.md).

## Observability

Опциональная интеграция с Langfuse (подробнее — [observability.md](observability.md)).

- `CallbackHandler` инжектируется в `config["callbacks"]` графа — автоматическое логирование LLM calls
- Root span `agent-run` с propagation атрибутов: `user_id`, `session_id` (thread_id), `project_id`
- `trace_id` передаётся через SSE для привязки user feedback
- Model definitions с pricing — cost tracking per invocation

Langfuse выполняет две роли: tracing (observability) + prompt management (runtime source of truth для системных промптов). Подробнее — [prompt-management.md](prompt-management.md).

**Graceful degradation:** при недоступности Langfuse — `_NoOpSpan` (no-op tracing), промпты переключаются на file fallback. Приложение работает без трейсинга.

## Graceful Degradation

| Компонент | При отказе | Поведение |
|-----------|-----------|-----------|
| SecurityGuard (LLM) | Guard LLM недоступен | CLEAN verdict, warning в логах, запрос проходит |
| LLM | Исключение в stream | `error` event клиенту, state сохранён в checkpointer |
| PromptProvider (Langfuse) | Langfuse недоступен | File fallback → `configs/prompts/` |
| Global MCP-серверы | Ошибка при инициализации | Приложение стартует без внешних tools |
| Per-user MCP-сервер | Сервер не отвечает | Skip + warning, остальные tools работают |
| Model override | Модель не в whitelist | Validation error → 422 до запуска графа |
| Summarization model | Ошибка суммаризации | Fallback на trim-only |
| Langfuse | Недоступен / не сконфигурирован | No-op span + file fallback для промптов |

Каждый компонент деградирует изолированно, не роняя систему.

## Configuration

Четыре источника конфигурации агента:

| Источник | Что настраивает | Приоритет |
|----------|----------------|-----------|
| `configs/agent.yaml` | LLM defaults, context params, summarization, global MCP, models whitelist | Base defaults |
| `configs/prompts/*.txt` | Seed-файлы промптов | Seed → Langfuse |
| Langfuse | Runtime промпты, model config в prompt metadata | Runtime override |
| DB (settings tables) | Per-scope model overrides, per-user MCP servers | Per-request override |

**`configs/agent.yaml`** — параметры runtime:

| Секция | Что настраивает |
|--------|----------------|
| `llm` | Модель по умолчанию, extra_body (reasoning effort и т.д.) |
| `context` | max_tokens, compaction_threshold_ratio, recent_messages_to_keep |
| `prompt` | Путь к файлу system prompt (seed) |
| `summarization` | Модель суммаризации, max_summary_tokens |
| `security` | Guard model, max retries, temperature (→ [architecture.md](../security/architecture.md)) |
| `mcp_servers` | Global MCP-серверы: transport, URL, API keys, whitelist инструментов |
| `models` | Model definitions: pricing, match patterns (Langfuse cost tracking) |

**Prompt files** — seed-файлы в `configs/prompts/`. Источник истины для промптов — Langfuse; файлы используются для seeding и как fallback. Подробнее — [prompt-management.md](prompt-management.md).

Application-level настройки — `backend/app/config.py` через Pydantic Settings. Ключевые env vars:
- `MCP_ENCRYPTION_KEY` — Fernet-ключ для шифрования API-ключей пользовательских MCP-серверов
- `LANGFUSE_PROMPT_LABEL` — label для получения промптов (по умолчанию: `development`)
- `CANARY_SECRET` — HMAC secret для canary token (пустой = canary отключён + warning)
