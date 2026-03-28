# Implementation Plan: agent/feat-002 — Knowledge Sphere

## Context

Итерация `agent/feat-002` — долгосрочная память проекта через LangGraph Store. Агент видит Index шара при каждом запросе (pre-loaded в system message), подгружает полные секции по необходимости (JIT через tool), обновляет шар сам через tools.

**Blocked by:** `agent/feat-001` — **снят** (✅ Done).

## Референсы

- **Таск-лист:** `doc/tasks/tasklist-agent.md` (feat-002)
- **Workflow:** `doc/workflow.md`
- **Conventions:** `doc/tech/conventions.md`
- **Архитектура:** `doc/tech/backend.md` (Agent Runtime — Memory, Tools, Context Engineering; Persistence — Store; API — Knowledge Sphere endpoints)
- **ADR-003:** `doc/tech/adr/ADR-003-knowledge-sphere.md` (Knowledge Sphere — связанная картина, structured Markdown, LangGraph Store)
- **ADR-004:** `doc/tech/adr/ADR-004-progressive-disclosure.md` (Index + Full sections, pre-loaded vs JIT)
- **ADR-005:** `doc/tech/adr/ADR-005-ks-update-mechanism.md` (Main Agent обновляет сам через tool)
- **LangGraph Reference:** `doc/tech/langgraph-reference.md` (Store API, InjectedStore, ToolRuntime, Runtime)
- **feat-001 summary:** `doc/tasks/iterations/agent/feat-001-agent-graph/summary.md`

## Принятые решения (согласовано с архитектором)

| Вопрос | Решение | Обоснование |
|---|---|---|
| Store key design | **Multi-key**: один key per section | Progressive disclosure на уровне хранения. Безопасный scoped fuzzy replace. Гранулярный доступ |
| Index | **Auto-derived** из секций, сортировка по `created_at` | Нет рассинхрона. Не нужен отдельный Index key |
| Section description | **Explicit** — поле `description` в value секции | Агент контролирует описание. Не хрупко (vs first paragraph) |
| Tool DI | **ToolRuntime** (не InjectedStore + RunnableConfig) | Типизированный context (AgentContext), один параметр, рекомендован в langgraph-reference.md. Консистентно с Runtime в нодах |
| update семантика | **Fuzzy find & replace** (per-section scoped) + overwrite mode | LLM цитирует неточно → fuzzy matching. Scope по секции → нет cross-section замен |
| Tool set | **get_section, create_section, update_section, delete_section** | Чёткая CRUD-семантика. Нет get_sphere_index — Index pre-loaded |
| SphereService | **Реализовать в feat-002** через Store. Вынести store на app.state | REST API работает с реальными данными. Объём небольшой, польза для отладки |
| backend.md | **Обновить** секцию Tools — привести в соответствие с реализацией | SSOT: документация отражает реальность |

## API валидация (быстро меняющиеся инструменты)

Проверено через `inspect` пакетов (11 марта 2026):

| Инструмент | Версия | Актуальный API |
|---|---|---|
| langgraph | 1.1.0 | `StateGraph`, `MessagesState`, `START`, `END` — from `langgraph.graph` |
| langgraph-prebuilt | 1.0.8 | `ToolNode`, `tools_condition`, `ToolRuntime` — from `langgraph.prebuilt` |
| Runtime | langgraph 1.1.0 | `from langgraph.runtime import Runtime` — в нодах, `.store`, `.context` |
| ToolRuntime | 1.0.8 | `runtime: ToolRuntime` — fields: `state`, `context`, `config`, `store`, `tool_call_id`, `stream_writer` |
| BaseStore | langgraph 1.1.0 | `put(ns, key, value)`, `get(ns, key) → Item\|None`, `search(ns_prefix, *, limit=10) → list[SearchItem]`, `delete(ns, key)`. Async: `aput`, `aget`, `asearch`, `adelete` |
| SearchItem | langgraph 1.1.0 | Extends Item: `.key`, `.value` (dict), `.namespace`, `.created_at`, `.updated_at`, `.score` |
| AsyncPostgresStore | 3.0.4 | `from_conn_string(url)` → async context manager. `.setup()` creates tables |
| @tool decorator | langchain-core 1.2.18 | `from langchain_core.tools import tool`. ToolRuntime auto-injected by ToolNode |
| fuzzysearch | **не установлен** | `fuzzysearch>=0.8.0` — нужно добавить |

## Store Design

### Namespace

```
("project", project_id, "sphere")
```

`project_id` берётся из `runtime.context.project_id` (ToolRuntime) / `runtime.context.project_id` (Runtime в agent node).

### Key format

```
"section:{section_id}"
```

`section_id` — осмысленный slug, задаётся агентом: `project-overview`, `tech-stack`, `key-decisions` и т.д.

### Value format

```python
{
    "description": "Brief description for Index navigation",
    "content": "Full section content in Markdown"
}
```

`description` — explicit, обязательный при создании. Обновляемый при необходимости.

### Index (auto-derived)

Не хранится. Формируется при каждом вызове agent node:

```
store.search(namespace, limit=100) → sort by created_at → format:

Knowledge Sphere:
- project-overview: AI learning assistant for personalized education
- tech-stack: Python 3.12, FastAPI, LangGraph
- key-decisions: LangGraph Store, PostgreSQL, MCP
```

Если секций нет — `"Knowledge Sphere: empty"`.

## Tools Design

### get_section

```python
@tool
def get_section(section_id: str, runtime: ToolRuntime) -> str:
    """Get full content of a Knowledge Sphere section."""
```

- `store.get(ns, f"section:{section_id}")` → return `item.value["content"]`
- Если не найдена → return error message (агент обработает в ReAct loop)

### create_section

```python
@tool
def create_section(
    section_id: str,
    description: str,
    content: str,
    runtime: ToolRuntime,
) -> str:
    """Create a new Knowledge Sphere section."""
```

- Проверить что секция не существует (store.get)
- `store.put(ns, f"section:{section_id}", {"description": description, "content": content})`
- Если уже существует → return error (используй update_section)

### update_section

```python
@tool
def update_section(
    section_id: str,
    content: str,
    target: str = "",
    description: str = "",
    runtime: ToolRuntime,
) -> str:
    """Update an existing Knowledge Sphere section.

    Patch mode (target provided): fuzzy find target text within section, replace with content.
    Overwrite mode (no target): replace entire section content.
    Optionally update description.
    """
```

- Проверить что секция существует
- Если `target` → fuzzy_find_and_replace(current_content, target, content)
  - Не найден → return error с начало текущего контента (помочь агенту)
- Если нет `target` → overwrite content
- Если `description` передан → обновить description
- `store.put(ns, key, updated_value)`

### delete_section

```python
@tool
def delete_section(section_id: str, runtime: ToolRuntime) -> str:
    """Delete a Knowledge Sphere section."""
```

- Проверить что секция существует
- `store.delete(ns, f"section:{section_id}")`

## Fuzzy Replace

### Зависимость

`fuzzysearch>=0.8.0` — Levenshtein distance based matching.

### Алгоритм

```python
from fuzzysearch import find_near_matches

def fuzzy_find_and_replace(
    document: str,
    target: str,
    replacement: str,
    threshold: float = 0.85,
) -> tuple[str, bool, str | None, float]:
    """Returns: (new_document, success, found_text, similarity)"""

    if not target or not document:
        return document, False, None, 0.0

    # Короткие строки (<10 символов) — exact match only
    if len(target) < 10:
        if target in document:
            idx = document.index(target)
            new_doc = document[:idx] + replacement + document[idx + len(target):]
            return new_doc, True, target, 1.0
        return document, False, None, 0.0

    # Адаптивная дистанция
    max_distance = max(1, int(len(target) * (1 - threshold)))
    if len(target) > 100:
        max_distance = min(max_distance, 15)

    matches = find_near_matches(target, document, max_l_dist=max_distance)
    if not matches:
        return document, False, None, 0.0

    match = matches[0]
    similarity = max(0.0, 1 - (match.dist / len(target)))

    new_document = document[:match.start] + replacement + document[match.end:]
    return new_document, True, match.matched, similarity
```

Используется в `update_section` при наличии `target`.

## Шаги реализации

### 0. Ветка

```bash
git fetch origin && git checkout -b feat/002-knowledge-sphere origin/develop
```

### 1. Зависимости

**Файл:** `backend/pyproject.toml`

Добавить:
```
"fuzzysearch>=0.8.0",
```

После: `cd backend && uv sync`

### 2. KS helpers

**Новый файл:** `backend/app/agent/tools/ks_helpers.py`

- `SPHERE_NAMESPACE_PREFIX = ("project",)` — константа
- `build_namespace(project_id: str) -> tuple[str, ...]` — `("project", project_id, "sphere")`
- `section_key(section_id: str) -> str` — `f"section:{section_id}"`
- `fuzzy_find_and_replace(document, target, replacement, threshold=0.85)` — алгоритм выше
- `format_index(items: list) -> str` — сортировка по `created_at`, формат `"- {id}: {description}"`

### 3. KS tools

**Новый файл:** `backend/app/agent/tools/knowledge_sphere.py`

Четыре tool-функции:
- `get_section(section_id, runtime: ToolRuntime) -> str`
- `create_section(section_id, description, content, runtime: ToolRuntime) -> str`
- `update_section(section_id, content, target="", description="", runtime: ToolRuntime) -> str`
- `delete_section(section_id, runtime: ToolRuntime) -> str`

Все используют `runtime.context.project_id` для namespace и `runtime.store` для доступа к Store.

**Файл:** `backend/app/agent/tools/__init__.py`

Обновить — экспортировать list всех KS tools для регистрации в графе:
```python
from app.agent.tools.knowledge_sphere import (
    get_section, create_section, update_section, delete_section,
)

ks_tools = [get_section, create_section, update_section, delete_section]
```

### 4. Agent graph: Index injection + tools registration

**Файл:** `backend/app/agent/graph.py`

Изменения в `agent_node`:
1. Получить `runtime.store` и `runtime.context.project_id`
2. `await store.asearch(namespace, limit=100)` — все секции
3. Сформировать Index через `format_index(items)`
4. Инжектить в system message: `f"{agent_config.prompt.system}\n\n{ks_index}"`

