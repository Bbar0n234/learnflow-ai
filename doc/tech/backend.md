# Backend

Архитектура верхнего уровня и стек — в [vision.md](../vision.md). Здесь — детальное описание бэкенда: слоистая архитектура, API, Agent Runtime, Persistence.

## Layered Architecture

### Слои

Слои показаны цветными подложками поверх компонентов и их связей; внизу — внешние системы:

```mermaid
graph TD
    subgraph COMP["Composition Root"]
        MAIN["main.py — lifespan,<br>синглтоны в app.state"]
        CONFIG["config.py — Settings"]
    end

    subgraph APIL["API Layer — app/api/"]
        ROUTES["routes/ — роутеры по ресурсам"]
        SCHEMAS["schemas/ — Pydantic-контракты"]
        DEPS["deps.py — DI-фабрики per-request"]
    end

    subgraph SVCL["Service Layer — app/services/"]
        CHATSVC["ChatService — thread mapping,<br>делегирование в AgentRunner"]
        TITLESVC["ChatTitleGenerator — fire-and-forget<br>auto-title, own DB session"]
        CRUD["CRUD-сервисы — Project,<br>Sphere, UserMemory, SkillContext, MCPServer"]
        WSSVC["ArtifactWorkspaceService ·<br>UploadWorkspaceService — тонкие обёртки<br>над Workspace для REST"]
        RESOLVER["ModelConfigResolver ·<br>MCPToolResolver"]
        ENC["EncryptionService — Fernet"]
    end

    subgraph AGTL["Agent Layer — app/agent/"]
        RUNNER["AgentRunner — runner.py"]
        FACTORY["GraphFactory — graph_factory.py"]
        GRAPH["StateGraph — graph.py"]
        TOOLS["tools/ — KS, файлы workspace<br>(read/write/list), execute_code/run_command,<br>user memory, skill context, skills"]
        GUARD["security/ — SecurityGuard:<br>detectors + LLM classifier"]
        PB["prompt_builder.py"]
    end

    subgraph DATAL["Data Layer"]
        REPOS["repositories/ — по репозиторию<br>на сущность (ORM CRUD)"]
        STORAGE["storage/ — Workspace (файлы<br>project workspace + /skills) ·<br>TraceStore (Redis)"]
        MODELS["models/ — SQLAlchemy ORM"]
    end

    subgraph INFRAL["Infra — app/infra/"]
        DBE["db.py — engine/sessions"]
        LG["langgraph.py —<br>Checkpointer + Store"]
        LLM["llm.py — LLM-клиенты"]
        IMG["image_generation.py —<br>OpenRouter Image API"]
        MCPC["mcp.py — MultiServerMCPClient"]
        EXECC["executor.py — httpx-клиент<br>POST /jobs"]
        PP["PromptProvider"]
        RL["rate_limit.py"]
    end

    subgraph SECPL["Security Pipeline — app/security_pipeline/"]
        PROC["SecurityEventProcessor — structlog"]
        TRANS["RedisEventTransport"]
    end

    PG[("PostgreSQL learnflow")]
    REDIS[("Redis")]
    LLMAPI["LLM API —<br>OpenAI-compatible"]
    LF["Langfuse"]
    MCPEXT["Внешние MCP-серверы"]
    EXECSVC["executor-сервис<br>(gVisor, отдельный compose-сервис)"]

    MAIN -. "синглтоны через app.state" .-> DEPS
    CONFIG --- MAIN
    ROUTES --> SCHEMAS
    ROUTES --> DEPS
    ROUTES --> RL
    DEPS --> CHATSVC
    DEPS --> CRUD
    DEPS --> WSSVC
    WSSVC --> STORAGE
    CHATSVC --> RUNNER
    CHATSVC --> REPOS
    CHATSVC --> STORAGE
    CHATSVC --> TITLESVC
    TITLESVC --> REPOS
    TITLESVC --> LLM
    TITLESVC --> PP
    CRUD --> REPOS
    CRUD --> GUARD
    CRUD --> ENC
    CRUD --> STORAGE
    RUNNER --> RESOLVER
    RESOLVER --> MCPC
    RUNNER --> FACTORY
    FACTORY --> GRAPH
    FACTORY --> LLM
    FACTORY --> LG
    GRAPH --> TOOLS
    GRAPH --> GUARD
    GRAPH --> PB
    GUARD --> LLM
    PB --> PP
    TOOLS --> REPOS
    TOOLS --> STORAGE
    TOOLS --> IMG
    TOOLS --> EXECC
    REPOS --> MODELS
    REPOS --> DBE
    STORAGE -->|TraceStore| REDIS
    DBE --> PG
    LG --> PG
    LLM --> LLMAPI
    IMG --> LLMAPI
    PP --> LF
    MCPC --> MCPEXT
    EXECC -->|"POST /jobs (сеть exec)"| EXECSVC
    RUNNER -. "tracing — CallbackHandler" .-> LF
    ROUTES -. "structlog: auth, rate limit" .-> PROC
    GUARD -. "structlog: guard verdicts" .-> PROC
    PROC --> TRANS
    TRANS -->|XADD| REDIS

    style COMP fill:#8b949e1a,stroke:#8b949e,color:#8b949e
    style APIL fill:#58a6ff1a,stroke:#58a6ff,color:#58a6ff
    style SVCL fill:#3fb9501a,stroke:#3fb950,color:#3fb950
    style AGTL fill:#bc8cff1a,stroke:#bc8cff,color:#bc8cff
    style DATAL fill:#d299221a,stroke:#d29922,color:#d29922
    style INFRAL fill:#39c5cf1a,stroke:#39c5cf,color:#39c5cf
    style SECPL fill:#f851491a,stroke:#f85149,color:#f85149
```

