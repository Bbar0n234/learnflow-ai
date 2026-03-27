# Backend

Архитектура верхнего уровня и стек — в [vision.md](../vision.md). Здесь — детальное описание бэкенда: слоистая архитектура, API, Agent Runtime, Persistence.

## Layered Architecture

### Слои # TODO: Ну по-хорошему бы это визуализировать не через ASCII диаграммы, конечно, а через Mermaid.

```
API Layer — FastAPI routes, schemas, SSE transport
    │
Service Layer — оркестрация, бизнес-правила
    │               │
    │          Agent Layer — LangGraph граф, tools, skills, context, memory
    │               │
Repository Layer ←──┘
    │
Infra — DB engine/sessions, LLM client, MCP client, HTTP client
```

- **API Layer** — HTTP/SSE-интерфейс, Pydantic-валидация, маршрутизация. Не содержит бизнес-логики.
- **Service Layer** — CRUD-сервисы (ProjectService, ArtifactService) + thin ChatService для chat-операций. ChatService оркестрирует взаимодействие с AgentRunner (маппинг chat_id → thread_id, обновление thread_views, формирование config).
- **Agent Layer** — LangGraph-граф, tools, skills, context engineering, memory. LangGraph-связанность сдержана внутри этого слоя: наружу выходят только доменные типы, не LangGraph-специфичные.
- **Repository Layer** — SQLAlchemy, доступ к app-managed таблицам.
- **Infra** — не слой с правилами вызовов, а утилитарный пакет с сконфигурированными клиентами внешних сервисов.

### Правила вызовов

| Вызов | Разрешён |
|-------|----------|
| API → Service | ✅ всегда (включая chat через ChatService) |
| Service → Repository | ✅ |
| Service → Agent Layer | ✅ (ChatService → AgentRunner) |
| Agent tools → Repository | ✅ прямой доступ |
| Agent → LangGraph Store / Checkpointer | ✅ нативно |
| Repository / Agent → Infra | ✅ клиенты |
| Repository → Service | ❌ |
| API → Repository | ❌ |
| API → Agent Layer | ❌ (только через Service) |

## API Layer

### Auth

Multi-user с простым разделением по пользователям.

**MVP:** header `X-User-Name` — deps.py извлекает имя, передаёт в роутеры через `Depends()`. Без паролей и токенов, достаточно для разграничения данных.

**Production:** подход к авторизации — открытый вопрос, решается отдельно.

### Endpoints

Все API-эндпоинты доступны под префиксом `/api` (например, `/api/projects`). Пути в таблицах ниже — относительно этого префикса. Health check (`GET /health`) — на root level, без префикса.

#### Projects

| Метод | Путь | Назначение |
|-------|------|-----------|
| POST | `/projects` | Создать проект |
| GET | `/projects` | Список проектов пользователя |
| GET | `/projects/{id}` | Получить проект |
| PUT | `/projects/{id}` | Обновить (название и т.д.) |
| DELETE | `/projects/{id}` | Удалить проект |

#### Chats

| Метод | Путь | Назначение |
|-------|------|-----------|
| POST | `/projects/{id}/chats` | Создать чат в проекте |
| GET | `/projects/{id}/chats` | Список чатов проекта |
| GET | `/projects/{id}/chats/{cid}` | История чата (сообщения) |
| GET | `/chats/recent?limit=10` | Недавние чаты пользователя (across projects, для sidebar) |

#### Messages (ядро)

| Метод | Путь | Назначение |
|-------|------|-----------|
| POST | `/projects/{id}/chats/{cid}/messages` | Отправить сообщение → SSE stream с ответом агента |
| POST | `/projects/{id}/chats/{cid}/cancel` | Отменить генерацию |

Стриминг через SSE (Server-Sent Events) — индустриальный стандарт для LLM-проектов. LangGraph нативно поддерживает SSE через `stream_events`.

#### Knowledge Sphere

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/projects/{id}/sphere` | Текущий шар (полный) |
| PUT | `/projects/{id}/sphere` | Перезаписать шар |

Для разработки, отладки и будущего UI. PATCH (частичное обновление секций) — при необходимости.

#### Artifacts

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/projects/{id}/artifacts` | Список артефактов проекта |
| GET | `/projects/{id}/artifacts/{aid}` | Получить артефакт (метаданные + content) |
| GET | `/projects/{id}/artifacts/{aid}/download?format=md\|pdf` | Скачать в формате |

