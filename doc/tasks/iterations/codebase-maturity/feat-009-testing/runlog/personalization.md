# S7 — Memory · settings · MCP · models · run-log

Скоуп S7 (широкое покрытие: happy + основные ошибки/авторизация). Автор тестов
независим от автора прод-кода. Возобновление после падения прошлого прогона:
`conftest.py`, `test_model_config_resolver.py`, `test_url_validator.py` уже лежали
дописанными и годными — осмотрены, сверены с прод-кодом, оставлены; остальное
достроено до зелёного и типобезопасности. С нуля ничего не переписывалось.

## Файлы (всё в `backend/tests/personalization/`)
- `conftest.py` — локальные фикстуры `configured_app` (наполняет `app.state`
  реальными-но-лёгкими коллабораторами: `ModelConfigResolver` поверх stub
  prompt-provider, `EncryptionService` с одноразовым Fernet-ключом, in-memory
  LangGraph store, `SpyToolResolver`, `agent_config` с двумя моделями) и
  `api_client` (authed клиент поверх enriched app). Lifespan под `ASGITransport`
  не поднимается, прод-провайдеры читают `app.state` — поэтому швы
  handler → service → repo/store гоняются по-настоящему.
- `test_model_config_resolver.py` — каскад `resolve` (sociable-unit, fake
  settings-repo).
- `test_url_validator.py` — SSRF-валидатор (solitary-unit, stub `getaddrinfo`).
- `test_user_memory_service.py` — `LangGraphUserMemoryService` (sociable поверх
  реального in-memory store + `StubGuard`).
- `test_user_memory_tools.py` — agent-tools `save/delete_user_memory` (поведение
  на real store + duck-typed `ToolRuntime`).
- `test_skills.py` — `make_load_skill_tool` / `scan_skills_index` /
  frontmatter-парсер (solitary, дерево скиллов под `tmp_path`).
- `test_mcp_server_service.py` — чистые хелперы (`extract_schema_text`,
  `serialize_mcp_meta_blob`) + `McpServerService` (sociable: fake-repo,
  `StubGuard`, реальный `EncryptionService`, сетевой шов monkeypatched).
- `test_mcp_tool_resolver.py` — `MCPToolResolver`: кэш/инвалидация/деградация +
  логика слияния (fake-repo + fake session_factory + подменённый `_fetch_tools`).
- `test_settings_repository.py` — `SettingsRepository` (integration, real PG).
- `test_mcp_server_repository.py` — `MCPServerRepository` (integration, real PG).
- `test_settings_routes.py`, `test_models_route.py`, `test_user_memory_routes.py`,
  `test_mcp_routes.py` — REST через `api_client`.

## Покрытые поведения
- **model_config_resolver**: каскад thread→project→user→langfuse→config (каждый
  уровень выигрывает); строка без `model_name` пропускается; `default()`; resolve
  без project/thread.
- **url_validator (SSRF)**: приватные диапазоны v4/v6 (parametrize:
  127/10/172.16/192.168/169.254/::1/fc00/fe80) → 422; публичные IP → пропуск;
  rebinding-форма (public+private) fail-closed; нет hostname → 400; нерезолвимый
  → 400.
- **user_memory service**: пустые инструкции → ""; round-trip update→get;
  изоляция по user; CLEAN/SUSPICIOUS проходят, INJECTION → 422 и НЕ пишет; list
  пустой/с элементами; delete.
- **user_memory tools**: save пишет под namespace юзера; delete удаляет; без
  store → RuntimeError; без context → RuntimeError.
- **skills**: load существующего → контент; неизвестный → "not found" + список;
  невалидные имена (parametrize: traversal/пробел/слэш/upper/точка) отбиты до
  чтения; index собирает name+нормализованное описание; dirs без frontmatter
  пропускаются; отсутствующая папка → "".
- **mcp_server service**: extract_schema_text берёт текстовые поля, отбрасывает
  типы; serialize_mcp_meta_blob содержит метаданные+tools; guard_and_persist:
  CLEAN→persist, INJECTION→блок (не пишет), unreachable→503, api_key
  шифруется+hint, без encryption→503; update: api_key-only без ревалидации
  (guard не опрошен), смена url→ревалидация (guard опрошен), INJECTION на смене
  url→блок.
- **mcp_tool_resolver**: кэш в пределах TTL; invalidate матчящего scope → пересчёт;
  invalidate неизвестного scope → no-op; деградация в `[]` при сбое; merge —
  dedup с приоритетом thread, исключение global-tools, пропуск disabled, обрезка
  до MAX_USER_TOOLS.
- **settings repo (PG)**: absent→None; upsert user create+read+update (одна
  строка); project/thread round-trip.
