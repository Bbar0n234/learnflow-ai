# Implementation Plan: agent/feat-003 — Skills System + Artifacts

## Context

Следующая запланированная итерация из `doc/tasks/tasklist-agent.md`. Зависимости сняты: agent/feat-001 (Done), backend-core/feat-003 ArtifactRepository (Done). Итерация добавляет два новых tool (load_skill, create_artifact) и расширяет streaming протокол событиями tool_start/tool_end/artifact_created.

## Референсы

- Workflow: `doc/workflow.md`
- Conventions: `doc/tech/conventions.md`
- Tasklist: `doc/tasks/tasklist-agent.md` (feat-003)
- Architecture: `doc/tech/backend.md` (Tools, SSE Streaming Protocol, Persistence/Artifact)
- ADR-002: `doc/tech/adr/ADR-002-skills-system.md` (Skills System)
- ADR-004: `doc/tech/adr/ADR-004-progressive-disclosure.md` (Progressive Disclosure, JIT skills)
- LangGraph Reference: `doc/tech/langgraph-reference.md` (ToolRuntime, stream modes)
- Пример реализации: `doc/tasks/iterations/agent/feat-002-knowledge-sphere/summary.md`

## Проверка API (быстро меняющиеся инструменты)

| Инструмент | Версия | Проверено |
|-----------|--------|-----------|
| langgraph | 1.1.0 | ToolRuntime из `langgraph.prebuilt`, stream_mode=["messages","updates"] — OK |
| langchain-core | 1.2.18 | @tool(response_format="content_and_artifact"), ToolMessage.artifact — OK |
| langgraph-checkpoint-postgres | 3.0.4 | Без изменений в этой итерации |
| **композиция** | — | `@tool(response_format="content_and_artifact")` + `ToolRuntime` инжекция через ToolNode — **smoke test пройден** (ToolMessage.artifact заполняется, runtime.context доступен) |

## Step 0: Ветка

```bash
git fetch origin && git checkout -b feat/003-skills-artifacts origin/develop
```

Ветка по conventions.md: `<type>/<NNN>-<short-desc>` → `feat/003-skills-artifacts`.

## Step 1: Skills — директория и формат файла

**Директория:** `skills/` в корне репозитория (рядом с `configs/`, `doc/`, `backend/`). Не внутри `backend/app/` — пользователь добавляет скиллы без необходимости лезть в код приложения.

**Структура:** каждый skill — своя поддиректория с `SKILL.md`:
```
skills/
└── structure/
    └── SKILL.md
```

**Формат SKILL.md** — 100% Claude Code skills-совместимый:

```markdown
---
name: structure
description: >
  Помогает структурировать учебный материал: разбивка на модули,
  логическая последовательность, learning objectives.
  Используй когда: структура, план обучения, модули, outline.
---

# Structure: Структурирование учебного материала

<knowledge content — инструкции, паттерны, подходы>
```

- `name` — идентификатор skill'а (= имя директории)
- `description` — описание + паттерны/триггеры (Claude Code convention: "Используй когда: ...")
- Body — knowledge: как делать (промпты, методики, паттерны)

Опционально: `references/`, `scripts/`, доп. файлы — как в Claude Code skills. Для MVP — только `SKILL.md`.

Создать placeholder `skills/structure/SKILL.md` с минимальным содержимым для e2e верификации.

**Existing `backend/app/agent/skills/__init__.py`**: пустой файл, остаётся как есть (пакет может понадобиться для будущей логики).

## Step 2: Tool — load_skill

**Новый файл:** `backend/app/agent/tools/skills.py`

```python
def make_load_skill_tool(skills_dir: Path):
    @tool
    async def load_skill(skill_name: str) -> str:
        """Load a skill module into context by name."""
        ...  # validate name, read SKILL.md, return full content
    return load_skill

def scan_skills_index(skills_dir: Path) -> str:
    """Build skills index from SKILL.md frontmatter (name + description)."""
    ...  # scan skills/*/SKILL.md, parse YAML frontmatter, return index string
```

### load_skill tool
- **Closure pattern**: tool захватывает `skills_dir` (путь к `<repo_root>/skills/`)
- **Путь к файлу**: `skills_dir / skill_name / "SKILL.md"` (Claude Code convention)
- **Sanitization**: skill_name — только `[a-z0-9_-]+`, проверка `is_relative_to(skills_dir)` для защиты от path traversal
- **Error handling**: несуществующий skill → строка ошибки с перечислением доступных skills (сканирование поддиректорий с `SKILL.md`). ToolNode вернёт как ToolMessage, агент увидит и скорректирует