PDF — конвертация из Markdown на бэкенде (pandoc / weasyprint).

### Schemas

Pydantic request/response модели. Сквозные соглашения:
- **ID** — UUID для всех app-managed сущностей (включая ThreadView.thread_id). При вызовах LangGraph API — `str(thread_id)`.
- **Списки** — обёртка `{ items: [...] }`, расширяемая пагинацией позже.
- **Ошибки** — дефолт FastAPI (`{ detail: "..." }`, 422 с полями валидации).

#### Projects

```
POST /projects
  Request:  { name: str }
  Response: { id: UUID, name: str, created_at: datetime, updated_at: datetime }

GET /projects
  Response: { items: [{ id, name, created_at, updated_at }] }

GET /projects/{id}
  Response: { id, name, created_at, updated_at }

PUT /projects/{id}
  Request:  { name: str }
  Response: { id, name, created_at, updated_at }

DELETE /projects/{id}
  Response: 204 No Content
```

#### Chats

```
POST /projects/{id}/chats
  Request:  { title?: str }
  Response: { thread_id: UUID, title: str, created_at: datetime, updated_at: datetime }

GET /projects/{id}/chats
  Response: { items: [{ thread_id: UUID, title, created_at, updated_at }] }

GET /projects/{id}/chats/{cid}
  Response: { thread_id: UUID, title, messages: [{ id, role, content, created_at?, artifacts: [{ id, title, type, created_at }] }] }

GET /chats/recent?limit=10
  Response: { items: [{ thread_id: UUID, title, project_id, project_name, updated_at }] }
```

`role`: `"user" | "assistant"`. Messages достаются из checkpointer. Tool-сообщения на фронт не отдаются.

Recents — последние чаты пользователя across all projects, сортировка по `updated_at` desc. Для sidebar.

#### Messages

```
POST /projects/{id}/chats/{cid}/messages
  Request:  { content: str }
  Response: SSE stream (формат — см. SSE Streaming Protocol)

POST /projects/{id}/chats/{cid}/cancel
  Response: { ok: bool }
```

#### Knowledge Sphere

```
GET /projects/{id}/sphere
  Response: { project_id: UUID, content: str, updated_at: datetime }

PUT /projects/{id}/sphere
  Request:  { content: str }
  Response: { project_id, content, updated_at }
```

#### Artifacts

```
GET /projects/{id}/artifacts
  Response: { items: [{ id, title, type, created_at }] }

GET /projects/{id}/artifacts/{aid}
  Response: { id, title, type, content, thread_id?, message_id?, created_at }

GET /projects/{id}/artifacts/{aid}/download?format=md|pdf
  Response: файл (Content-Disposition: attachment)
```

В списке — только метаданные, без content.

### SSE Streaming Protocol

Формат: type-in-data (индустриальный стандарт LLM-стриминга — OpenAI, Anthropic). Один поток `data:`, тип события внутри JSON.

#### Event types

| Type | Когда | Payload |
|------|-------|---------|
| `text_chunk` | Каждый токен/чанк от LLM | `{ content: str }` |
| `tool_start` | Агент вызывает tool | `{ tool: str, call_id: str }` |
| `tool_end` | Tool завершился | `{ tool: str, call_id: str }` |
| `artifact_created` | Агент создал артефакт | `{ id: UUID, title: str, artifact_type: str }` |
| `done` | Генерация завершена | `{ message_id?: str }` |
| `error` | Ошибка в процессе | `{ detail: str }` |

Tool-события отдают имя tool и `call_id` (для корреляции start/end при параллельных вызовах) — параметры и сырые результаты не отдаются.

#### Lifecycle

```
POST /projects/{id}/chats/{cid}/messages → 200, Content-Type: text/event-stream

  data: {"type": "text_chunk", "content": "Давайте"}
  data: {"type": "text_chunk", "content": " разберём"}
  data: {"type": "tool_start", "tool": "web_search", "call_id": "..."}
  data: {"type": "tool_end", "tool": "web_search", "call_id": "..."}
  data: {"type": "text_chunk", "content": "По результатам..."}
  data: {"type": "artifact_created", "id": "...", "title": "...", "artifact_type": "markdown"}
  data: {"type": "done"}

  [connection closed]
```

