# Implementation Plan: feat-003 — Runtime Agent Configuration

## Context

Агент сейчас полностью статичен: модель, system prompt, MCP серверы — всё задаётся при старте, запекается в LangGraph StateGraph. Любое изменение = перезапуск сервиса. Персонализации пользователей нет.

**Цель:** runtime-конфигурация без перезапуска + per-user кастомизация на трёх уровнях (user → project → thread).

**Три трека:**
- **Track A** — Langfuse Prompt Management + Model Switching
- **Track B** — Memory Architecture (custom instructions + user memory)
- **Track C** — User MCP Servers

## Reference Documents

| Документ | Назначение |
|----------|------------|
| [design-brief.md](doc/tasks/iterations/post-mvp/feat-003-agent-config/design-brief.md) | Полный design: decisions, interfaces, file changes |
| [ADR-013](doc/tech/adr/ADR-013-model-settings-storage.md) | Per-Scope Settings: 3 typed tables с FK |
| [ADR-014](doc/tech/adr/ADR-014-dynamic-model-resolution.md) | Graph Factory: per-request build+compile |
| [ADR-015](doc/tech/adr/ADR-015-unified-memory-backend.md) | LangGraph Store как unified memory backend |
| [ADR-016](doc/tech/adr/ADR-016-per-scope-mcp-servers.md) | Per-Scope MCP Servers: storage, encryption, merge |
| [tasklist-post-mvp.md](doc/tasks/tasklist-post-mvp.md) | Definition of Done |
| [workflow.md](doc/workflow.md) | Рабочий процесс, итерации |
| [conventions.md](doc/tech/conventions.md) | Git flow, naming, code quality |
| [agent-runtime.md](doc/tech/agent-runtime.md) | Текущая архитектур�� агента |
| [backend.md](doc/tech/backend.md) | Layered architecture, API, persistence |
| [frontend.md](doc/tech/frontend.md) | Компоненты, state management, routing |
| [observability.md](doc/tech/observability.md) | Langfuse tracing |

## Architect Decisions (из диалога)

1. **Model UI:** все 3 уровня — user (/settings), project (Settings tab), chat (селектор слева сверху)
2. **MCP UI:** все 3 уровня — user (/settings), project (Settings tab), chat (tools panel)
3. **Settings API:** unified `/settings` endpoints (GET/PUT per scope)
4. **`allowed_tools` в MCP UI:** не показывать (поле остаётся в DB/API, скрыто на фронте)
5. **`make sync-prompts`:** включить в scope
6. **REST API paths:** `/api/users/me/settings`, `/api/projects/{pid}/settings`, `/api/projects/{pid}/chats/{tid}/settings`

## API Verification (быстро меняющие��я инструменты)

| Инструмент | Версия | Верификация |
|-----------|--------|-------------|
| **Langfuse SDK** | 4.0.1 | `Langfuse.get_prompt(name, label=, cache_ttl_seconds=, fallback=)` → `TextPromptClient`. `TextPromptClient.prompt` (str), `.config` (dict), `.compile(**kwargs)`. `Langfuse.create_prompt(name=, prompt=, labels=, config=)` |
| **LangGraph Store** | via langgraph 1.1.3 | `BaseStore.aget(namespace, key)` → `Item|None`. `aput(namespace, key, value)`. `asearch(namespace_prefix, limit=)` → `list[SearchItem]`. `adelete(namespace, key)` |
| **LangGraph Runtime** | 1.1.3 | `Runtime[T]` — attrs: `context`, `store`, `stream_writer`, `previous` |
| **LangGraph Checkpointer** | checkpoint 4.0.1 | `BaseCheckpointSaver.aget_tuple(config)` → `CheckpointTuple`. `checkpoint.channel_values` — dict с messages |
| **langchain-mcp-adapters** | 0.2.1 | `MultiServerMCPClient(connections)`. `get_tools(server_name=)` — **async**. `SSEConnection(transport="sse", url=, headers=)`. `StreamableHttpConnection(transport="streamable_http", url=, headers=)` |
| **Fernet** | cryptography 46.0.5 | `Fernet(key)`. `encrypt(bytes)→bytes`. `decrypt(bytes|str)→bytes`. `generate_key()→bytes` |

**Ключевые находки:**
- `MultiServerMCPClient.get_tools()` — **async** (не sync, как может показаться из документации)
- **MCP tools standalone:** tools из `get_tools()` захватывают `connection` config через closure. При каждом `tool.invoke()` создаётся свежая сессия через `create_session(connection)`. Клиент можно закрыть после получения tools — кэшируем tools, не клиент
- `BaseStore.asearch()` первый параметр — `namespace_prefix` (позиционный), не `namespace`
- `TextPromptClient.config` — `Dict[str, Any]`, заполняется из `prompt.config` при инициализации
- `Langfuse.get_prompt()` имеет параметр `fallback: str` — нативный file fallback через SDK
- `PromptProvider.get_prompt()` sync — при cache miss синхронный HTTP в async контексте. Langfuse SDK кэширует с TTL, miss раз в 60с. Приемлемо для текущего масштаба; при необходимости — `asyncio.to_thread()` wrap