### scan_skills_index (progressive disclosure)
По аналогии с KS Index (ADR-004): Skills Index = name + description из YAML frontmatter каждого скилла. Агент **всегда** видит доступные скиллы и их описания в system message, загружает полный контент JIT через `load_skill`.

- Сканирует `skills/*/SKILL.md` на старте
- Парсит YAML frontmatter (`---`-delimited, `yaml.safe_load`)
- Возвращает строку: `"Available Skills:\n- name: description\n- name: description"`
- Статический index — вычисляется один раз при старте (skills не меняются во время работы сервера)

Паттерн аналогичен KS tools (`_store()`, `_ns()` в `ks_helpers.py`), но через closure вместо ToolRuntime, т.к. зависимость — filesystem path, а не LangGraph-managed Store.

## Step 3: Tool — create_artifact

**Новый файл:** `backend/app/agent/tools/artifacts.py`

```python
def make_create_artifact_tool(session_factory: async_sessionmaker[AsyncSession]):
    @tool(response_format="content_and_artifact")
    async def create_artifact(
        title: str, content: str, type: str, runtime: ToolRuntime,
    ) -> tuple[str, dict]:
        """Save agent's work result as a project artifact."""
        ...  # create via ArtifactRepository, return (text, metadata)
    return create_artifact
```

Ключевые моменты:
- **Closure pattern**: захватывает `session_factory` (async_sessionmaker из lifespan)
- **ToolRuntime**: `runtime.context.project_id` для project_id, `runtime.config["configurable"]["thread_id"]` для thread_id
- **Отдельная сессия**: tool создаёт свою AsyncSession и коммитит внутри себя. Отдельная транзакция от request-scoped сессии — стандартный паттерн для операций внутри графа. **Важно:** `ArtifactRepository.create()` делает `flush()`, не `commit()` — нужен явный `await session.commit()` после `repo.create()` (либо `async with session.begin():` блок), иначе транзакция откатится при закрытии сессии
- **`response_format="content_and_artifact"`**: tool возвращает `tuple[str, dict]` → ToolMessage.content = текст для LLM, ToolMessage.artifact = `{"id": str, "title": str, "type": str}` — структурированные метаданные для streaming event `artifact_created`. Совместимость с ToolRuntime подтверждена smoke-тестом
- **ArtifactRepository** (existing): `backend/app/repositories/artifact.py` — `create(project_id, title, type, content, thread_id)`

## Step 4: Streaming — tool_start / tool_end / artifact_created

**Модифицируемый файл:** `backend/app/agent/runner.py` — `LangGraphAgentRunner.stream()`

Текущий подход: `stream_mode="messages"` — только text_chunk и done.

Новый подход: `stream_mode=["messages", "updates"]` — комбинированный стрим:

```
async for mode, data in self._graph.astream(..., stream_mode=["messages", "updates"]):
```

Маппинг событий:

| mode | data | → StreamEvent |
|------|------|---------------|
| `"messages"` | `(AIMessageChunk, metadata)` с непустым content | `text_chunk` |
| `"updates"` | `{"agent": {"messages": [AIMessage(tool_calls=[...])]}}` | `tool_start` для каждого tool_call |
| `"updates"` | `{"tools": {"messages": [ToolMessage(...)]}}` | `tool_end` для каждого ToolMessage |
| `"updates"` + tool_end | `ToolMessage.name == "create_artifact"` и `ToolMessage.artifact` не None | `artifact_created` (дополнительно к tool_end) |

Порядок событий в потоке:
1. Agent node: text_chunk (messages) → tool_start (updates, agent завершён с tool_calls)
2. Tools node: tool_end (updates, tools завершены) + artifact_created (если create_artifact)
3. Повторить если ReAct loop продолжается
4. done / error

### Edge cases при разборе updates

- **Agent без tool_calls** (финальный текстовый ответ): updates от agent → `{"agent": {"messages": [AIMessage(content="...")]}}` без tool_calls. Молча игнорировать — tool_start эмитится только при наличии `msg.tool_calls`
- **ToolMessage со status="error"**: если tool упал, ToolNode всё равно возвращает ToolMessage (с ошибкой). `tool_end` эмитится безусловно для каждого ToolMessage, независимо от status
- **Несколько tool_calls за один ход**: агент может вызвать 2+ tools. Updates от "agent" содержит AIMessage с несколькими tool_calls → `tool_start` для каждого. Updates от "tools" содержит список ToolMessage → цикл с `tool_end` для каждого + `artifact_created` для create_artifact

## Step 5: Wiring — подключение tools к графу

**Модифицируемые файлы:**

