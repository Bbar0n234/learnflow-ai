# ADR-016: Per-Scope MCP Servers

## Статус

Принято

## Контекст

feat-003 Track C вводит per-user MCP серверы — пользователи подключают свои внешние инструменты через MCP. Серверы конфигурируются на трёх уровнях (user, project, thread), аналогично model settings (ADR-013).

Вопросы, требующие решения:
- **Storage:** где хранить конфигурации серверов (PostgreSQL vs LangGraph Store)
- **Encryption:** как защищать user-provided API keys
- **Merge strategy:** как объединять серверы с разных уровней
- **Transport:** какие MCP транспорты разрешены для user-provided серверов
- **Security:** защита от SSRF через user-provided URLs

## Рассмотренные варианты

### Storage

#### A: LangGraph Store

Хранить MCP конфигурации в Store namespaces `("user", uid, "mcp_servers")`.

- **За:** уже используется для KS и user memory; единая инфраструктура.
- **Против:** нет field-level encryption; нет FK constraints (orphaned records при удалении пользователя); нет structured queries (count, unique validation); Store — для агентных данных, не для инфраструктурной конфигурации.

#### B: JSONB в settings таблицах

Колонка `mcp_servers JSONB` в `user_settings` / `project_settings` / `thread_settings`.

- **За:** минимум таблиц (0 новых).
- **Против:** encrypted API keys в JSONB (base64 внутри JSON array — awkward); нет per-server UNIQUE constraint; CRUD одного сервера = read-modify-write всего JSONB; нет per-server ID для REST API.

#### C: Typed таблицы с FK

`user_mcp_servers`, `project_mcp_servers`, `thread_mcp_servers` — каждая с FK CASCADE на parent.

- **За:** proper FK CASCADE; typed columns; per-server UNIQUE(scope_id, name); BYTEA для encrypted keys; standard CRUD; per-server ID для REST API.
- **Против:** три таблицы.

### Encryption

#### Fernet (symmetric, `cryptography` package)

- AES-128-CBC + HMAC-SHA256, URL-safe base64
- Ключ из env var `MCP_ENCRYPTION_KEY`
- Encrypt при записи, decrypt при чтении
- Достаточно для нашего масштаба; rotation не требуется

#### KMS / Vault

- Overkill для single-instance deployment с малым числом пользователей

### Merge strategy

#### Override (first non-NULL wins)

Как model settings: thread → project → user, первый не-NULL побеждает.

- **Против:** MCP серверы — не scalar override, а коллекция. "Один побеждает" не имеет смысла.

#### Additive (union)

Объединение: thread ∪ project ∪ user ∪ global. При конфликте tool names — более специфичный уровень побеждает.

- **За:** естественная семантика: пользователь добавляет серверы на разных уровнях, все доступны.

## Решение

- **Storage:** Вариант C — три typed таблицы с FK CASCADE.
- **Encryption:** Fernet. Ключ из env var. BYTEA column.
- **Merge:** Additive. thread ∪ project ∪ user ∪ global. Dedup по tool name: thread > project > user > global.
- **Transport:** только `http` (streamable_http) и `sse`. Stdio запрещён (subprocess от user-provided config = RCE вектор).
- **Security:** SSRF protection — DNS resolve + IP deny list (private/loopback/link-local/reserved) при добавлении сервера и при подключении (defense in depth vs DNS rebinding).

## Обоснование

- **Typed tables (не Store, не JSONB):** MCP конфигурации содержат encrypted API keys, нуждаются в FK CASCADE, per-server UNIQUE constraints и individual CRUD. Это инфраструктурная конфигурация, не агентные данные.
- **Fernet:** production-ready symmetric encryption из `cryptography` package. Достаточен для нашего масштаба. API никогда не возвращает ключ — только `has_api_key: bool`.
- **Additive merge:** серверы на разных уровнях дополняют друг друга. Пользователь может иметь глобальные tools (user level), project-specific tools, и per-chat tools одновременно. Global tools (из agent.yaml) всегда имеют приоритет — user tools не могут их переопределить.
- **Stdio banned:** stdio transport запускает subprocess с user-provided command — прямой вектор RCE. HTTP-based транспорты безопасны при SSRF protection.

## Следствия

- Одна Alembic-миграция создаёт три таблицы. SQLAlchemy mixin `MCPServerMixin` для общих колонок.
- Один generic `MCPServerRepository` с typed методами per scope.
- `MCPToolResolver` — новый компонент: additive merge + TTL cache (5 min) + dedup.
- `EncryptionService` — новый инфра-компонент: Fernet encrypt/decrypt, inject через DI.
- SSRF validation при API create/update и при подключении к серверу.
- REST API: один параметризованный router, три точки монтирования (user/project/thread).
- Limits: max 5 серверов per scope, max 20 user tools total, 30s timeout per tool call.