## Logging Conventions (из conventions.md — применяются ко всему новому коду)

Backend: `structlog.get_logger()`, keyword-args: `logger.info("event", key=value)`. Frontend: `import { logger } from "@/shared/lib/logger"`.

| Уровень | Примеры событий feat-003 |
|---------|-------------------------|
| **INFO** | `"prompt fetched"`, `"model resolved"`, `"mcp tools loaded"`, `"settings updated"`, `"user memory saved"` |
| **WARNING** | `"langfuse prompt fetch failed, using file fallback"`, `"mcp server unreachable"`, `"user tools truncated to limit"`, `"encryption key not configured"` |
| **DEBUG** | `"cascade resolve details"`, `"mcp connection config"`, `"prompt cache hit"`, `"store fetch"` |
| **ERROR** | `"encryption failed"`, `"ssrf validation failed"`, `"migration error"` |

Антипаттерны: INFO на входе/выходе каждой функции (шум), WARNING для ожидаемого поведения, ERROR для клиентских ошибок (422).

---

## Implementation Phases

### Phase 1: Foundation — DB, Models, Config, Infra

**1.1 Alembic migration — 6 новых таблиц**

Определяем SQLAlchemy модели (1.2), затем `make migration msg="add settings and mcp servers"` — Alembic **автогенерирует** миграцию из diff моделей vs текущая БД. Применяем: `make migrate`.

Settings tables (ADR-013):
```
user_settings(user_id PK/FK → users.id CASCADE, model_name VARCHAR NULL, extra_body JSONB NULL, created_at, updated_at)
project_settings(project_id PK/FK → projects.id CASCADE, model_name VARCHAR NULL, extra_body JSONB NULL, created_at, updated_at)
thread_settings(thread_id PK/FK → thread_views.thread_id CASCADE, model_name VARCHAR NULL, extra_body JSONB NULL, created_at, updated_at)
```

MCP server tables (ADR-016):
```
user_mcp_servers(id UUID PK, user_id FK → users.id CASCADE, name VARCHAR, transport VARCHAR, url VARCHAR, api_key_encrypted BYTEA NULL, allowed_tools JSONB DEFAULT '[]', is_active BOOLEAN DEFAULT true, created_at, updated_at)
  UNIQUE(user_id, name)
project_mcp_servers(id UUID PK, project_id FK → projects.id CASCADE, name, transport, url, api_key_encrypted, allowed_tools, is_active, created_at, updated_at)
  UNIQUE(project_id, name)
thread_mcp_servers(id UUID PK, thread_id FK → thread_views.thread_id CASCADE, name, transport, url, api_key_encrypted, allowed_tools, is_active, created_at, updated_at)
  UNIQUE(thread_id, name)
```

**Результат:** автогенерированный файл в `backend/alembic/versions/`

**1.2 SQLAlchemy models**

`backend/app/models/settings.py`:
- `SettingsMixin` (model_name, extra_body, created_at, updated_at)
- `UserSettings`, `ProjectSettings`, `ThreadSettings` — каждая с proper FK

`backend/app/models/mcp_server.py`:
- `MCPServerMixin` (name, transport, url, api_key_encrypted, allowed_tools, is_active, created_at, updated_at)
- `UserMCPServer`, `ProjectMCPServer`, `ThreadMCPServer` — каждая с FK + UNIQUE constraint

`backend/app/models/__init__.py` — обновить imports.

**1.3 Config changes**

`backend/app/config.py` — новые поля Settings:
```python
langfuse_prompt_label: str = "production"
langfuse_prompt_cache_ttl: int = 60
mcp_encryption_key: str = ""
```

`backend/app/agent/config.py` — новые типы:
```python
@dataclass
class AvailableModel:
    name: str
    display_name: str

@dataclass
class ResolvedModelConfig:
    model: str
    extra_body: dict[str, Any] | None
    source: str  # "thread"|"project"|"user"|"langfuse"|"config"
```
- Добавить `available_models: list[AvailableModel]` в `AgentConfig`
- Удалить `PromptConfig` (промпты теперь из PromptProvider)

`configs/agent.yaml`:
- Добавить секцию `available_models`
- Удалить секцию `prompt`
- Секции `llm` и `summarization` остаются (fallback для Langfuse)

**1.4 Seed file**

`configs/prompts/summarization.txt` — содержимое из текущего hardcoded промпта в `graph.py::_summarize()`:
```
Summarize the following conversation concisely. Preserve: key decisions, unresolved questions, current focus, important facts and context. Discard: redundant tool outputs, intermediate reasoning, greetings.
```