Composition root — `app/main.py`: lifespan инициализирует синглтоны (engine, AgentRunner, guard и т.д.) в `app.state`; `app/api/deps.py` — per-request фабрики поверх `app.state`.

- **API Layer** — HTTP/SSE-интерфейс, Pydantic-валидация, маршрутизация. Не содержит бизнес-логики.
- **Service Layer** — CRUD-сервисы (ProjectService, UserMemoryService, SkillContextService, MCPServerService, SphereService) + thin ChatService для chat-операций. ChatService оркестрирует взаимодействие с AgentRunner (маппинг chat_id → thread_id, model resolution, обновление thread_views, формирование config), а также rename/delete чата и каскад удаления (полиморфные MCP-disables → удаление строки → commit → best-effort очистка LangGraph checkpoints через `AgentRunner.delete_thread`) и удаление workspace-директории проекта при удалении проекта. Отдельный сервис `ChatTitleGenerator` — fire-and-forget генерация auto-title дешёвой LLM: реестр задач по `thread_id` держится в самом объекте (создаётся в lifespan, живёт в `app.state.chat_title_generator`, с `shutdown()`-teardown), задача работает в собственной DB-сессии и атомарно-условно пишет title (не перезаписывает ручной rename или заблокированный чат). `ArtifactWorkspaceService`/`UploadWorkspaceService` — тонкие обёртки над `Workspace` для REST-поверхности артефактов и загрузки вложений: не CRUD-сервисы (файловая система — источник правды, не ORM), их единственная причина существования — import-linter контракт «`api/routes` не импортирует `storage` напрямую» (routes ходят в файловый слой только через них). Write-методы для persistent storage (MCP-серверы, custom instructions, KS write через REST, skill context write через REST) первыми вызывают security guard — INJECTION → HTTP 422, до endpoint-специфичных валидаций ([security/architecture.md](../security/architecture.md)). ModelConfigResolver — каскадное разрешение модели per-request.
- **Agent Layer** — LangGraph-граф, GraphFactory (per-request build+compile), tools, skills, context engineering, memory, security (inline-проверки в графе и стриминге — [architecture.md](../security/architecture.md)). LangGraph-связанность сдержана внутри этого слоя: наружу выходят только доменные типы, не LangGraph-специфичные.
- **Repository Layer** — SQLAlchemy, CRUD-доступ к app-managed таблицам, по репозиторию на ORM-сущность.
- **Storage Layer** — абстракции хранилища с заменяемым бэкендом или не-ORM семантикой (файлы, key-value); независимый сосед Repository Layer, не наследует и не оборачивает его. `Workspace` (файловый слой project workspace + read-only `/skills`, ADR-032 — единственный известный бэкенд, отдельный `typing.Protocol` не заводится) и `TraceStore` (Redis) — нейминг и граница с Repository Layer см. [conventions.md § Именование](conventions.md#именование).
- **Infra** — не слой с правилами вызовов, а утилитарный пакет с сконфигурированными клиентами внешних сервисов, включая `executor.py` — тонкий httpx-клиент к соседнему сервису `executor` (`POST /jobs`, [executor.md](executor.md)).

### Правила вызовов

| Вызов | Разрешён |
|-------|----------|
| API → Service | ✅ всегда (включая chat через ChatService) |
| Service → Repository | ✅ |
| Service → Storage | ✅ (`ChatService` → `TraceStore`) |
| Service → Agent Layer | ✅ (ChatService → AgentRunner) |
| Agent tools → Repository | ✅ прямой доступ |
| Agent tools → Storage | ✅ прямой доступ (файловые/исполняющие tools и `image_generation` → `Workspace`) |
| Agent → LangGraph Store / Checkpointer | ✅ нативно |
| Repository / Storage / Agent → Infra | ✅ клиенты |
| Repository → Service | ❌ |
| API → Repository | ❌, кроме тонкого read-only исключения (см. ниже) |
| API → Storage | ❌, кроме тонкого read-only исключения (см. ниже) |
| API → Agent Layer | ❌ (только через Service) |

Известное локализованное исключение: `services/mcp_server.py` импортирует схему из `api/schemas/mcp_servers.py` — против направления, без цикла.

Известное расхождение стиля DI: `ProjectService` получает `MCPServerRepository` обязательным конструкторским параметром, а `ChatService.delete_chat` инстанцирует его inline от собственной сессии — стили разошлись независимо, унификация не форсирована.

**Исключение — тонкий read-only инжект в route-handler.** API → Repository/Storage в обход Service-слоя допустим, когда выполнены все три условия: (1) только чтение; (2) ноль бизнес-логики в handler'е — он только достаёт данные и отдаёт их; (3) авторизация уже выполнена существующими dependencies (ownership-проверки и т.п.) до обращения к хранилищу. Появление бизнес-логики или записи требует Service-слоя.

Прецеденты:
- `list_user_servers` и симметричные list-хендлеры (`GET /users/me/mcp-servers` и project/thread-эквиваленты, `api/routes/mcp_servers.py`) — листинг напрямую через `MCPServerRepository`, без бизнес-логики.

Артефакты и вложения под это исключение больше не попадают: `api/routes/artifacts.py`/`uploads.py` ходят в файловый слой через `ArtifactWorkspaceService`/`UploadWorkspaceService` (Service Layer) — не read-only DI-обход, а обязательный посредник (import-linter контракт `api/routes ↛ storage`).

Write-хендлеры `mcp_servers.py` (create/update/delete) под это исключение не попадают — там есть бизнес-логика (guard, лимиты на scope, инвалидация резолвера); они остаются известным долгом R1 ([arch-checker.md](arch-checker.md#известные-исключения-allowlist)).

### Сквозной поток: сообщение в чат

Главный сценарий системы через все слои. Протокол SSE и lifecycle стрима — [streaming.md](streaming.md), внутренности графа — [agent-runtime.md](agent-runtime.md).

```mermaid
flowchart TD
    FE["Frontend"] -->|"POST /chats/{chat_id}/messages"| RT["api/routes/messages.py"]
    RT --> CS["ChatService<br>chat_id → thread_id · ModelConfigResolver · config"]
    CS --> TV["ThreadView — обновление метаданных чата"]
    CS --> AR["AgentRunner.stream()"]
    AR --> GF["GraphFactory — build + compile per-request"]
    GF --> G["StateGraph: agent ⇄ tools (ReAct)<br>+ inline security checkpoints"]
    G <--> TOOLS["tools/ — KS, artifacts, memory, skills, MCP"]
    G --> CKPT[("Checkpointer<br>полный state + история")]
    G -->|"события графа"| AR
    AR -->|"SSE events"| RT
    RT -->|"StreamingResponse"| FE
```

## API Layer

### Auth

JWT + Refresh Token. Access token (short-lived, localStorage) для API-запросов, refresh token (long-lived, httpOnly cookie) для обновления. Подробнее: [auth.md](auth.md), обоснование — [ADR-011](adr/ADR-011-auth-architecture.md).

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
| POST | `/projects/{id}/chats` | Создать чат в проекте (без тела — сервер ставит плейсхолдер названия) |
| GET | `/projects/{id}/chats` | Список чатов проекта |
| GET | `/projects/{id}/chats/{cid}` | История чата (сообщения) |
| PUT | `/projects/{id}/chats/{cid}` | Переименовать чат |
| DELETE | `/projects/{id}/chats/{cid}` | Удалить чат (идемпотентно, каскад) |
| GET | `/chats/recent` | Недавние чаты пользователя (across projects, для sidebar) |

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

Артефакт = файл в зоне `artifacts/` project workspace, не PG-строка ([ADR-032](adr/ADR-032-project-workspace-file-model.md)) — адресация путём в query-параметре, не сегментом URL (путь-как-сегмент конфликтует со слэшами: ASGI разворачивает `%2F` до роутинга).

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/projects/{id}/artifacts` | Без `path` — список (дерево строит фронт); с `?path=…` — detail одного файла (метаданные + `content` для текстовых) |
| GET | `/projects/{id}/artifacts/download?path=…` | Скачать файл как есть (`Content-Disposition: attachment`) |
| GET | `/projects/{id}/artifacts/media?path=…` | Бинарные данные (bytes + `Content-Type` по расширению) |

`download`/`media` без ветки `format=pdf` — PDF-экспорт файлами workspace больше не является бэкендовой фичей, он становится выходом джобы (скилл поверх execution runtime).

Media endpoint читает файл напрямую с диска (404, если файла нет). Кэш — `ETag`/`Last-Modified` из `(mtime, size)` + `Cache-Control: no-cache` (не `immutable`: путь — перезаписываемая идентичность, файл может быть перезаписан агентом под тем же путём; браузер ревалидирует условным запросом, 304/200). `X-Content-Type-Options: nosniff` сохранён.

Загрузка вложений пользователя — отдельный write-only endpoint:

| Метод | Путь | Назначение |
|-------|------|-----------|
| POST | `/projects/{id}/uploads` | Multipart-загрузка файла в зону `uploads/` workspace, ответ `{path}` |

REST-чтения `uploads/` нет (чип вложения в истории чата некликабелен, метаданные приезжают вместе с сообщением — см. [streaming.md](streaming.md)).

#### Models & Settings

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/models` | Список доступных моделей (whitelist из agent.yaml) |
| GET | `/users/me/settings` | Настройки пользователя (model override) |
| PUT | `/users/me/settings` | Обновить настройки пользователя |
| GET | `/projects/{id}/settings` | Настройки проекта |
| PUT | `/projects/{id}/settings` | Обновить настройки проекта |
| GET | `/projects/{id}/chats/{cid}/settings` | Настройки чата |
| PUT | `/projects/{id}/chats/{cid}/settings` | Обновить настройки чата |

Каскад разрешения модели: thread → project → user → Langfuse → agent.yaml. `model_name: null` = inherit.

#### User Memory

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/users/me/instructions` | Пользовательские инструкции |
| PUT | `/users/me/instructions` | Обновить инструкции (max 5000 chars) |
| GET | `/users/me/memories` | Список записей памяти агента |
| DELETE | `/users/me/memories/{key}` | Удалить запись памяти |

Инструкции включаются в system message каждого чата. Записи памяти создаются агентом через `save_user_memory` / `delete_user_memory` tools, удаляются пользователем через UI.

#### Skill Context

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/users/me/skill-contexts` | Список документов, сгруппированных по скиллу (`in_library` на группе) |
| GET | `/users/me/skill-contexts/{skill_name}/{key}` | Получить документ |
| PUT | `/users/me/skill-contexts/{skill_name}/{key}` | Заменить существующий документ (404, если ещё не создан) |
| DELETE | `/users/me/skill-contexts/{skill_name}/{key}` | Удалить документ |

Создание документа — только агент (`save_skill_context` tool, upsert); REST правит и удаляет существующие. Подробнее о модели и доставке в контекст агента — [user-memory.md § Skill Context](user-memory.md#skill-context).

#### MCP Servers

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/users/me/mcp-servers` | Список MCP серверов пользователя |
| POST | `/users/me/mcp-servers` | Добавить MCP сервер |
| PUT | `/users/me/mcp-servers/{sid}` | Обновить |
| DELETE | `/users/me/mcp-servers/{sid}` | Удалить |
| POST | `/users/me/mcp-servers/{sid}/test` | Тест подключения |

Аналогичные эндпоинты для project (`/projects/{id}/mcp-servers/...`) и thread (`/projects/{id}/chats/{cid}/mcp-servers/...`).

Cascade visibility: project/thread list endpoints поддерживают `?include_inherited=true` — возвращает inherited серверы из вышестоящих scope с `is_disabled` флагом. Toggle inherited серверов: `PUT .../mcp-servers/inherited/{sid}/toggle` с `{ disabled: bool }`.

Ограничения: max 5 серверов per scope, transport = http|sse (stdio запрещён), SSRF-защита (private IPs → 400), API key шифруется Fernet, `api_key_hint` хранит маску (первые/последние 4 символа) для отображения.

### Schemas

Pydantic request/response модели. Сквозные соглашения:
- **ID** — UUID для всех app-managed сущностей (включая ThreadView.thread_id). При вызовах LangGraph API — `str(thread_id)`.
- **Списки** — единый envelope `{ items, total, limit, offset }` (generic `Page[T]` в `app/api/schemas/common.py`); query-параметры `limit` (default 50, max 200) и `offset` через общий dependency `Pagination`.
- **Ошибки** — RFC 9457 Problem Details (`application/problem+json`): `{ type, title, status, detail, …extensions }`; глобальные handlers в `app/api/problem.py`. Детали — [conventions/api.md](conventions/api.md#rest-api).
- **Ownership** — path-цепочка валидируется зависимостями `UserProject` / `UserThread` (404 на чужой ресурс).

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
  Request:  (без тела)
  Response: { thread_id: UUID, title: str, created_at: datetime, updated_at: datetime }

GET /projects/{id}/chats
  Response: { items: [{ thread_id: UUID, title, created_at, updated_at }] }

GET /projects/{id}/chats/{cid}
  Response: { thread_id: UUID, title, messages: [{ id, role, content, created_at?, parts: [typed part...], attachments: [{ path, title }] }] }

PUT /projects/{id}/chats/{cid}
  Request:  { title: str }
  Response: { thread_id: UUID, title, created_at, updated_at }

DELETE /projects/{id}/chats/{cid}
  Response: 204 No Content (идемпотентно — повторный DELETE тоже 204)

GET /chats/recent?limit=10
  Response: { items: [{ thread_id: UUID, title, project_id, project_name, updated_at }] }
```

`role`: `"user" | "assistant"`. Messages достаются из checkpointer. Tool-сообщения на фронт не отдаются — вместо них ассистентское сообщение несёт `parts` (typed union: reasoning, text, tool_call, artifact — union-дискриминатор `type`, артефакты записи/перезаписи файла в этом ходе входят как part с `kind: created | updated`; полный протокол — [streaming.md](streaming.md)). `attachments` — файлы, приложенные пользователем к этому сообщению (`{path, title}`, путь в зоне `uploads/`); REST-чтения самого файла нет, чип в истории некликабелен.

Recents — последние чаты пользователя across all projects, сортировка по `updated_at` desc. Для sidebar.

Название чата пользователь нигде не вводит: `POST /chats` ставит плейсхолдер `DEFAULT_CHAT_TITLE` («Новый чат»), дешёвая LLM переписывает его по первому сообщению (см. ниже), `PUT` позволяет переименовать вручную в любой момент, включая заблокированные (`security_blocked`) чаты. `DELETE` каскадно подчищает связанные записи и best-effort удаляет LangGraph checkpoints этого треда — детали см. в описании `ChatService` ниже.

#### Messages

```
POST /projects/{id}/chats/{cid}/messages
  Request:  { content: str, attachments?: [path: str] }
  Response: SSE stream (формат — см. SSE Streaming Protocol)

POST /projects/{id}/chats/{cid}/cancel
  Response: { ok: bool }
```

`attachments` — пути, полученные ранее от `POST /projects/{id}/uploads` (см. Artifacts ниже); backend дописывает модели пометку с путями в текст сообщения и хранит вложения в metadata чекпоинта отдельно от чистого пользовательского текста.

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
  Response: { items: [{ path, title, type, updated_at }] }   # без ?path=, плоский список (Page[T])

GET /projects/{id}/artifacts?path=lecture-1/slides.md
  Response: { path, title, type, updated_at, content? }      # content отсутствует в JSON для бинарных файлов

GET /projects/{id}/artifacts/download?path=…
  Response: файл (Content-Disposition: attachment)

GET /projects/{id}/artifacts/media?path=…
  Response: bytes, Content-Type по расширению (404, если файла нет)

POST /projects/{id}/uploads
  Request:  multipart (одно поле file)
  Response: { path }   # "uploads/<санитайзенное имя>"
```

`path` — идентификатор артефакта: относительный путь внутри зоны `artifacts/` (без её префикса), вложенность поддерживается. Список — плоский `Page[T]` с полными путями; группировку в дерево директорий делает фронт. `type` — расширение файла без точки. Detail для бинарного файла отдаёт объект без ключа `content` (не `null`) — тело только через `/media`.

### SSE Streaming Protocol

Формат: type-in-data (индустриальный стандарт LLM-стриминга — OpenAI, Anthropic). Event types, lifecycle, cancellation, frontend consumption — [streaming.md](streaming.md).

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
│   ├── security/        # SecurityGuard, detectors, classifier, observer, prompt-builder helpers (→ security/architecture.md)
│   └── tools/           # Реализации tools
│
├── repositories/        # Repository Layer
│
├── storage/             # Storage Layer
│
├── models/              # SQLAlchemy ORM-модели (app-managed таблицы)
│
├── infra/               # Клиенты внешних сервисов, DB engine/sessions
│
└── security_pipeline/   # SecurityEventProcessor + Redis-транспорт (→ siem-service.md)
```

**api/** — HTTP/SSE-интерфейс. Роутеры сгруппированы по ресурсам, каждый вызывает соответствующий сервис. Schemas — Pydantic-контракт с фронтендом. deps.py — FastAPI dependencies для инъекции зависимостей в роутеры.

**services/** — Оркестрация и бизнес-правила. CRUD-сервисы (Project, UserMemory, SkillContext, MCPServer) + thin ChatService для chat-операций (маппинг chat_id → thread_id, model resolution, делегирование в AgentRunner, управление ThreadView, rename/delete чата с каскадом). `ArtifactWorkspaceService`/`UploadWorkspaceService` — тонкие обёртки над `Workspace`, единственная причина существования которых — import-linter контракт (`api/routes` не может импортировать `storage` напрямую). `ChatTitleGenerator` — отдельный fire-and-forget сервис auto-title (реестр задач в `app.state`, собственная DB-сессия, teardown в lifespan). ModelConfigResolver — каскадное разрешение модели; MCPToolResolver — резолв MCP-инструментов per-request (оба инжектятся в AgentRunner). EncryptionService (Fernet) — шифрование API-ключей user MCP-серверов. Зависимости (repositories, AgentRunner) — через конструктор, wiring в deps.py.

**agent/** — LangGraph-граф, GraphFactory (per-request build+compile), tools, context engineering, промпт. Публичный интерфейс — AgentRunner (stream, get_history, get_last_ai_message_id, cancel, delete_thread — best-effort удаление checkpoints по `thread_id`). LangGraph-типы не выходят за пределы этого пакета. tools/ — суб-пакет с внутренней группировкой (KS, файлы workspace — `read_file`/`write_file`/`list_files`, исполнение кода — `execute_code`/`run_command`, user memory, skill context, skills); подробный контракт инструментов — [agent-runtime.md](agent-runtime.md).

**skills/** — директория в корне репозитория (`skills/`, рядом с `backend/`, `configs/`). Каждый skill — поддиректория с `SKILL.md` (Claude Code compatible формат). Вынесены из backend, чтобы пользователь мог добавлять skills без необходимости лезть в код приложения. Доступ — read-only bind-mount `/skills` в оба контейнера (app и executor), не копия в workspace.

**repositories/** — CRUD-доступ к app-managed таблицам через SQLAlchemy async session. По репозиторию на сущность.

**storage/** — абстракции хранилища с заменяемым бэкендом или не-ORM семантикой: `Workspace` (`app/storage/workspace.py`) — файловый слой per-project workspace + read-only `/skills` ([ADR-032](adr/ADR-032-project-workspace-file-model.md)): резолв путей против двух корней, атомарная запись (tmp+rename), чтение с лимитом, листинг, snapshot/diff зоны `artifacts/` вокруг джобы; `TraceStore` (Redis) для маппинга trace_id/feedback. Независимый сосед `repositories/` — ни один из двух пакетов не импортирует другой; нейминг и граница между ними — [conventions.md § Именование](conventions.md#именование).

**models/** — SQLAlchemy ORM-модели для app-managed таблиц (User, Project, ThreadView, MCP-серверы, Settings, RefreshToken). Артефакты моделью не представлены — их источник правды файловая система, не PostgreSQL.

**infra/** — Сконфигурированные клиенты внешних сервисов: DB engine/session factory, Checkpointer + Store (`langgraph.py`), LLM-клиенты, клиент OpenRouter Image API (`image_generation.py` — голый `httpx`, без LangChain-обёртки), MCP client (`MultiServerMCPClient`), клиент соседнего сервиса `executor` (`executor.py` — тонкий httpx-клиент `POST /jobs`, [executor.md](executor.md)), PromptProvider (Langfuse SDK wrapper), rate limiting, Redis client. Импортируется из Repository Layer, Service Layer и Agent Layer. MCPToolResolver и EncryptionService живут в `services/`, не здесь.

## Agent Runtime

LangGraph-граф с ReAct-паттерном, context engineering, tools, skills, MCP-интеграция, security. Детальное описание — [agent-runtime.md](agent-runtime.md). Связанные концепты: [knowledge-sphere.md](knowledge-sphere.md), [user-memory.md](user-memory.md), [prompt-management.md](prompt-management.md), [observability.md](observability.md), [architecture.md](../security/architecture.md).

Ключевые ADR: [ADR-001](adr/ADR-001-general-agent.md) (General Agent), [ADR-002](adr/ADR-002-skills-system.md) (Skills), [ADR-003](adr/ADR-003-knowledge-sphere.md) (KS), [ADR-004](adr/ADR-004-progressive-disclosure.md) (Progressive Disclosure), [ADR-005](adr/ADR-005-ks-update-mechanism.md) (KS Updates), [ADR-006](adr/ADR-006-custom-stategraph.md) (Custom StateGraph), [ADR-007](adr/ADR-007-mcp-external-tools.md) (MCP), [ADR-013](adr/ADR-013-model-settings-storage.md) (Settings Storage), [ADR-014](adr/ADR-014-dynamic-model-resolution.md) (Graph Factory), [ADR-015](adr/ADR-015-unified-memory-backend.md) (Store Memory), [ADR-016](adr/ADR-016-per-scope-mcp-servers.md) (MCP Servers), [ADR-017](adr/ADR-017-prompt-injection-defense.md) (Sec 1.0), [ADR-018](adr/ADR-018-siem-service-topology.md) (SIEM Topology), [ADR-020](adr/ADR-020-security-event-contract.md) (Event Contract), [ADR-022](adr/ADR-022-protected-disclosable-boundary.md) (Confidentiality Boundary), [ADR-023](adr/ADR-023-two-level-detection.md) (Detection Layers), [ADR-024](adr/ADR-024-streaming-security-guard.md) (Streaming Guard).

## Persistence

Две системы хранения: PostgreSQL (структурированные данные — два механизма управления, LangGraph-managed и app-managed) и файловый workspace per project (артефакты, вложения, рабочие файлы агента — [ADR-032](adr/ADR-032-project-workspace-file-model.md)). Миграции app-managed таблиц PostgreSQL — через Alembic (async engine); у workspace миграций нет, файловая система — источник правды сама по себе.

```mermaid
graph LR
    AGENT["Agent Layer —<br>Checkpointer + Store, нативно LangGraph"]
    REPOS["repositories/ —<br>SQLAlchemy async"]
    WSCLS["storage/ —<br>Workspace (файловый слой)"]

    subgraph PG["PostgreSQL learnflow"]
        subgraph LGM["LangGraph-managed — схема создаётся фреймворком"]
            CPT["checkpoints · checkpoint_blobs<br>checkpoint_writes · checkpoint_migrations"]
            STORET["store — KS per-project,<br>User Memory per-user"]
        end
        subgraph APPM["App-managed — миграции Alembic"]
            CORE["User · Project · ThreadView · RefreshToken"]
            SETT["UserSettings · ProjectSettings · ThreadSettings"]
            MCPS["User/Project/ThreadMCPServer · MCPServerDisable"]
        end
    end

    subgraph WS["volume workspaces — вне PostgreSQL"]
        WSFILES["/workspaces/{project_id}/artifacts · uploads · …"]
    end

    AGENT --> CPT
    AGENT --> STORET
    REPOS --> CORE
    REPOS --> SETT
    REPOS --> MCPS
    WSCLS --> WSFILES
    CORE -. "ThreadView.thread_id = str(UUID) →<br>LangGraph thread_id" .- CPT

    style PG fill:#8b949e12,stroke:#8b949e,color:#8b949e
    style LGM fill:#bc8cff1a,stroke:#bc8cff,color:#bc8cff
    style APPM fill:#d299221a,stroke:#d29922,color:#d29922
    style WS fill:#3fb9501a,stroke:#3fb950,color:#3fb950
```

### LangGraph-managed

Управляется фреймворком, таблицы создаются автоматически.

**Checkpointer** — полный state агента, включая историю сообщений. Сообщения не дублируются в отдельную app-таблицу: checkpointer хранит полную историю, доступную через `get_state()`. Таблицы: `checkpoints`, `checkpoint_blobs`, `checkpoint_writes`, `checkpoint_migrations`.

**Store** — Knowledge Sphere (per-project) и User Memory (per-user: custom instructions, agent memory, skill context). Таблицы: `store`, `store_vectors` (будущее: embeddings). Namespace-based изоляция — [user-memory.md](user-memory.md#storage).

### App-managed

Управляется нашим Repository Layer через SQLAlchemy.

```
User
├── id, name, password_hash, is_admin, created_at

RefreshToken
├── id (UUID PK), user_id (FK CASCADE), token_hash (indexed), expires_at, created_at, revoked_at

Project
├── id, user_id, name, created_at, updated_at

ThreadView
├── thread_id (PK, UUID — при вызовах LangGraph конвертируется в str), project_id, title, security_blocked (bool), created_at, updated_at

UserSettings / ProjectSettings / ThreadSettings
├── user_id|project_id|thread_id (PK, FK CASCADE), model_name, extra_body (JSONB), created_at, updated_at

UserMCPServer / ProjectMCPServer / ThreadMCPServer
├── id (UUID PK), user_id|project_id|thread_id (FK CASCADE), name, transport, url, api_key_encrypted, api_key_hint, allowed_tools (JSONB), is_active, created_at, updated_at
├── UNIQUE(scope_id, name)

MCPServerDisable
├── scope_type + scope_id + server_id (composite PK) — disables inherited server at child scope
```

**ThreadView** — легковесная индексная таблица для UI (листинг чатов, заголовки, даты). OSS LangGraph не предоставляет API для листинга threads, поэтому метаданные чатов хранятся отдельно. `security_blocked` маркируется при INJECTION на любом runtime checkpoint'е; FastAPI-зависимость на POST `/messages` отдаёт 403 пока флаг стоит ([security/architecture.md](../security/architecture.md)).

### Файловый workspace (вне PostgreSQL)

Артефакты, ранее хранившиеся в PG-таблицах `artifacts`/`artifact_blobs`, — файлы в `/workspaces/{project_id}/artifacts/` на именованном volume, смонтированном в `app` и `executor`; идентификатор артефакта — путь относительно этой зоны, не UUID. `uploads/` — вложения пользователя; остальное пространство workspace — рабочие файлы агента. PG-индекса нет: файловая система — единственный источник правды, `Workspace` (`app/storage/workspace.py`) — единственная точка доступа к ней. Модель, lifecycle, границы путей — [ADR-032](adr/ADR-032-project-workspace-file-model.md); контракт исполнения кода над этими же файлами — [executor.md](executor.md).

### Связи

```
User 1 → N Project
Project 1 → N ThreadView
ThreadView.thread_id = str(UUID) → LangGraph thread_id (связь с checkpointer)
Project.id = {project_id} → директория /workspaces/{project_id} (файловая, не FK)
```

## Logging

Централизованное логирование на базе structlog поверх stdlib через `ProcessorFormatter`. Обоснование — [ADR-009](adr/ADR-009-logging-strategy.md). Стиль и семантика уровней — [conventions.md](conventions.md#logging-conventions). Трейсинг и observability — [observability.md](observability.md).

### Setup

Единая точка входа: `backend/app/infra/logging.py` → `setup_logging()`. Вызывается в `lifespan()` до инициализации сервисов.

Конфигурация:
- `configs/logging.yaml` — формат вывода (`human-readable` / `json`), per-library overrides для шумных библиотек
- `LOG_LEVEL` env var — уровень логирования (default: `info`)

### Structlog + stdlib интеграция

Подход "Rendering using structlog-based formatters within logging": structlog loggers (наш код) и stdlib loggers (uvicorn, sqlalchemy, httpx) проходят через единый `ProcessorFormatter` → единый формат вывода.

### Request ID

FastAPI middleware генерирует UUID для каждого HTTP-запроса → `structlog.contextvars`. Все лог-записи в контексте запроса автоматически содержат `request_id`.

### Security Event Logging Convention

Структурированное логирование security-событий для SIEM pipeline. Логирование вызывается с флагом `security_event=True` и canonical `event_type` из vocabulary:

```python
logger.warning(
    "injection detected",
    security_event=True,
    event_type="agent.guard.input.classifier_injection",
    severity="critical",
    metadata={"checkpoint": "user_input", "detector": "llm_classifier"}
)
```

**Обработка:** `SecurityEventProcessor` перехватывает лог-записи с `security_event=True`, нормализует в `SecurityEvent`, пубирует в Redis Stream. Context binding (ip, user_id, request_id, thread_id и т.д.) вытягивается из contextvars автоматически.

**Vocabulary:** Полный набор `event_type` и их metadata-формы — [security-events.md](security-events.md). Типизация via Literal для mypy-проверяемости.

## SIEM Service

Отдельный FastAPI backend-сервис (порт 8001, собственная PostgreSQL siem-db): потребляет security-события из Redis Stream, коррелирует, генерирует алерты, отдаёт admin-only REST API для мониторинга. Main app — producer событий (см. Security Event Logging Convention выше); процессная изоляция и blast radius — [ADR-018](adr/ADR-018-siem-service-topology.md).

Полное описание сервиса (слои, pipeline, correlation engine, persistence, API, конфигурация) — [siem-service.md](siem-service.md).

## Executor Service

Второй соседний сервис: исполнение кода, который пишет агент (`execute_code`/`run_command`), происходит не в процессе backend'а, а в отдельном сервисе `executor` под gVisor — недоверенный код не должен оказаться рядом с секретами, БД и Store. Backend — единственный клиент, канал один: `POST /jobs` по изолированной сети `exec`. Файловые операции (`read_file`/`write_file`/`list_files`, REST-отдача артефактов) через executor не идут — backend читает/пишет тот же volume workspace напрямую.

Полный контракт джобы, слои песочницы, kill-механика, конфигурация — [executor.md](executor.md); обоснование выбора изоляции — [ADR-031](adr/ADR-031-execution-runtime-isolation.md).

## Error Handling

Конвенции выбора сигнала, барьерный стек, graceful degradation vs fail-fast, таймауты — [conventions.md](conventions.md#обработка-ошибок).

Main app реализует: иерархию `AppError` в `services/exceptions.py` (доменные исключения без знания о HTTP-транспорте); барьерный стек на `app/api/problem.py` (3 слоя: `AppError` → инфра-исключения → generic 500); SSE-барьер в `api/routes/messages.py` (терминальный `error`-event для непойманных исключений в стриме агента).

## Configuration

`pydantic-settings` с загрузкой из env vars. Набор параметров выводится из стека: DB URL, LLM API key/model, CORS origins, Langfuse credentials. Механика env-файлов — в [conventions.md](conventions.md#docker).

Ключевые env vars:
- `MCP_ENCRYPTION_KEY` — Fernet-ключ для шифрования API-ключей per-user MCP серверов
- `LANGFUSE_PROMPT_LABEL` — label для фетча промптов (default: `development`)
- `LANGFUSE_PROMPT_CACHE_TTL` — TTL кэша промптов в секундах (default: `60`)
- `CANARY_SECRET` — HMAC secret для canary token (→ [architecture.md](../security/architecture.md))
- `LLM_DEFENSE_ENABLED` — операционный тумблер inline LLM-защиты (guard + security-часть промпта); default `true`, в проде `false` (→ [architecture.md](../security/architecture.md))
- `SIEM_ENABLED` — операционный тумблер эмиссии security-событий в Redis Stream; default `true`, в проде `false` (→ [siem-service.md](siem-service.md#kill-switch))
- `CLIENT_IP_SOURCE` / `CLIENT_IP_XFF_HOPS` — источник клиентского IP (`socket` / `x-real-ip` / `x-forwarded-for`) и отступ справа для XFF; default `socket`, в проде `x-real-ip` (→ [conventions.md](conventions.md#logging-conventions), [setup/production.md](setup/production.md))
- `WORKSPACES_ROOT` / `SKILLS_ROOT` — корни файлового слоя (volume `workspaces`, ro-mount `/skills`); default `/workspaces` / `/skills` (→ [ADR-032](adr/ADR-032-project-workspace-file-model.md))
- `WORKSPACE_READ_LIMIT_CHARS` / `WORKSPACE_DIFF_FILE_LIMIT_BYTES` / `WORKSPACE_DIFF_TOTAL_LIMIT_BYTES` — потолки чтения `read_file` и diff-снапшота `artifacts/` вокруг джобы (per-file/суммарный на джобу; превышение — `diff: null`, не отказ)
- `UPLOAD_MAX_SIZE_BYTES` — потолок размера файла в `POST /projects/{id}/uploads`
- `EXECUTOR_BASE_URL` / `EXECUTOR_JOB_TIMEOUT_SECONDS` / `EXECUTOR_CLIENT_TIMEOUT_GRACE_SECONDS` — клиентские knobs httpx-обвязки `execute_code`/`run_command` к сервису `executor` (сами knobs executor-контейнера — отдельный `Settings` с тем же префиксом `EXECUTOR_`, другой процесс, документированы в [executor.md](executor.md))
- `EXECUTOR_AUTH_TOKEN` — общий с executor'ом секрет, уходит в `Authorization: Bearer` на каждый `POST /jobs`. Обязателен, без дефолта: backend не стартует без него, а значение обязано совпадать с тем, что получил контейнер `executor` ([executor.md](executor.md) § Аутентификация вызывающего)

Agent-специфичная конфигурация (модель, контекст, промпт, summarization, MCP) — отдельный YAML-файл, не env vars. Prompt management — [prompt-management.md](prompt-management.md).

**Допущение: один uvicorn-воркер.** Канал эмиссии `artifact_created`/`artifact_updated` (reporter узла `tools`) работает in-process — tool-вызов и SSE-подписчик того же хода находятся в одном процессе backend'а. При масштабировании на несколько uvicorn-воркеров без доработки (например, Redis pub/sub между воркерами) доставка этих событий сломается для запросов, обслуженных разными воркерами. Подробности протокола — [streaming.md](streaming.md).
