# Post-Implementation Summary: feat-003 — Runtime Agent Configuration

## Результат

Реализованы все три трека runtime-конфигурации агента:

- **Track A** — Langfuse Prompt Management + Model Switching: per-request model resolution с каскадом thread → project → user → Langfuse → agent.yaml, GraphFactory для per-request build+compile, PromptProvider с Langfuse SDK cache + file fallback
- **Track B** — Memory Architecture: custom instructions в system message, agent-managed user memory через LangGraph Store tools, DELETE endpoint для memories
- **Track C** — User MCP Servers: per-scope CRUD (user/project/thread) с SSRF protection, Fernet encryption, MCPToolResolver с additive merge + targeted cache invalidation, cascade visibility с toggle (mcp_server_disables table), api_key_hint для безопасного отображения

## Отклонения от плана

### Архитектурные адаптации

| Решение в плане | Фактическая реализация | Причина |
|----------------|----------------------|--------|
| `SettingsMixin` / `MCPServerMixin` | Typed models без mixins | Explicit > implicit для 3 таблиц; mypy лучше резолвит typed columns |
| Generic `get_by_id(scope, id)` в MCPServerRepository | Typed methods: `get_user_server()`, `get_project_server()`, `get_thread_server()` | Устранение union type issues в mypy |
| agent_node ~25 строк | agent_node ~70 строк | Inline orchestration читаемее при текущем количестве шагов |
| md5 cache key в MCPToolResolver | Tuple `(user_id, project_id, thread_id)` | md5 делал невозможной targeted invalidation; tuple позволяет фильтровать по позиции scope |
| ChatToolsPanel (slide-over) | Dialog с MCPServersSection | Dialog из shadcn/ui уже доступен; slide-over требовал новый компонент |

### Дополнения (не в исходном плане)

Эти компоненты появились по результатам верификации (test-cases.md, 14 findings):

| Компонент | Причина |
|-----------|--------|
| `mcp_server_disables` table + repo + toggle endpoints | FIX-8: cascade visibility — inherited servers с возможностью отключения на дочернем уровне |
| `api_key_hint` column (VARCHAR(20)) на 3 MCP таблицах | FIX-6: безопасное отображение ключа (первые/последние 4 символа) вместо binary has/no |
| `DELETE /api/users/me/memories/{key}` endpoint | FIX-7: пользователь может удалять записи памяти агента |
| Prompt naming `{name}--{label}` | FIX-11: полная изоляция dev/prod промптов (evaluator) |
| `MCPServerConfig.enabled` field | FIX-13: explicit management серверов без комментирования YAML |
| shadcn/ui Select + Switch components | FIX-5/FIX-8: замена нативных элементов |

### Дефолт `LANGFUSE_PROMPT_LABEL`

Изменён с `"production"` на `"development"` (FIX-2). Fail-safe: при забытой env-переменной промпт попадёт в development, а не в production.

## Верификация

Детальные результаты: [test-cases.md](test-cases.md)

| Layer | Всего | Pass | Deferred |
|-------|-------|------|----------|
| L0: Automated | 3 | 3 | 0 |
| L1: API Tests | 40 | 40 | 0 |
| L2: Integration | 18 | 12 | 6 |
| L3: E2E UI | 40 | 40 | 0 |
| **Итого** | **101** | **95** | **6** |

14 findings обнаружено и исправлено (1 HIGH, 4 MEDIUM, 9 LOW). Подробности в test-cases.md.

6 deferred кейсов — edge cases, требующие специальной инфраструктуры (DNS rebinding, 5+ MCP серверов, Langfuse downtime). Не влияют на основные пользовательские сценарии.

## Миграции

1. `4c786a9bcae6` — 6 таблиц: user/project/thread_settings + user/project/thread_mcp_servers
2. `2902408bdfd5` — api_key_hint (3 columns) + mcp_server_disables table

## Quality Gates

- `make check`: 91 files, 0 errors (ruff + mypy)
- `make check-fe`: 0 errors (tsc + ESLint + Prettier)