**1.5 EncryptionService**

`backend/app/services/encryption.py`:
- `EncryptionService` — Fernet wrapper с disabled mode
- `encrypt(plaintext: str) → bytes` — raises если disabled
- `decrypt(ciphertext: bytes) → str` — raises если disabled
- `is_available: bool` — property, True если key задан
- Конструктор: `(key: str)`. Если key пустой → disabled mode (не crash)
- Создаётся **всегда** в lifespan. Если key не задан → warning в логах, `is_available=False`
- API enforcement: `POST /mcp-servers` с `api_key` непустым + `is_available=False` → **400** «MCP_ENCRYPTION_KEY not configured, cannot store API keys»
- Серверы без `api_key` работают в любом случае

**1.6 URL Validator (SSRF protection — defense in depth)**

`backend/app/services/url_validator.py`:
- `validate_url(url: str) → None` (raises ValueError on private IP)
- DNS resolve → IP deny list: 127.0.0.0/8, 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 169.254.0.0/16, ::1, fc00::/7, fe80::/10
- **Двойная валидация (ADR-016):**
  1. **API-time:** при `POST/PUT /mcp-servers` — немедленная проверка URL
  2. **Connection-time:** в `MCPToolResolver.resolve()`, непосредственно перед созданием MCP connection — повторная проверка (защита от DNS rebinding: DNS-имя может сменить IP между валидацией и подключением)

---

### Phase 2: Track A — Langfuse Prompt Management + Model Switching

**2.1 PromptProvider**

`backend/app/infra/prompt_provider.py`:
- Infra-level компонент (аналог `infra/llm.py`, `infra/mcp.py`)
- `get_prompt(name: str) → str` — sync, использует Langfuse SDK кэш
- `get_config(name: str) → dict | None` ��� config из prompt
- Fallback: file из `configs/prompts/{name}.txt`
- Конструктор: `(langfuse: Langfuse | None, label: str, cache_ttl: int, prompts_dir: Path)`
- При Langfuse=None или fetch error → file fallback + warning в логах

Логика get_prompt:
```python
def get_prompt(self, name: str) -> str:
    if self._langfuse:
        try:
            prompt = self._langfuse.get_prompt(
                name, label=self._label, cache_ttl_seconds=self._cache_ttl,
                fallback=self._load_file(name),
            )
            self._prompt_cache[name] = prompt  # cache TextPromptClient for config access
            return prompt.compile()
        except Exception:
            logger.warning("prompt fetch failed, using file fallback", name=name)
    return self._load_file(name)
```

**2.2 Startup seed + file→Langfuse sync**

В `main.py` lifespan, после init_langfuse. Логика: seed (если Langfuse пуст) + push (если файл содержит версию, которой нет в Langfuse).

**Защита от дубликатов:** сравниваем файл со **всеми** версиями промпта, не только с latest. Без этого — edge case: файл v1 → push v1 → правка в UI → v2 → перезапуск → сравнение с v2 → отличается → push v1 как v3 (дубликат).

API: `langfuse.api.prompts.list(name=)` → `PromptMeta.versions: list[int]`, затем `get_prompt(name, version=N)` для каждой.

```python
if langfuse_enabled:
    langfuse = get_client()
    for prompt_name in ["system", "summarization"]:
        file_text = (prompts_dir / f"{prompt_name}.txt").read_text()
        file_config = _load_prompt_config(agent_config, prompt_name)
        file_hash = _content_hash(file_text, file_config)
        try:
            meta = langfuse.api.prompts.list(name=prompt_name)
            if not meta.data:
                # Промпт не существует → seed из файла
                langfuse.create_prompt(name=prompt_name, prompt=file_text,
                    labels=[settings.langfuse_prompt_label], config=file_config)
                continue

            all_versions = meta.data[0].versions  # [1, 2, 3, ...]
            is_duplicate = any(
                _content_hash(langfuse.get_prompt(prompt_name, version=v).prompt,
                              langfuse.get_prompt(prompt_name, version=v).config) == file_hash
                for v in all_versions
            )
            if not is_duplicate:
                # Файл содержит действительно новую версию → push
                langfuse.create_prompt(name=prompt_name, prompt=file_text,
                    labels=[settings.langfuse_prompt_label], config=file_config)
        except Exception:
            logger.warning("prompt seed/sync failed", name=prompt_name, exc_info=True)
```

`_load_prompt_config()`: для "system" → `{"model": agent_config.llm.model, "extra_body": agent_config.llm.extra_body}`, для "summarization" → `{"model": agent_config.summarization.model, "max_tokens": agent_config.summarization.max_summary_tokens}`.

`_content_hash(text, config)`: `hashlib.sha256((text + json.dumps(config, sort_keys=True)).encode()).hexdigest()`

**2.3 Sync script (Langfuse → files)**