Изменения в `build_graph`:
1. Параметр `tools` уже есть — передаём KS tools
2. ToolNode создаётся с этими tools (уже работает)

### 5. SphereService: реальная реализация через Store

**Файл:** `backend/app/services/sphere.py`

Добавить `LangGraphSphereService`:
```python
class LangGraphSphereService:
    def __init__(self, store: BaseStore) -> None:
        self._store = store

    async def get(self, *, project_id: uuid.UUID) -> SphereData:
        ns = ("project", str(project_id), "sphere")
        items = await self._store.asearch(ns, limit=100)
        # Sort by created_at, concat sections
        content = _format_full_sphere(items)
        updated_at = max((i.updated_at for i in items), default=datetime.now(UTC))
        return SphereData(project_id=project_id, content=content, updated_at=updated_at)

    async def update(self, *, project_id: uuid.UUID, content: str) -> SphereData:
        # Parse markdown into sections → store.put each
        # Delete old sections not in new content
        ...
```

`_format_full_sphere` — concat всех секций в единый Markdown для REST API response.

`update` (PUT) — парсинг входящего Markdown:
- Разбить по H2 headers (`## Title`)
- Для каждой секции: section_id = slugify(title), description = первая строка (или explicit из формата), content = остальное
- Записать в Store, удалить отсутствующие

Оставить `StubSphereService` как fallback (не удалять).

### 6. Wiring: main.py + deps.py

**Файл:** `backend/app/main.py`

Изменения в lifespan:
1. `app.state.store = store` — вынести Store на app.state для доступа из Service Layer
2. Передать KS tools в `build_graph`:
```python
from app.agent.tools import ks_tools

builder = build_graph(model=llm, tools=ks_tools, agent_config=agent_config)
```

**Файл:** `backend/app/api/deps.py`

Изменить `get_sphere_service`:
```python
from app.services.sphere import LangGraphSphereService

def get_sphere_service(request: Request) -> LangGraphSphereService:
    return LangGraphSphereService(store=request.app.state.store)
```

Обновить `SphereServiceDep` type annotation.

### 7. Обновление services/__init__.py

Добавить `LangGraphSphereService` в exports. Убрать `StubSphereService` из `__all__` (если больше не используется).

### 8. Документация

**Файл:** `doc/tech/backend.md`

Обновить секцию **Tools / Internal**:
- Убрать `get_sphere_index()` — Index pre-loaded, не tool
- Заменить `update_sphere(facts)` на `create_section`, `update_section`, `delete_section`
- Описать fuzzy replace в update_section
- Обновить секцию **Context Engineering** — отразить auto-derived Index

## Что НЕ входит в feat-002

- Based Prompt (feat-005) — system prompt остаётся минимальным
- Skills (feat-003)
- MCP tools (feat-004)
- History compaction / summarization (feat-005)
- Streaming events tool_start/tool_end (feat-003)
- REST API schema изменения (расширение SphereResponse до structured sections — при необходимости)

## Артефакты — новые файлы

```
backend/app/agent/tools/
├── __init__.py              # обновлён: экспорт ks_tools
├── ks_helpers.py            # namespace builders, fuzzy_find_and_replace, format_index
└── knowledge_sphere.py      # get_section, create_section, update_section, delete_section
```

## Артефакты — изменённые файлы

```
backend/pyproject.toml           # +fuzzysearch
backend/app/agent/graph.py       # Index injection в agent_node, tools передаются
backend/app/main.py              # app.state.store, ks_tools в build_graph
backend/app/api/deps.py          # LangGraphSphereService wiring
backend/app/services/sphere.py   # LangGraphSphereService implementation
backend/app/services/__init__.py # exports update
doc/tech/backend.md              # Tools section update
```

## Верификация

1. `cd backend && uv sync` — fuzzysearch установлен
2. `make docker-up` — PostgreSQL запущен
3. `make dev` — приложение стартует, Store setup ok
4. **Тест create + get:**
   ```bash
   # Создать проект
   curl -X POST http://localhost:8000/projects \
     -H "X-User-Name: test" -H "Content-Type: application/json" \
     -d '{"name": "Test"}'

   # Создать чат, отправить сообщение, агент создаст секции KS
   curl -N -X POST http://localhost:8000/projects/<id>/chats/<cid>/messages \
     -H "X-User-Name: test" -H "Content-Type: application/json" \
     -d '{"content": "I am building a Python web app with FastAPI"}'

   # Проверить шар через REST API
   curl http://localhost:8000/projects/<id>/sphere \
     -H "X-User-Name: test"
   # → секции, созданные агентом
   ```
5. **Тест Index pre-loading:** следующее сообщение в чате — агент видит KS Index в контексте, ссылается на известную информацию
6. **Тест fuzzy update:** агент обновляет факт в секции через update_section с target
7. **REST PUT:** перезапись шара через API → агент видит обновлённый Index
8. `make check` — ruff check, ruff format --check, mypy проходят

## Финальный шаг

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.
