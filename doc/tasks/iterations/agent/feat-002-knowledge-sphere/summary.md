# Post-Implementation Summary: agent/feat-002 — Knowledge Sphere

## Результат

Реализовано полностью. Долгосрочная память проекта через LangGraph Store: CRUD-tools для секций, auto-derived Index в system message, fuzzy patch, LangGraphSphereService для REST API.

## Отклонения от плана

### Tool set

План: `get_section`, `create_section`, `update_section`, `delete_section`. Реализовано 1-в-1, отклонений нет.

### StubSphereService

План: "оставить как fallback, не удалять". По решению архитектора при ревью — **удалён**. Обоснование: мёртвый код, `deps.py` использует `LangGraphSphereService`, для тестов достаточно mock/fixture через `SphereService` Protocol.

### Assert → RuntimeError

В `agent_node` для проверки `runtime.store is not None` изначально использовался `assert`. По решению архитектора заменён на explicit `raise RuntimeError(...)` — production-стиль с понятным сообщением об ошибке.

### Mypy-совместимость ToolRuntime

`ToolRuntime.store` и `ToolRuntime.context` типизированы как `Optional`. Для mypy-совместимости добавлены helper-функции `_store()` и `_ns()` в `knowledge_sphere.py` с assert-проверками внутри. Не влияет на публичный API.

### fuzzysearch mypy override

Библиотека не имеет type stubs. Добавлен `[[tool.mypy.overrides]]` для модуля `fuzzysearch` в `pyproject.toml` (аналогично `pdfkit`, `mdx_math`).

### update_section: keyword-only runtime

Ruff B008 запрещает вызовы функций в default-значениях аргументов. `runtime: ToolRuntime` вынесен за `*` separator как keyword-only параметр без default. ToolNode инжектит runtime корректно.

## Верификация

E2E верификация через curl (9 кейсов):

| Кейс | Статус |
|------|--------|
| Старт сервера (health, Store setup) | ✅ |
| Пустой шар (`GET /sphere` → `content: ""`) | ✅ |
| REST PUT → GET roundtrip (2 секции) | ✅ |
| Агент видит KS Index + `get_section` | ✅ |
| Агент создаёт секцию (`create_section`) | ✅ |
| Агент обновляет секцию overwrite | ✅ |
| Агент обновляет секцию fuzzy patch (target) | ✅ |
| Агент удаляет секцию (`delete_section`) | ✅ |
| REST PUT перезаписывает шар + агент видит новый Index | ✅ |

`make check` (ruff check + ruff format + mypy) — чисто.

### Замечание из логов

Pydantic serialization warning при checkpointing: `PydanticSerializationUnexpectedValue` для `AgentContext`. Функционально не влияет, косметический fix — при необходимости в будущих итерациях.

## Актуализация документации

- `doc/tech/backend.md` — обновлена секция Tools/Internal (CRUD вместо `get_sphere_index`/`update_sphere`, описание fuzzy patch) и Context Engineering (auto-derived Index).
- Остальная документация (ADR-003, ADR-004, ADR-005) не требует изменений — реализация соответствует архитектуре.

## Артефакты

### Новые файлы

- `backend/app/agent/tools/ks_helpers.py` — namespace builders, `fuzzy_find_and_replace`, `format_index`
- `backend/app/agent/tools/knowledge_sphere.py` — `get_section`, `create_section`, `update_section`, `delete_section`

### Изменённые файлы

- `backend/pyproject.toml` — `fuzzysearch>=0.8.0`
- `pyproject.toml` — mypy override для `fuzzysearch`
- `backend/app/agent/tools/__init__.py` — экспорт `ks_tools`
- `backend/app/agent/graph.py` — KS Index injection в agent_node, explicit RuntimeError
- `backend/app/main.py` — `app.state.store`, `ks_tools` в `build_graph`
- `backend/app/services/sphere.py` — `LangGraphSphereService`, удалён `StubSphereService`
- `backend/app/services/__init__.py` — экспорт `LangGraphSphereService`, убран `StubSphereService`
- `backend/app/api/deps.py` — `LangGraphSphereService` wiring
- `doc/tech/backend.md` — секции Tools и Context Engineering
