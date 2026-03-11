# Post-Implementation Summary: agent/feat-003 — Skills System + Artifacts

## Результат

Реализовано полностью. Skills System (файловая система + JIT-подгрузка через `load_skill`), Artifacts tool (`create_artifact` с `content_and_artifact` response format), расширенный streaming протокол (tool_start/tool_end/artifact_created).

## Отклонения от плана

### SSE wire format: коллизия `type` в `artifact_created`

**План:** `artifact_created` event payload: `{ id, title, type }`.

**Проблема:** SSE wire format в `messages.py` формирует JSON как `{"type": event.type, **event.data}`. Поле `type` из artifact metadata (`"plan"`) перезаписывало `type` события (`"artifact_created"`). На стриме вместо `artifact_created` приходило `plan`.

**Решение:** в `runner.py` при формировании `artifact_created` event поле переименовывается: `type` → `artifact_type`. Итоговый payload: `{ id, title, artifact_type }`. Документация в `backend.md` актуализирована.

### SSE wire format: `call_id` в tool_start/tool_end

**План:** payload `{ tool: str }` (по документации).

**Реализация:** добавлен `call_id` для корреляции tool_start/tool_end в случае параллельных tool calls. Payload: `{ tool: str, call_id: str }`. Документация в `backend.md` актуализирована.

### skills_dir path

**План:** `Path(__file__).resolve().parents[1] / "skills"` (в `main.py`).

**Реализация:** `.parents[2]` — `parents[1]` = `backend/`, а `skills/` в корне репозитория. Ошибка в плане, исправлено при реализации.

### assert → RuntimeError

По решению архитектора при ревью, `assert` заменён на explicit `RuntimeError` во всех tools:
- `artifacts.py` — `create_artifact` (runtime.context)
- `knowledge_sphere.py` — `_ns()` (runtime.context) и `_store()` (runtime.store)

Консистентно с паттерном в `graph.py` (agent_node проверка store). Затрагивает код из feat-002, но изменение минимальное.

### _list_available guard

По результатам ревью: добавлена проверка `if not skills_dir.is_dir()` в `_list_available()` для консистентности с `scan_skills_index()`. Предотвращает `FileNotFoundError` при вызове на несуществующей директории.

### Skills directory — корень репозитория

**План** корректно предусматривал `skills/` в корне (не внутри `backend/app/`). Документация в `backend.md` (Module Structure) содержала устаревшее указание на `agent/skills/` — актуализировано.

## Верификация

E2E верификация через Python скрипт (6 кейсов + make check):

| Кейс | Статус |
|------|--------|
| Старт сервера (health OK) | Pass |
| Skills Index в контексте (агент перечисляет `structure` без tool call) | Pass |
| load_skill (existing) — tool_start → tool_end, skill content использован | Pass |
| load_skill (nonexistent) — tool_start → tool_end, ошибка с перечислением доступных | Pass |
| create_artifact — tool_start → tool_end → artifact_created с id/title/artifact_type | Pass |
| Артефакт в БД (GET /artifacts — в списке) | Pass |
| tool_start/tool_end для KS tools (create_section) | Pass |
| `make check` (ruff check + ruff format + mypy) | Pass |

## Актуализация документации

- `doc/tech/backend.md` — обновлены секции:
  - SSE Streaming Protocol: `call_id` в tool_start/tool_end, `artifact_type` в artifact_created
  - Module Structure: skills вынесены в `skills/` корня репозитория (не `agent/skills/`)
  - Context Engineering: Skills Index — Pre-loaded (аналогично KS Index)

## Артефакты

### Новые файлы

- `skills/structure/SKILL.md` — placeholder skill (Claude Code compatible формат)
- `backend/app/agent/tools/skills.py` — `make_load_skill_tool`, `scan_skills_index`
- `backend/app/agent/tools/artifacts.py` — `make_create_artifact_tool`

### Изменённые файлы

- `backend/app/agent/tools/__init__.py` — экспорт новых tool factories
- `backend/app/agent/runner.py` — `stream_mode=["messages", "updates"]`, маппинг tool_start/tool_end/artifact_created
- `backend/app/agent/graph.py` — параметр `skills_index`, инжекция в system message
- `backend/app/main.py` — создание tools через factories, wiring
- `backend/app/agent/tools/knowledge_sphere.py` — assert → RuntimeError в `_ns()`, `_store()`
- `doc/tech/backend.md` — SSE protocol, Module Structure, Context Engineering
- `doc/tasks/tasklist-agent.md` — статус feat-003 → Done