### `backend/app/agent/tools/__init__.py`
Экспорт: `ks_tools` (existing) + `make_load_skill_tool`, `make_create_artifact_tool`.

### `backend/app/main.py` (lifespan)
```python
from app.agent.tools import ks_tools, make_create_artifact_tool, make_load_skill_tool
from app.agent.tools.skills import scan_skills_index

# В lifespan, после создания session_factory:
skills_dir = Path(__file__).resolve().parents[2] / "skills"  # <repo_root>/skills/
load_skill = make_load_skill_tool(skills_dir)
skills_index = scan_skills_index(skills_dir)
create_artifact = make_create_artifact_tool(app.state.session_factory)
all_tools = ks_tools + [load_skill, create_artifact]

builder = build_graph(model=llm, tools=all_tools, agent_config=agent_config, skills_index=skills_index)
```

### `backend/app/agent/graph.py` — инжекция Skills Index
```python
def build_graph(model, tools, agent_config, skills_index: str = "") -> StateGraph:
    ...
    async def agent_node(state, runtime):
        ...
        parts = [agent_config.prompt.system, ks_index]
        if skills_index:
            parts.append(skills_index)
        system = SystemMessage(content="\n\n".join(parts))
        ...
```

Skills Index инжектится в system message **рядом** с KS Index. Оба — pre-loaded context по ADR-004.

## Step 6: make check

`make check` (ruff check + ruff format + mypy) — должен пройти чисто.

Потенциальные mypy issues:
- ToolRuntime generics (как в feat-002, решается через helper-функции с assert)
- Новые модули — стандартная типизация

## Файлы — сводка изменений

### Новые файлы
| Файл | Назначение |
|------|-----------|
| `backend/app/agent/tools/skills.py` | `make_load_skill_tool` — factory для load_skill tool |
| `backend/app/agent/tools/artifacts.py` | `make_create_artifact_tool` — factory для create_artifact tool |
| `skills/structure/SKILL.md` | Placeholder skill (Claude Code compatible формат) |

### Модифицируемые файлы
| Файл | Изменения |
|------|-----------|
| `backend/app/agent/tools/__init__.py` | Экспорт новых tool factories |
| `backend/app/agent/runner.py` | stream_mode → ["messages", "updates"], маппинг tool_start/tool_end/artifact_created |
| `backend/app/agent/graph.py` | Параметр `skills_index`, инжекция в system message рядом с KS Index |
| `backend/app/main.py` | Создание tools через factories, scan_skills_index, передача в build_graph |

### Без изменений
- `backend/app/repositories/artifact.py` — используется as-is
- `backend/app/models/artifact.py` — используется as-is
- `backend/app/api/routes/messages.py` — SSE wire format не меняется (StreamEvent → JSON)
- `backend/app/services/agent_runner.py` — StreamEvent protocol не меняется

## Верификация

### make check
```bash
make check  # ruff check + ruff format + mypy
```

### E2E проверка (curl)

Каждый кейс указывает, нужен ли новый thread. Новый thread = новый `POST /projects/{id}/chats` → свежий `thread_id`. Предотвращает влияние истории предыдущих сообщений на результат.

1. **Старт сервера** — `make dev`, health check OK

2. **Skills Index в контексте** — [новый thread] отправить "какие скиллы тебе доступны?". Проверить:
   - Агент перечисляет `structure` (и описание из frontmatter) — значит Skills Index инжектирован в system message
   - Не должен вызывать load_skill для ответа на этот вопрос (Index pre-loaded)

3. **load_skill** — [новый thread] "загрузи скилл structure и используй его для структурирования темы Machine Learning". Проверить:
   - В SSE стриме: `tool_start` → `tool_end` с `tool: "load_skill"`
   - Агент видит содержимое skill-файла и использует в ответе

4. **load_skill (несуществующий)** — [новый thread] "загрузи скилл nonexistent". Проверить:
   - `tool_start` → `tool_end`, агент сообщает что skill не найден

5. **create_artifact** — [новый thread] "создай артефакт с планом изучения Python". Проверить:
   - В SSE стриме: `tool_start` → `tool_end` с `tool: "create_artifact"` + `artifact_created` с id, title, type
   - `GET /projects/{id}/artifacts` — артефакт в списке
   - `GET /projects/{id}/artifacts/{aid}` — content не пустой

6. **tool_start/tool_end для KS tools** — [новый thread] "обнови шар знаний, запомни что я интересуюсь ML". Проверить:
   - `tool_start`/`tool_end` события для create_section/update_section

## Step 7 (финальный): Ревью архитектора

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем. Не коммитить до явного подтверждения.