`backend/scripts/sync_prompts.py`:
- `sync_to_files(label)`: Langfuse → `configs/prompts/{name}.txt` + обновить соответствующие секции agent.yaml
- Обратное направление (file → Langfuse) **не нужно как скрипт** — обрабатывается в lifespan (2.2)

`Makefile`:
- `make sync-prompts` → `uv run python backend/scripts/sync_prompts.py --label production`

**2.4 SettingsRepository**

`backend/app/repositories/settings.py`:
- Один generic repository для всех 3 таблиц
- `get_user_settings(user_id) → UserSettings | None`
- `get_project_settings(project_id) → ProjectSettings | None`
- `get_thread_settings(thread_id) → ThreadSettings | None`
- `upsert_user_settings(user_id, **kwargs) → UserSettings`
- `upsert_project_settings(project_id, **kwargs) → ProjectSettings`
- `upsert_thread_settings(thread_id, **kwargs) → ThreadSettings`
- Upsert через `INSERT ... ON CONFLICT DO UPDATE` или merge pattern

**2.5 ModelConfigResolver**

`backend/app/services/model_config_resolver.py`:
- Stateless resolver, injectable
- `resolve(user_id, project_id, thread_id) → ResolvedModelConfig`
- Cascade: thread → project → user → Langfuse prompt.config → agent.yaml
- Deps: `SettingsRepository`, `PromptProvider`, `LLMConfig` (file fallback)
- Три SELECT по indexed PK, затем merge в коде
- NULL / отсут��твие записи = inherit

**2.6 GraphFactory**

`backend/app/agent/graph_factory.py`:
- `GraphFactory` — per-request build+compile (ADR-014)
- Конструктор: settings, agent_config, global_tools, skills_index, checkpointer, store, prompt_provider
- `build(model_config: ResolvedModelConfig, extra_tools: list) → CompiledStateGraph`
- Внутри: `create_llm_from_config()` для main model, summarization model из PromptProvider config → agent.yaml fallback

`backend/app/infra/llm.py` — новые функции:
- `create_llm_from_config(settings, model_config: ResolvedModelConfig) → BaseChatModel`
- `create_summarization_llm_from_prompt_config(settings, config: dict) → BaseChatModel`

**2.7 Agent node refactoring**

`backend/app/agent/graph.py`:
- `build_graph()` — добавить параметр `prompt_provider`
- `agent_node` — из 84-строчной god function в ~25-строчный оркестратор
- Extracted functions:
  - `_reduce_context(messages, summarization_model, context_config, prompt_provider)` — compaction + trim
  - `_build_system_message(prompt_provider, runtime, skills_index, ...)` — KS + instructions + memory + prompt → SystemMessage
  - `_invoke_llm(bound_model, messages)` — ainvoke + timing + usage logging

`_reduce_context()`:
- Summarization prompt из `prompt_provider.get_prompt("summarization")`
- Fallback: если prompt_provider unavailable → hardcoded (текущее поведение)
- Compaction → trim → return (messages, context_ops)

`_build_system_message()`:
- Base prompt из `prompt_provider.get_prompt("system")`
- KS index из store (без изменений)
- Custom instructions из store (Track B) → `<custom_instructions>` блок
- User memory index из store (Track B) → `<user_memory>` блок
- Skills index (без изменений)

**2.8 AgentRunner refactoring**

`backend/app/agent/runner.py`:
- Конструктор: `checkpointer`, `graph_factory`, `model_resolver`, `tool_resolver` (вместо `graph`)
- `stream()`: resolve model + tools → graph_factory.build() → astream
- `get_history()`: `checkpointer.aget_tuple(config)` → extract from `checkpoint.channel_values["messages"]`
- `get_last_ai_message_id()`: аналогично через checkpointer
- Protocol в `services/agent_runner.py` — **без изменений**

**2.9 main.py — rewiring lifespan**

- `PromptProvider` init (langfuse client, settings)
- Startup seed (промпты в Langfuse)
- `GraphFactory` init (вместо прямого build_graph + compile_graph)
- `ModelConfigResolver` init
- `MCPToolResolver` init (Phase 4)
- `AgentRunner` получает checkpointer + factory + resolvers
- Удалить: `create_llm()`, `create_summarization_llm()`, `build_graph()`, `compile_graph()`
- `app.state.prompt_provider`, `app.state.checkpointer` — для DI в deps

**2.10 API — models + settings**

`backend/app/api/routes/models.py`:
- `GET /api/models` → `{"items": [{"name": "...", "display_name": "..."}]}`

`backend/app/api/routes/settings.py` — parametrized router:
- `GET /api/users/me/settings` → `SettingsResponse` (resolved model + raw overrides)
- `PUT /api/users/me/settings` → `SettingsResponse`
- `GET /api/projects/{pid}/settings` → `SettingsResponse`
- `PUT /api/projects/{pid}/settings` → `SettingsResponse`
- `GET /api/projects/{pid}/chats/{tid}/settings` → `SettingsResponse`
- `PUT /api/projects/{pid}/chats/{tid}/settings` → `SettingsResponse`

