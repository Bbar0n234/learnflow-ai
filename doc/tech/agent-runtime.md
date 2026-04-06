# Agent Runtime

Ядро AI-функциональности: LangGraph-граф с ReAct-паттерном, context engineering, tools, skills, MCP-интеграция. Инкапсулирован в Agent Layer — наружу выходят только доменные типы (`StreamEvent`, `Message`), не LangGraph-специфичные. Стриминг событий — [streaming.md](streaming.md).

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

**AgentRunner** — protocol-интерфейс взаимодействия с Service Layer:

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

`StateGraph(MessagesState)` — single key `messages`, reducer `add_messages`.

```mermaid
graph LR
    START(("START")) --> AGENT["agent"]
    AGENT --> COND{tool_calls?}
    COND -->|Да| TOOLS["tools (ToolNode)"]
    TOOLS --> AGENT
    COND -->|Нет| END_(("END"))
```

- **agent** — основной узел: compaction → system message → trimming → LLM invocation
- **tools** — `ToolNode` (prebuilt), выполнение tool calls
- **tools_condition** (prebuilt) — routing: AIMessage с tool_calls → tools, иначе → END

**Context schema:** `AgentContext(project_id, user_id)` — передаётся через `context=` параметр `astream()`, доступен в nodes и tools через `runtime.context`.

**Compile:** GraphFactory на каждый запрос:
- `checkpointer=AsyncPostgresSaver` — shared, персистентная история (PostgreSQL)
- `store=AsyncPostgresStore` — shared, key-value для Knowledge Sphere и User Memory

**Invocation:**
```
graph.astream(input_msg, config, stream_mode=["messages", "updates"], context=context)
```
- `stream_mode=["messages"]` — потоковые токены от LLM → `text_chunk` events
- `stream_mode=["updates"]` — результаты узлов → `tool_start`, `tool_end`, `artifact_created` events

## System Message

Собирается из пяти частей на каждый вызов agent node:

```
┌─────────────────────────────────┐
│ Base Prompt                     │  ← PromptProvider (→ prompt-management.md)
│ (стиль, guidelines, boundaries) │
├─────────────────────────────────┤
│ <custom_instructions>           │  ← LangGraph Store, per-user
│   Пользовательские инструкции   │     (→ user-memory.md)
├─────────────────────────────────┤
│ <user_memory>                   │  ← LangGraph Store, per-user
│   Факты о пользователе          │     (→ user-memory.md)
├─────────────────────────────────┤
│ <knowledge_sphere>              │  ← LangGraph Store, per-project
│   KS Index                      │     (→ knowledge-sphere.md)
├─────────────────────────────────┤
│ <available_skills>              │  ← skills/ directory (scanned at startup)
│   Skills Index                  │
└─────────────────────────────────┘
```

| Часть | Source | Scope | Обновление |
|-------|--------|-------|------------|
| Base prompt | PromptProvider (Langfuse → file fallback) | Global | При изменении в Langfuse (SDK cache TTL) |
| Custom instructions | LangGraph Store | Per-user | При сохранении через REST API |
| User memory | LangGraph Store | Per-user | Автономно агентом (tools) |
| KS Index | LangGraph Store | Per-project | При изменении секций (agent tools / REST API) |
| Skills Index | Filesystem scan | Global | При старте приложения |

Пересборка на каждый вызов гарантирует актуальность динамических частей (KS Index, memories могли измениться между вызовами).

## Context Engineering

Стратегия: **Progressive Disclosure + JIT Loading.**

```mermaid
graph TD
    subgraph "Всегда в system message"
        CI["Custom Instructions"]
        UM["User Memory"]
        KSI["KS Index (~500-1500 tokens)"]
        SI["Skills Index"]
    end

    subgraph "JIT — по запросу агента"
        KSF["Полная секция KS (get_section)"]
        SKL["Полный SKILL.md (load_skill)"]
    end

    KSI -.->|"Агент видит список и решает"| KSF
    SI -.->|"Агент видит список и решает"| SKL
```

| Уровень | Что | Когда | Размер |
|---------|-----|-------|--------|
| Pre-loaded | Custom Instructions, User Memory | Каждый вызов agent node | Variable (user-dependent) |
| Pre-loaded | KS Index, Skills Index | Каждый вызов agent node | ~500-1500 tokens |
| JIT | Полная секция KS | `get_section(section_id)` | Variable |
| JIT | Полный SKILL.md | `load_skill(skill_name)` | Variable |
| Managed | Message history | Trimming + compaction | До `max_tokens` budget |

Агент видит индексы в system message и решает, какой контекст подтянуть для текущей задачи. Полные данные загружаются только когда нужны — минимизирует расход контекстного окна.

## Message Compaction

Управление длинными сессиями: суммаризация старых сообщений при превышении порога.

**Trigger:** `total_tokens > max_tokens × compaction_threshold_ratio`

| Параметр | Default | Назначение |
|----------|---------|------------|
| `max_tokens` | 100 000 | Бюджет контекстного окна |
| `compaction_threshold_ratio` | 0.75 | Порог (75k tokens) |
| `recent_messages_to_keep` | 10 | Сколько последних сообщений оставить |
| `max_summary_tokens` | 500 | Лимит на summary |

**Два механизма, работающих последовательно:**