`done` и `error` — терминальные события, после них соединение закрывается. При cancel (`POST /cancel`) — сервер отправляет `error` и закрывает стрим.

Маппинг LangGraph stream events → наши event types — внутреннее дело Agent Layer (AgentRunner).

## Module Structure

Горизонтальная нарезка по слоям. Конкретные файлы внутри пакетов выводятся из сущностей (Persistence), tools (Agent Runtime) и endpoints (API) — здесь не дублируются.

```
app/
├── main.py              # FastAPI app factory, lifespan
├── config.py            # Settings (pydantic-settings)
│
├── api/                 # API Layer
│   ├── routes/          # FastAPI роутеры (по ресурсам)
│   ├── schemas/         # Pydantic request/response модели
│   └── deps.py          # Dependencies: DB session, current user, инъекция сервисов
│
├── services/            # Service Layer
│
├── agent/               # Agent Layer
│   └── tools/           # Реализации tools
│
├── repositories/        # Repository Layer
│
├── models/              # SQLAlchemy ORM-модели (app-managed таблицы)
│
└── infra/               # Клиенты внешних сервисов, DB engine/sessions
```

**api/** — HTTP/SSE-интерфейс. Роутеры сгруппированы по ресурсам, каждый вызывает соответствующий сервис. Schemas — Pydantic-контракт с фронтендом. deps.py — FastAPI dependencies для инъекции зависимостей в роутеры.

**services/** — Оркестрация и бизнес-правила. CRUD-сервисы (Project, Artifact) + thin ChatService для chat-операций (маппинг chat_id → thread_id, делегирование в AgentRunner, управление ThreadView). Зависимости (repositories, AgentRunner) — через конструктор, wiring в deps.py.

**agent/** — LangGraph-граф, tools, context engineering, промпт. Публичный интерфейс — AgentRunner (stream, get_history, cancel). LangGraph-типы не выходят за пределы этого пакета. tools/ — суб-пакет с внутренней группировкой.

**skills/** — директория в корне репозитория (`skills/`, рядом с `backend/`, `configs/`). Каждый skill — поддиректория с `SKILL.md` (Claude Code compatible формат). Вынесены из backend, чтобы пользователь мог добавлять skills без необходимости лезть в код приложения.

**repositories/** — CRUD-доступ к app-managed таблицам через SQLAlchemy async session. По репозиторию на сущность.

**models/** — SQLAlchemy ORM-модели для app-managed таблиц (User, Project, ThreadView, Artifact).

**infra/** — Сконфигурированные клиенты: DB engine/session factory, LLM client, MCP client (`MultiServerMCPClient`), HTTP client. Импортируется из Repository Layer и Agent Layer.

## Agent Runtime

### General Agent

General Agent с ReAct loop — подробнее в [ADR-001](adr/ADR-001-general-agent.md).

```
General Agent = Based Prompt + ReAct Loop + Context Engineering + Memory + Tool Use
```

- **Based Prompt** — правила поведения агента (см. ниже)
- **ReAct Loop** — Reason → Action → Observe → Adjust, цикл до достижения цели
- **Context Engineering** — управление тем, что попадает в контекст и когда
- **Memory** — short-term (диалог) + long-term (Knowledge Sphere)
- **Tool Use** — вызов инструментов через единый интерфейс

Реализация на LangGraph. Checkpointer и Store — PostgreSQL с первого дня.

### Based Prompt

Текст промпта хранится в отдельном файле (не в коде). System message собирается из частей: based prompt + KS index + skills index.

Покрывает:
- **Роль и миссия** — AI assistant для tech-спикеров, JTBD
- **Взаимодействие** — expert-to-expert, match user's language, direct
- **Knowledge Sphere** — автономное обновление, когда подгружать секции
- **Artifacts** — save deliverables, не промежуточные черновики
- **Error handling** — retry/adapt, communicate problems
- **Границы** — focus on material preparation, honesty about uncertainty

Tool descriptions не дублируются в промпте — живут в docstrings инструментов.

### Memory

#### Short-term

История сообщений в пределах чата. LangGraph Checkpointer.

Compaction при приближении к лимиту контекста: суммаризация старых сообщений отдельной (дешёвой) моделью с сохранением ключевых решений и текущего фокуса. Graceful degradation: при сбое summarization — fallback на trim-only. Подробнее — [ADR-004](adr/ADR-004-progressive-disclosure.md).

#### Long-term (Knowledge Sphere)

Связанная картина проекта, а не набор атомарных фактов. Подробнее — [ADR-003](adr/ADR-003-knowledge-sphere.md).

**Управление (MVP):** Main Agent сам решает, когда обновить шар, и вызывает tool `update_sphere`. Полный контекст диалога → качественное решение. Отдельный Classifier / KS Agent — при реальных проблемах (перегрузка контекста, cost). Подробнее: [ADR-005](adr/ADR-005-ks-update-mechanism.md).

**Два режима:**
1. Автономный — работает тихо, не грузит пользователя
2. Проактивный — пользователь видит шар, может править

**Хранение:** LangGraph Store + PostgreSQL. MVP-формат — структурированный Markdown. Миграция на Knowledge Graph с embeddings — при реальных failure modes (шар > 50k токенов).

### Skills

Skills в формате Claude Code — подгружаемые модули знаний, расширяющие поведение агента. Общепринятый стандарт, набирающий обороты в индустрии (Claude Code, Cursor и др.). Подробнее — [ADR-002](adr/ADR-002-skills-system.md).

**MVP:** файловая система + API-обёртка для подгрузки.

**Структура skill'а:** описание + паттерны (триггеры) + знания (prompts, docs).

**Планируемые skills:** structure, research.

**Lifecycle:** задача пользователя → агент подгружает skill (just-in-time) → использует → skill выгружается.

### Tools

#### Internal (работа с системой)

##### Knowledge Sphere (CRUD)

Index шара **не является tool** — формируется автоматически из Store и инжектится в system message при каждом вызове agent node (auto-derived, см. [ADR-004](adr/ADR-004-progressive-disclosure.md)).

```
get_section(section_id: str) → str
```
Получить Full секцию шара. Just-in-time подгрузка по решению агента.

```
create_section(section_id: str, description: str, content: str) → str
```
Создать новую секцию Knowledge Sphere.

```
update_section(section_id: str, content: str, target?: str, description?: str) → str
```
Обновить секцию. Два режима:
- **Patch** (target задан): fuzzy find & replace целевого фрагмента внутри секции. LLM цитирует неточно → fuzzy matching (Levenshtein distance, threshold 0.85). Scope по секции → нет cross-section замен.
- **Overwrite** (без target): полная перезапись content.

Опционально обновляет description.

```
delete_section(section_id: str) → str
```
Удалить секцию Knowledge Sphere.

##### Other

```
load_skill(skill_name: str) → SkillContent
```
Подгрузить skill в контекст. Just-in-time.

#### External (MCP)

Подключаются через MCP Client — готовые MCP-серверы, конкретный провайдер конфигурируется. Обоснование и альтернативы: [ADR-007](adr/ADR-007-mcp-external-tools.md).

Типичные tools (зависят от подключённого MCP-сервера): web search, URL scraping/reading, crawling. Default MVP: Firecrawl MCP (search + scrape + crawl в одном сервере).

MCP tools загружаются через `langchain-mcp-adapters`, конвертируются в стандартные `BaseTool` и живут в одном `ToolNode` вместе с internal tools.

#### Artifacts

```
create_artifact(title: str, content: str, type: str) → ArtifactRef
```
Сохранить результат работы агента как артефакт проекта. Возвращает artifact_id. Фронтенд рендерит карточку файла вместо инлайн-текста.

### Agent Graph

Custom StateGraph — обоснование в [ADR-006](adr/ADR-006-custom-stategraph.md). Детали по LangGraph-паттернам: [langgraph-reference.md](langgraph-reference.md).

```
START → agent ──→ tools_condition? ──tool_calls──→ tools (ToolNode) ─┐
                       │                                              │
                      нет                                             │
                       ▼                                              │
                      END                              agent ←────────┘
```

**Узлы:**
- **agent** — собирает context (Based Prompt + KS Index + trimmed messages) локально, вызывает LLM с bind_tools. Результат → messages. Context не записывается в state — подготовка эфемерна.
- **tools** — prebuilt `ToolNode` из `langgraph.prebuilt`. Поддерживает InjectedStore для KS-tools.

**State:** `MessagesState` — один ключ `messages`. Полная история, управляется reducer `add_messages`.

**Routing:** prebuilt `tools_condition` — conditional edge: есть tool_calls → tools, иначе → END.

**Config:** `thread_id`, `project_id`, `user_id` через `config["configurable"]`. Доступен в agent-ноде и tools.

### Context Engineering

Управление контекстом агента. Подробнее — [ADR-004](adr/ADR-004-progressive-disclosure.md).

| Что | Стратегия |
|-----|-----------|
| Knowledge Sphere Index | Pre-loaded (auto-derived из Store, инжектится в system message) |
| Full sections шара | Just-in-time (через get_section tool) |
| История диалога | В контексте + compaction при приближении к лимиту |
| Skills Index | Pre-loaded (scan из SKILL.md frontmatter, инжектится в system message) |
| Full skill content | Just-in-time (через load_skill tool) |

## Persistence

Одна PostgreSQL база, два механизма управления: LangGraph-managed и app-managed. Миграции app-managed таблиц — через Alembic (async engine).

### LangGraph-managed

Управляется фреймворком, таблицы создаются автоматически.

**Checkpointer** — полный state агента, включая историю сообщений. Сообщения не дублируются в отдельную app-таблицу: checkpointer хранит полную историю, доступную через `get_state()`. Таблицы: `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`.

**Store** — Knowledge Sphere (cross-thread память). Таблицы: `store`, `store_vectors` (будущее: embeddings).

### App-managed

Управляется нашим Repository Layer через SQLAlchemy.

```
User
├── id, name, created_at

Project
├── id, user_id, name, created_at, updated_at

ThreadView
├── thread_id (PK, UUID — при вызовах LangGraph конвертируется в str), project_id, title, created_at, updated_at

Artifact
├── id, project_id, thread_id, message_id, title, type (markdown | ...), content, created_at
```

**ThreadView** — легковесная индексная таблица для UI (листинг чатов, заголовки, даты). OSS LangGraph не предоставляет API для листинга threads, поэтому метаданные чатов хранятся отдельно.

### Связи

```
User 1 → N Project
Project 1 → N ThreadView
Project 1 → N Artifact
ThreadView.thread_id = str(UUID) → LangGraph thread_id (связь с checkpointer)
Artifact.thread_id → ThreadView.thread_id (артефакт создаётся в контексте чата)
```

## Logging

Централизованное логирование на базе structlog поверх stdlib через `ProcessorFormatter`.

### Setup

Единая точка входа: `backend/app/infra/logging.py` → `setup_logging()`. Вызывается в `lifespan()` до инициализации сервисов.

Конфигурация:
- `configs/logging.yaml` — формат вывода (`human-readable` / `json`), per-library overrides для шумных библиотек
- `LOG_LEVEL` env var — уровень логирования (default: `info`)

### Structlog + stdlib интеграция

Подход "Rendering using structlog-based formatters within logging": structlog loggers (наш код) и stdlib loggers (uvicorn, sqlalchemy, httpx) проходят через единый `ProcessorFormatter` → единый формат вывода.

### Request ID

FastAPI middleware генерирует UUID для каждого HTTP-запроса → `structlog.contextvars`. Все лог-записи в контексте запроса автоматически содержат `request_id`.

### Использование

Стиль и семантика уровней — в [conventions.md](conventions.md#logging-conventions).

## Error Handling

Основные сценарии покрываются фреймворками: ToolNode возвращает ошибку как ToolMessage (агент видит и решает сам в ReAct loop), FastAPI — стандартные HTTP-ошибки, SSE — терминальный `error` event. Детали (retry policy для LLM, поведение при disconnect, cancel semantics) — определяются при реализации.

## Configuration

`pydantic-settings` с загрузкой из env vars. Набор параметров выводится из стека: DB URL, LLM API key/model, MCP-серверы (transport, URL, API keys), CORS origins. Механика env-файлов — в [conventions.md](conventions.md#docker).

Agent-специфичная конфигурация (модель, контекст, промпт, summarization, MCP) — отдельный YAML-файл, не env vars.