`backend/app/api/schemas/settings.py`:
```python
class SettingsUpdate(BaseModel):
    model_name: str | None = None   # null = inherit
    extra_body: dict | None = None

class SettingsResponse(BaseModel):
    model_name: str | None           # raw value (null = inherited)
    extra_body: dict | None
    resolved_model: str              # effective model after cascade
    resolved_source: str             # "thread"|"project"|"user"|"langfuse"|"config"

class ModelsListResponse(BaseModel):
    items: list[AvailableModelResponse]

class AvailableModelResponse(BaseModel):
    name: str
    display_name: str
```

Авторизация: user settings через `CurrentUser`, project/thread через `UserProject` + ownership check.
Валидация: `model_name` проверяется по whitelist из `agent.yaml.available_models`.

---

### Phase 3: Track B — Memory Architecture

**3.1 store_helpers.py — generic helper**

`backend/app/agent/tools/store_helpers.py`:
- `format_index(items, title, key_fn=lambda item: item.key) → str`
- Generic для KS и User Memory

**3.2 Refactor ks_helpers.py**

`backend/app/agent/tools/ks_helpers.py`:
- `format_index()` → import из `store_helpers.py`
- KS-специфичный вызов: `format_index(items, "Knowledge Sphere", key_fn=lambda i: i.key.removeprefix("section:"))`
- `build_namespace()`, `section_key()`, `fuzzy_find_and_replace()` — без изменений

**3.3 User memory tools**

`backend/app/agent/tools/user_memory.py`:
- `save_user_memory(key, description, content, runtime)` — write to `("user", uid, "memory")`
- `delete_user_memory(key, runtime)` — delete from `("user", uid, "memory")`
- Tools используют `runtime.store` и `runtime.context.user_id`

**3.4 prompt_builder.py — расширение**

- Добавить 2 параметра: `custom_instructions: str = ""`, `user_memory_index: str = ""`
- Template: +`<custom_instructions>` блок (conditional), +`<user_memory>` блок (conditional)
- Порядок в template: based_prompt → `<custom_instructions>` → `<user_memory>` → `<knowledge_sphere>` → `<available_skills>`

**3.5 agent_node — fetch instructions & memory**

В `_build_system_message()`:
```python
# Custom Instructions
instr_item = await store.aget(("user", user_id, "instructions"), "default")
custom_instructions = instr_item.value["content"] if instr_item else ""

# User Memory
mem_items = await store.asearch(("user", user_id, "memory"), limit=50)
user_memory_index = format_index(list(mem_items), title="User Memory")
```

**3.6 UserMemoryService**

`backend/app/services/user_memory.py`:
- Protocol + `LangGraphUserMemoryService(store)` implementation
- `get_instructions(user_id) → str`
- `update_instructions(user_id, content) → str`
- `list_memories(user_id) → list[MemoryItemData]`

**3.7 REST API — instructions + memories**

`backend/app/api/routes/user_memory.py`:
- `GET /api/users/me/instructions` → `InstructionsResponse`
- `PUT /api/users/me/instructions` → `InstructionsResponse`
- `GET /api/users/me/memories` → `MemoryListResponse`

`backend/app/api/schemas/user_memory.py`:
```python
class InstructionsResponse(BaseModel):
    content: str

class InstructionsUpdate(BaseModel):
    content: str  # max_length=5000

class MemoryItem(BaseModel):
    key: str
    description: str
    content: str                      # полное содержимое записи
    created_at: datetime

class MemoryListResponse(BaseModel):
    items: list[MemoryItem]
```

**3.8 Wiring Track B**

- `backend/app/main.py`: register user memory tools (`save_user_memory`, `delete_user_memory`) в `all_tools`, include `user_memory` router
- `backend/app/api/deps.py`: `get_user_memory_service(request) → UserMemoryService`, `UserMemoryServiceDep`
- `backend/app/api/routes/__init__.py`: import `user_memory`

**3.9 system.txt — guidelines**

Добавить `<user_memory_guidelines>` блок в `configs/prompts/system.txt`:
```
<user_memory_guidelines>
You have persistent cross-project memory. When you learn something notable about the user — preferences, expertise, work patterns, recurring needs — save it with save_user_memory.

Guidelines:
- Save: preferences, expertise areas, work style, recurring patterns, stated goals
- Do NOT save: temporary task context, sensitive data, single-use facts
- Update existing keys rather than creating duplicates
- Use descriptive keys (e.g., "prefers-bullet-points", "senior-go-dev")
- Keep entries concise — one concept per memory
- Max 50 entries. If near limit, consolidate related entries.
</user_memory_guidelines>
```