- **mcp_server repo (PG)**: create+get; missing→None; list active_only фильтрует;
  count_by_scope; disables set/list/idempotent/remove; cleanup_for_server по всем
  scope'ам.
- **REST settings**: GET без override → config-источник; PUT валидной модели →
  user-источник + персист; PUT модели вне allowlist → 422; PUT `model_name=null`
  → 200 (clear не триггерит allowlist).
- **REST models**: список доступных моделей; пагинация (срез + полный total).
- **REST user_memory**: GET инструкций пусто; PUT→GET round-trip; INJECTION→422 +
  не пишет; list пусто/seeded; delete→204.
- **REST mcp**: список пуст; update/delete несуществующего → 404 (ownership);
  переполнение scope (5 серверов) → 409; create→201 + персист + invalidation
  кэша; project-список пуст; чужой проект → 404 (ownership-dep).

## Дубли / инфра
- Postgres — только под repository-integration и под REST-хендлерами (поверх
  репозиториев), на транзакционном откате из замороженного backend harness.
  Логика сервисов — на fake-репозиториях / реальном in-memory store. Guard —
  `StubGuard` из `packages/testing` (фиксированный вердикт; тестируем реакцию
  кода, не качество). Сетевой шов MCP (`fetch_remote_metadata`, `validate_url`,
  `_fetch_tools`) — monkeypatch, тесты офлайн и детерминированы. Шифрование —
  настоящий `EncryptionService` (in-process, не болезненная граница). Внешних
  эффектов с mock-ожиданием нет (SpyToolResolver лишь записывает invalidate —
  проверяем сам факт инвалидации как контракт роута).

## Результат верификации
- `make test-scope P=backend/tests/personalization` — **98 passed**.
- `ruff check` / `ruff format --check` tests/personalization — clean.
- `mypy backend/tests/personalization/` (root config, как гейт) — clean.

## Точечные правки типобезопасности (только тест-файлы скоупа, прод не тронут)
- `PromptProvider` / `SecurityGuard` / `SettingsRepository` / `MCPServerRepository`
  — конкретные классы, не Protocol; duck-typed фейки → `cast(...)` в местах
  передачи (`conftest.py`, `test_model_config_resolver.py`,
  `test_user_memory_service.py`, `test_mcp_server_service.py`). Паттерн cast для
  тест-дублей — как в scope sphere/projects/security.
- Pydantic-плагин строгий (`init_typed`/`init_forbid_extra`): прямой
  `MCPServerCreate(url="…")` / `MCPServerUpdate(url="…")` не проходит (str vs
  `HttpUrl`, мнимо-required `name`). Конструируем через `model_validate({...})` —
  та же коэрция, что в HTTP-слое.
- `@tool` возвращает `BaseTool` без типизированного `.coroutine`; инъектируемый
  `runtime` исключён из публичной схемы (через `.ainvoke` не передать) → cast к
  `StructuredTool` + хелпер `_call`, гоняющий `.coroutine` напрямую. `ToolRuntime`
  здесь — duck-typed `cast(ToolRuntime, SimpleNamespace(store=…, context=…))`:
  tools читают только `.store`/`.context`, конструктор generic-dataclass обходим.

## Баги для Ф5
- Нет. Прод-код S7 ведёт себя по контракту; обходов/правок прода не потребовалось.

## Непокрытое и почему
- `url_validator` НЕ проверяет схему URL и НЕ следует редиректам — таких веток в
  прод-коде нет (валидатор делает только DNS-резолв + проверку приватных
  диапазонов). Поэтому «отказ по схеме»/«SSRF через редирект» не тестируются:
  тестировать нечего, поведение отсутствует. Если защита по схеме/редиректам —
  требование, это вопрос к прод-коду (не баг текущего контракта). SSRF-глубина
  даётся через приватные диапазоны и DNS-rebinding-форму.
- `_test_connection` / `fetch_remote_metadata` / `_fetch_tools` (реальный вызов
  `MultiServerMCPClient`) не гоняются против живого MCP — это сеть/внешний
  сервис; покрыт код вокруг (валидация, маппинг ошибок в 503, guard, сборка
  блоба), сам wire — вне unit-гейта.
- thread-scope MCP-роуты (`/chats/{id}/mcp-servers`) точечно не покрыты REST'ом —
  идентичны user/project-веткам (тот же сервис/репо), покрытым выше; user+project
  REST + repo-integration по всем scope'ам дают широту. Риск низкий.
- Реальный Postgres-backed agent store не гоняется (testing.md: логику — на
  in-memory; PG-store — узкий integration вне этого скоупа).
- Конкурентных запросов в одном тесте нет (ограничение одной сессии харнесса,
  F2 в infra.md).

## Блокеры
- Нет. Замороженную инфру (`packages/testing`, общий backend `conftest.py`,
  Makefile, pyproject, прод-код) не трогал.