```mermaid
flowchart TD
    CHECK["total_tokens > threshold?"] -->|Да| SPLIT["Разделить: old / recent (последние 10)"]
    SPLIT --> SUMM["Суммаризировать old отдельной моделью"]
    SUMM -->|Успех| REPLACE["RemoveMessage(old) + AIMessage(summary)"]
    SUMM -->|Ошибка| TRIM
    REPLACE --> TRIM
    CHECK -->|Нет| TRIM
    TRIM["trim_messages (strategy=last, max_tokens) — ВСЕГДА"]
```

**Compaction** (условный) — умная суммаризация: старые сообщения заменяются на summary отдельной моделью. Сохраняет ключевые решения, нерешённые вопросы, текущий фокус; отбрасывает промежуточные tool outputs и reasoning. При ошибке суммаризации — пропускается (graceful degradation).

**Trimming** (безусловный) — safety net после compaction. `trim_messages(strategy="last")` гарантирует, что финальный набор сообщений не превышает `max_tokens`. Если всё влезает — no-op. Нужен потому, что compaction считает только messages, а system message (based prompt + KS Index + Skills Index) тоже занимает место в контекстном окне.

**Checkpointer хранит полную историю** — оба механизма оптимизируют контекстное окно, не уничтожают данные.

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

`response_format="content_and_artifact"` — tool возвращает и текстовый ответ, и metadata артефакта (`id`, `title`, `type`). Metadata передаётся через SSE как `artifact_created` event.

**User Memory** — автономное управление фактами о пользователе (подробнее — [user-memory.md](user-memory.md)):

| Tool | Назначение |
|------|------------|
| `save_user_memory` | Сохранить/обновить факт о пользователе |
| `delete_user_memory` | Удалить запись из памяти |

Агент решает самостоятельно, когда сохранять информацию. Память кросс-проектная — доступна во всех чатах пользователя.

**Skills:**

| Tool | Назначение |
|------|------------|
| `load_skill` | Загрузить полный SKILL.md по имени |

### External Tools (MCP)

Загружаются из MCP-серверов через **MCPToolResolver**. Итоговый набор tools для графа:

```
all_tools = internal_tools + mcp_tools(resolved)
```

Подробнее об MCP-архитектуре — секция [MCP Integration](#mcp-integration).

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
| `api_key_env` | Имя env-переменной с API ключом |
| `command` / `args` | Команда запуска для stdio |
| `allowed_tools` | Whitelist инструментов (фильтрация после получения) |
| `enabled` | Включён/выключен без удаления конфигурации |

Client: `MultiServerMCPClient` из `langchain_mcp_adapters`. Создаётся при старте, shared across invocations.

### Per-User MCP Servers

Пользователи добавляют собственные MCP-серверы через REST API на трёх уровнях: user → project → thread. Хранятся в БД с шифрованием API-ключей (Fernet).

Ограничения безопасности:
- Только HTTP-транспорты (`streamable_http`, `sse`) — `stdio` запрещён (RCE-вектор)
- SSRF-защита: DNS resolve + deny list приватных IP-диапазонов
- API-ключи зашифрованы, API возвращает только `has_api_key: bool` + `api_key_hint`

CRUD и каскадная видимость — [backend.md](backend.md).

### MCPToolResolver

Центральный компонент разрешения MCP tools для каждого запроса.

**Additive merge:** thread ∪ project ∪ user ∪ global — tools от всех уровней объединяются.

**Dedup:** при конфликте имён инструментов global побеждает (security boundary — пользовательский MCP не может подменить системный tool).

**Cache:** TTL-кэш с targeted invalidation по scope tuple `(user_id, project_id, thread_id)`. CRUD-операции над MCP-серверами инвалидируют соответствующий scope.

**Graceful degradation:** недоступный MCP-сервер → skip + warning в логах, остальные tools работают.

## Observability

Опциональная интеграция с Langfuse (подробнее — [observability.md](observability.md)).

- `CallbackHandler` инжектируется в `config["callbacks"]` графа — автоматическое логирование LLM calls
- Root span `agent-run` с propagation атрибутов: `user_id`, `session_id` (thread_id), `project_id`
- `trace_id` передаётся через SSE для привязки user feedback
- Model definitions с pricing — cost tracking per invocation

Langfuse выполняет dual role: tracing (observability) + prompt management (runtime source of truth для системных промптов). Подробнее — [prompt-management.md](prompt-management.md).

**Graceful degradation:** при недоступности Langfuse — `_NoOpSpan` (no-op tracing), промпты переключаются на file fallback. Приложение работает без трейсинга.

## Graceful Degradation

| Компонент | При отказе | Поведение |
|-----------|-----------|-----------|
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
| `mcp_servers` | Global MCP-серверы: transport, URL, API keys, allowed_tools |
| `models` | Model definitions: pricing, match patterns (Langfuse cost tracking) |

**Prompt files** — seed-файлы в `configs/prompts/`. Source of truth для промптов — Langfuse; файлы используются для seeding и как fallback. Подробнее — [prompt-management.md](prompt-management.md).

Application-level настройки — `backend/app/config.py` через Pydantic Settings. Ключевые env vars для feat-003:
- `MCP_ENCRYPTION_KEY` — Fernet-ключ для шифрования API-ключей per-user MCP
- `LANGFUSE_PROMPT_LABEL` — label для фетча промптов (default: `development`)