---

### Phase 4: Track C — User MCP Servers

**4.1 MCPServerRepository**

`backend/app/repositories/mcp_server.py`:
- Generic repo с typed methods per scope
- `list_by_user(user_id, active_only=True) → list[UserMCPServer]`
- `list_by_project(project_id, active_only=True) → list[ProjectMCPServer]`
- `list_by_thread(thread_id, active_only=True) → list[ThreadMCPServer]`
- `get_by_id(scope, id) → model | None`
- `create(scope, **data) → model`
- `update(model, **data) → model`
- `delete(model) → None`
- `count_by_scope(scope, scope_id) → int` (для лимита 5 per scope)

**4.2 MCPToolResolver**

`backend/app/services/mcp_tool_resolver.py`:
- `resolve(user_id, project_id, thread_id) → list[BaseTool]`
- Collect active servers: thread ∪ project ∪ user
- For each server:
  1. **Connection-time SSRF check:** `validate_url(server.url)` перед подключением (defense in depth, ADR-016)
  2. Decrypt API key → build `MultiServerMCPClient` connection (с `timeout` — см. ниже) → `await get_tools()`
  3. Tools standalone — захватывают connection config, клиент можно отпустить
- Dedup by tool name: thread > project > user
- Filter conflicts with global tools (global wins)
- **Resource limits (ADR-016):**
  - **Max 20 tools total** от user MCP серверов: после additive merge, если `len(user_tools) > 20` → truncate до 20 + warning в логах (предотвращает prompt bloat)
  - **30s timeout per tool call:** при создании connection dict → `timeout=30` в `StreamableHttpConnection` / `sse_read_timeout=30` в `SSEConnection` (оба поддерживают, подтверждено API Verification)
- TTL cache (5 min), key = hash of scope IDs. Кэшируются tools (не клиенты)
- `invalidate(scope_type, scope_id)` — вызывается при CRUD

**4.3 REST API — MCP servers**

`backend/app/api/routes/mcp_servers.py` — parametrized router:

User level:
- `GET    /api/users/me/mcp-servers` → list
- `POST   /api/users/me/mcp-servers` → create (201)
- `PUT    /api/users/me/mcp-servers/{id}` → update
- `DELETE /api/users/me/mcp-servers/{id}` → 204
- `POST   /api/users/me/mcp-servers/{id}/test` → test connection

Project level:
- `GET/POST/PUT/DELETE /api/projects/{pid}/mcp-servers[/{id}]`
- `POST /api/projects/{pid}/mcp-servers/{id}/test`

Thread level:
- `GET/POST/PUT/DELETE /api/projects/{pid}/chats/{tid}/mcp-servers[/{id}]`
- `POST /api/projects/{pid}/chats/{tid}/mcp-servers/{id}/test`

`backend/app/api/schemas/mcp_servers.py`:
```python
class MCPServerCreate(BaseModel):
    name: str                           # max_length=100
    transport: Literal["http", "sse"]
    url: HttpUrl
    api_key: str | None = None
    allowed_tools: list[str] = []       # в DB/API, скрыто в UI

class MCPServerUpdate(BaseModel):
    name: str | None = None
    transport: Literal["http", "sse"] | None = None
    url: HttpUrl | None = None
    api_key: str | None = None          # "" = remove, non-empty = update, absent = keep
    allowed_tools: list[str] | None = None
    is_active: bool | None = None

class MCPServerResponse(BaseModel):
    id: UUID
    name: str
    transport: str
    url: str
    has_api_key: bool
    allowed_tools: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime

class MCPServerListResponse(BaseModel):
    items: list[MCPServerResponse]

class TestConnectionResponse(BaseModel):
    success: bool
    tools: list[str] = []
    error: str | None = None
```

Валидация:
- Transport: только "http" или "sse" (stdio → 400)
- URL: SSRF protection ч��рез `validate_url()`
- Лим��т: max 5 серверов per scope → 400
- API key: Fernet encrypt при записи, decrypt при чтении

Авторизация: user → CurrentUser, project → UserProject, thread → UserProject + thread ownership check (паттерн из `messages.py`).

**4.4 Wiring Track C**

- `backend/app/main.py`: `EncryptionService` init (всегда, с disabled mode если key не задан), `MCPToolResolver` init, include `mcp_servers` router
- `backend/app/api/deps.py`: `get_encryption_service()`, `get_mcp_server_repo()`, `MCPServerRepoDep`, `EncryptionServiceDep`

---

### Phase 5: Frontend

**5.1 Types + API client**

`frontend/src/shared/api/types.ts` — добавить:
```typescript
// Settings (Track A)
interface AvailableModel { name: string; display_name: string; }
interface Settings { model_name: string | null; extra_body: object | null; resolved_model: string; resolved_source: string; }
interface SettingsUpdate { model_name: string | null; extra_body?: object | null; }

// User Memory (Track B)
interface Instructions { content: string; }
interface MemoryItem { key: string; description: string; content: string; created_at: string; }

// MCP Servers (Track C)
interface MCPServer { id: string; name: string; transport: string; url: string; has_api_key: boolean; is_active: boolean; created_at: string; updated_at: string; }
interface MCPServerCreate { name: string; transport: "http" | "sse"; url: string; api_key?: string; }
interface MCPServerUpdate { name?: string; transport?: "http" | "sse"; url?: string; api_key?: string; is_active?: boolean; }
interface TestConnectionResult { success: boolean; tools: string[]; error?: string; }
```

`frontend/src/shared/api/models.ts` — `getModels()`
`frontend/src/shared/api/settings.ts` — `getSettings(scope, id?)`, `updateSettings(scope, id?, data)`
`frontend/src/shared/api/user-memory.ts` — `getInstructions()`, `updateInstructions(data)`, `getMemories()`
`frontend/src/shared/api/mcp-servers.ts` — CRUD + test для всех scope

**5.2 Route: /settings**

`frontend/src/app/router.tsx` — добавить:
```tsx
<Route path="settings" element={<SettingsPage />} />
```

Внутри `<Route element={<AppLayout />}>`, рядом �� index и projects.

**5.3 Settings Page (user-level)**

`frontend/src/features/settings/`:
```
components/
  SettingsPage.tsx          — layout: Model + Instructions + Memory + MCP Servers
  ModelSection.tsx           — dropdown выбора дефолтной модели
  CustomInstructionsSection.tsx — textarea + save button
  AgentMemorySection.tsx    — read-only список
  MCPServersSection.tsx     — list + add/edit/delete/test
  MCPServerForm.tsx         — dialog для add/edit
hooks/
  useModels.ts              — GET /api/models (query)
  useSettings.ts            — GET settings (query, parametrized by scope)
  useUpdateSettings.ts      — PUT settings (mutation, parametrized)
  useInstructions.ts        — GET instructions
  useUpdateInstructions.ts  — PUT instructions (mutation)
  useMemories.ts            — GET memories
  useMCPServers.ts          — GET mcp-servers (parametrized by scope)
  useMCPServerMutations.ts  — create/update/delete/test (mutations)
```

**5.4 Sidebar — Settings icon**

`frontend/src/app/components/Sidebar.tsx`:
- Добавить иконку ⚙ (Settings из lucide-react) рядом с username в user footer
- Клик → navigate("/settings")

**5.5 Project Settings tab**

`frontend/src/app/layouts/ProjectLayout.tsx`:
- Добавить NavLink "Settings" в nav tabs

`frontend/src/app/router.tsx`:
- Добавить `<Route path="settings" element={<ProjectSettingsPage />} />` внутри project routes

`frontend/src/features/settings/components/ProjectSettingsPage.tsx`:
- Model override (dropdown с опцией "Inherit from user")
- MCP Servers (project-level) — тот же `MCPServersSection` с scope="project"

**5.6 Chat View — model selector + tools panel**

`frontend/src/features/chat/components/ChatView.tsx`:
- Добавить header: `<ChatHeader>` между loading check и MessageList
- `ChatHeader` содержит: chat title (опционально) + model selector (слева сверху) + tools button

`frontend/src/features/chat/components/ChatHeader.tsx`:
- Model selector dropdown (слева): текущая модель, выбор из whitelist, опция "Inherit"
- Tools button (справа): открывает ChatToolsPanel

`frontend/src/features/chat/components/ModelSelector.tsx`:
- Shared component (используется в /settings, project settings, chat header)
- Props: `scope`, `scopeId`, `onModelChange`
- Показывает resolved model + source

`frontend/src/features/chat/components/ChatToolsPanel.tsx`:
- Slide-over или modal panel
- Shows: global tools (read-only list), user tools (from /settings), project tools, chat tools
- Chat-level: add/edit/delete MCP servers
- Reuses `MCPServersSection` с scope="thread"

**5.7 TanStack Query keys**

```
["models"]                                    — available models
["settings", "user"]                          — user settings
["settings", "project", pid]                  — project settings
["settings", "thread", tid]                   — thread settings
["instructions"]                              — custom instructions
["memories"]                                  — user memories
["mcp-servers", "user"]                       — user MCP servers
["mcp-servers", "project", pid]               — project MCP servers
["mcp-servers", "thread", tid]                — thread MCP servers
```

Invalidation: PUT settings → invalidate `["settings", scope, id]`. MCP CRUD → invalidate `["mcp-servers", scope, id]`.

---

### Phase 6: Final Integration & env

> **Примечание:** wiring каждого трека (роутеры, deps, main.py) выполняется в конце соответствующей фазы (2.9 для Track A, 3.8 для Track B, 4.4 для Track C). Phase 6 — финальная ревизия и smoke test.

**6.1 main.py — финальная ревизия**

Проверить что все компоненты зарегистрированы:
- PromptProvider, GraphFactory, ModelConfigResolver (Phase 2.9)
- User memory tools + router (Phase 3.8)
- EncryptionService, MCPToolResolver, mcp_servers router (Phase 4.4)
- Models router, settings router (Phase 2.10)
- `app.state.checkpointer`, `app.state.prompt_provider` для deps

**6.2 .env / .env.example updates**

```
LANGFUSE_PROMPT_LABEL=production
LANGFUSE_PROMPT_CACHE_TTL=60
MCP_ENCRYPTION_KEY=          # generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

`.env.local.example`:
```
LANGFUSE_PROMPT_LABEL=development
```

---

### Phase 7: Documentation Updates

- `doc/tech/agent-runtime.md` — обновить Architecture Overview, System Message (новые слоты), Tools (user memory tools), MCP Integration (per-user), Configuration (GraphFactory, PromptProvider)
- `doc/tech/backend.md` — API endpoints (settings, models, user-memory, mcp-servers), Persistence (новые таблицы), Module Structure
- `doc/tech/frontend.md` — Routes (/settings), Features (settings), Components (ChatHeader, ModelSelector), State Management (новые query keys), API modules
- `doc/tech/observability.md` — если есть изменения �� tracing (model name в trace)
- `doc/index.md` — если добавлены новые документы

---

## Verification

Детальные тестовые кейсы: [test-cases.md](doc/tasks/iterations/post-mvp/feat-003-agent-config/test-cases.md)

4 слоя: Automated (gate) → API (endpoints) → Integration (компоненты вместе) → E2E (UI flows, 9 сценариев).

### Процесс верификации

1. **Агент-реализатор** завершает реализацию, фиксирует в summary.md
2. **Агент-evaluator** (отдельный) совместно с архитектором проходит test-cases.md:
   - Поднимает инфраструктуру (`make docker-up-db`, `make migrate`, `make dev`, `make dev-fe`)
   - Проходит кейсы последовательно по слоям (Layer 0 → 1 → 2 → 3)
   - Каждый кейс отмечается сразу: `- [x]` + результат или `- [ ] ⚠️` + причина
   - Кейсы, требующие UI/браузер — эскалация архитектору
3. Непройденные кейсы → обратная связь агенту-реализатору → доработка → повторная проверка
4. Все кейсы пройдены → коммит + пуш

### DoD Checklist (из tasklist)

**Track A:**
- [ ] PromptProvider фетчит промпты из Langfuse; fallback → file + warning
- [ ] Startup seed: на пустом Langfuse промпты создаются из файлов с label production
- [ ] Model override каскад: thread → project → user → Langfuse → agent.yaml
- [ ] GET /api/models — whitelist из agent.yaml
- [ ] PUT model на уровне user/project/thread
- [ ] Смена модели через UI → следующее сообщение обрабатывается выбранной моделью
- [ ] GraphFactory: per-request build+compile
- [ ] agent_node: оркестратор + extracted functions

**Track B:**
- [ ] PUT /api/users/me/instructions → text в system message `<custom_instructions>`
- [ ] GET /api/users/me/memories — записи, созданные агентом
- [ ] Агент использует save_user_memory / delete_user_memory
- [ ] Settings page: textarea instructions + read-only memories
- [ ] store_helpers.format_index() — generic, shared KS + User Memory

**Track C:**
- [ ] CRUD для user/project/thread MCP серверов; POST .../test
- [ ] Additive merge: thread ∪ project ∪ user ∪ global
- [ ] SSRF: private IP → 400
- [ ] stdio → 400; API key encrypted, response: has_api_key bool
- [ ] Graceful degradation: user MCP fail → global tools + warning

**Cross-cutting:**
- [ ] make check + make check-fe
- [ ] Миграции на чистой БД
- [ ] E2E: instructions → model switch → message → agent follows, Langfuse trace correct

---

## Implementation Order (recommended)

```
Phase 1 (Foundation)
  ↓
Phase 2 (Track A + wiring 2.9-2.10)
  ↓
Phase 3 (Track B + wiring 3.8)
  ↓
Phase 4 (Track C + wiring 4.4)
  ↓
Phase 5 (Frontend — all tracks, один проход)
  ↓
Phase 6 (Final integration + env — ревизия, smoke test)
  ↓
Phase 7 (Documentation)
```

Track A — фундамент (GraphFactory, PromptProvider, AgentRunner refactoring). Track B и C зависят от инфраструктуры Track A. Wiring (роутеры, deps, main.py) выполняется в конце каждой фазы, не откладывается. Frontend реализуется после backend всех треков — один проход по UI.

---

## Final Step

Дождаться ревью и обратной связи от архитекто��а перед коммитом и пушем.
