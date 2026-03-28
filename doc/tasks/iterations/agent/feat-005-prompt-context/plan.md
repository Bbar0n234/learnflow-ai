# Implementation Plan: feat-005 — Based Prompt & Context Engineering

## Context

Итерация закрывает последний блок agent runtime из tasklist-agent.md: полноценный системный промпт и стратегия управления контекстом. Сейчас system prompt — заглушка `"You are a helpful AI learning assistant."`, trimming работает но без compaction, system message собирается через `"\n\n".join()` без структуры.

**Цель:** агент рассуждает осмысленно, эффективно использует tools и память, gracefully обрабатывает ошибки и длинные сессии.

## Референсы

| Документ | Что берём |
|----------|-----------|
| [doc/workflow.md](../../learnflow-ai/doc/workflow.md) | Формат итерации, жизненный цикл |
| [doc/tech/conventions.md](../../learnflow-ai/doc/tech/conventions.md) | Git flow, naming, code quality |
| [doc/tasks/tasklist-agent.md](../../learnflow-ai/doc/tasks/tasklist-agent.md) | Состав работ, критерии приёмки |
| [doc/tech/backend.md](../../learnflow-ai/doc/tech/backend.md) | Agent Runtime, Based Prompt spec, Context Engineering, Tools |
| [doc/tech/adr/ADR-004-progressive-disclosure.md](../../learnflow-ai/doc/tech/adr/ADR-004-progressive-disclosure.md) | Progressive disclosure, compaction |
| [doc/tech/adr/ADR-001-general-agent.md](../../learnflow-ai/doc/tech/adr/ADR-001-general-agent.md) | General Agent формула |
| [doc/tech/langgraph-reference.md](../../learnflow-ai/doc/tech/langgraph-reference.md) | trim_messages, RemoveMessage, context engineering patterns |
| [doc/product/use-cases.md](../../learnflow-ai/doc/product/use-cases.md) | UC-1..UC-3 для тестирования |
| [doc/idea.md](../../learnflow-ai/doc/idea.md) | Роль, ICP, JTBD |
| Skill: prompt-engineering | Принципы написания промпта |

## Согласованные решения

| Вопрос | Решение |
|--------|---------|
| Хранение промпта | Отдельный TXT-файл, путь из `agent.yaml` |
| Язык промпта | Английский |
| Сборка system message | Jinja2-шаблон вместо `"\n\n".join()` |
| Разметка динамических секций | XML-теги (`<knowledge_sphere>`, `<skills>`) |
| Tool descriptions | В docstrings инструментов, НЕ дублировать в промпте |
| Модель для summarization | Отдельная (дешевле), конфигурируется в `agent.yaml` |
| KS Index refinement | Интеграция в Based Prompt + Jinja2 шаблон + XML-теги |

## Инструменты — актуальные версии

| Пакет | Версия | Заметки |
|-------|--------|---------|
| langgraph | 1.1.0 | SummarizationNode **НЕ доступен** |
| langgraph-prebuilt | 1.0.8 | ToolNode, ToolRuntime, tools_condition — ОК |
| langchain-core | 1.2.18 | trim_messages, count_tokens_approximately, RemoveMessage — ОК |
| langchain-openai | 1.1.11 | |
| langgraph-checkpoint-postgres | 3.0.4 | |

Ключевые API проверены через `inspect`:
- `trim_messages(messages, *, max_tokens, token_counter, strategy, include_system, start_on, end_on)` — ОК
- `RemoveMessage(id=...)`, `REMOVE_ALL_MESSAGES` — ОК
- `Runtime[AgentContext]` с `.context`, `.store` — ОК
- `StateGraph(state_schema, context_schema=...)` — ОК

## Шаги реализации

### Шаг 0: Ветка

```bash
git fetch origin && git checkout -b feat/005-prompt-context origin/develop
```

Ветка `feat/005-prompt-context` согласно conventions.md.

---

### Шаг 1: Зависимость Jinja2

**Файл:** `backend/pyproject.toml`

Добавить `jinja2>=3.1` в dependencies.

---

### Шаг 2: Based Prompt — TXT-файл

**Новый файл:** `configs/prompts/system.txt`

**Минимальный каркас** системного промпта на английском. Модель (Gemini Flash) достаточно продвинута — очевидные инструкции расписывать не нужно. Это baseline для итеративной доработки в ходе опытной эксплуатации.

При написании **обязательно использовать скилл `/prompt-engineering`** и применять его принципы:
- **High-signal tokens** — каждый токен несёт информацию, без воды и повторений
- **Goldilocks zone** — специфично для направления, гибко для непокрытых кейсов
- **Understanding over instructions** — объясняем "почему", не только "что"
- **Без дублирования tool descriptions** — tools описаны в своих docstrings, в промпт не включать
- **Не over-engineer** — промпт дорабатывается по failure modes, не пишется "идеальным" сразу

#### Содержание промпта (краткий каркас)

Только то, что модель сама не выведет из контекста:

- **Role & mission** — AI assistant для tech-спикеров, JTBD (мысли → структурированные материалы)
- **Interaction style** — expert-to-expert, match user's language, direct
- **Knowledge Sphere** — что это (persistent project memory), когда подгружать/обновлять секции, автономность обновлений
- **Artifacts** — save final deliverables, не промежуточные черновики
- **Error handling** — retry/adapt, communicate problems
- **Boundaries** — focus on material preparation, honesty about uncertainty

**Не включать:** описания отдельных tools/skills, пошаговые инструкции для очевидных вещей, хардкоды (длина ответов, количество шагов).

---

### Шаг 3: Конфигурация — путь к промпту и модель summarization

**Файл:** `backend/app/agent/config.py`

Изменения в `PromptConfig`:
```python
class PromptConfig(BaseModel):
    system_file: str  # путь к TXT-файлу промпта (относительно configs/)
    system_text: str = ""  # populated at load time — загруженный текст промпта
```

`load_agent_config` читает файл по `system_file` и заполняет `system_text`. Оба поля в одном объекте — конфиг самодостаточен, не нужно таскать текст промпта отдельно.

Добавить `SummarizationConfig`:
```python
class SummarizationConfig(BaseModel):
    model: str  # модель для summarization (дешевле основной)
    max_summary_tokens: int = 500  # максимальный размер summary
```

Добавить в `ContextConfig`:
```python
class ContextConfig(BaseModel):
    max_tokens: int
    compaction_threshold_ratio: float = 0.75  # доля max_tokens, при которой срабатывает compaction
    recent_messages_to_keep: int = 10  # сколько последних сообщений НЕ суммаризировать
```

Добавить в `AgentConfig`:
```python
class AgentConfig(BaseModel):
    llm: LLMConfig
    context: ContextConfig
    prompt: PromptConfig
    summarization: SummarizationConfig | None = None  # опционально, без него — только trim
    mcp_servers: dict[str, MCPServerConfig] = {}
```

`load_agent_config` — загружает текст промпта из файла по пути `prompt.system_file`.

**Файл:** `configs/agent.yaml`

```yaml
llm:
  model: "google/gemini-3-flash-preview"

context:
  max_tokens: 100000
  compaction_threshold_ratio: 0.75
  recent_messages_to_keep: 10

prompt:
  system_file: "prompts/system.txt"

summarization:
  model: "google/gemini-3.1-flash-lite-preview"
  max_summary_tokens: 500

mcp_servers:
  firecrawl:
    transport: http
    url: https://mcp.firecrawl.dev/v2/mcp
    api_key_env: FIRECRAWL_API_KEY
```

---

### Шаг 4: Jinja2-шаблон для system message

**Новый файл:** `backend/app/agent/prompt_builder.py`

Модуль для сборки system message из частей через Jinja2.

```python
from jinja2 import Template

SYSTEM_MESSAGE_TEMPLATE = Template("""\
{{ based_prompt }}

<knowledge_sphere>
{{ ks_index }}
</knowledge_sphere>

{% if skills_index %}
<available_skills>
{{ skills_index }}
</available_skills>
{% endif %}
""")

def build_system_message(
    based_prompt: str,
    ks_index: str,
    skills_index: str = "",
) -> str:
    return SYSTEM_MESSAGE_TEMPLATE.render(
        based_prompt=based_prompt,
        ks_index=ks_index,
        skills_index=skills_index,
    )
```

XML-теги (`<knowledge_sphere>`, `<available_skills>`) для семантического разделения динамических секций — принцип из prompt-engineering скилла.

---

### Шаг 5: Рефакторинг agent_node — использование шаблона

**Файл:** `backend/app/agent/graph.py`

Текущий код:
```python
parts = [agent_config.prompt.system, ks_index]
if skills_index:
    parts.append(skills_index)
system = SystemMessage(content="\n\n".join(parts))
```

Заменить на:
```python
from app.agent.prompt_builder import build_system_message

content = build_system_message(
    based_prompt=based_prompt,  # загруженный текст из TXT-файла
    ks_index=ks_index,
    skills_index=skills_index,
)
system = SystemMessage(content=content)
```

`build_graph` принимает `based_prompt: str` вместо `agent_config` для промпта (или весь `agent_config` — но промпт загружен на этапе lifespan).

---

### Шаг 6: History compaction

**Файл:** `backend/app/agent/graph.py` (внутри `agent_node`)

SummarizationNode НЕ доступен — реализуем compaction inline в `agent_node`.

#### Логика

```python
async def agent_node(state: MessagesState, runtime: Runtime[AgentContext]) -> dict:
    messages = state["messages"]
    result_prefix: list = []  # RemoveMessage + summary, если compaction нужен

    # 1. Check if compaction is needed
    total_tokens = count_tokens_approximately(messages)
    threshold = agent_config.context.max_tokens * agent_config.context.compaction_threshold_ratio

    if (
        summarization_model is not None
        and total_tokens > threshold
        and len(messages) > agent_config.context.recent_messages_to_keep
    ):
        keep_count = agent_config.context.recent_messages_to_keep
        old_messages = messages[:-keep_count]
        recent_messages = messages[-keep_count:]

        try:
            # Summarize old messages
            summary_text = await _summarize(summarization_model, old_messages)

            # Remove old messages + add summary as AIMessage
            result_prefix = [RemoveMessage(id=m.id) for m in old_messages]
            summary_msg = AIMessage(content=f"[Previous conversation summary]\n{summary_text}")
            result_prefix.append(summary_msg)

            messages = [summary_msg] + recent_messages
        except Exception:
            logger.warning("Summarization failed, falling back to trim-only", exc_info=True)
            # Compaction — оптимизация, не критический путь.
            # При сбое summarization (сеть, rate limit, модель недоступна)
            # просто тримим как раньше, пользователь не видит ошибку.

    # 2. Build system message (existing logic, now with Jinja2)
    # ...

    # 3. Trim messages
    trimmed = trim_messages(messages, ...)

    # 4. LLM call
    response = await bound_model.ainvoke([system, *trimmed])

    return {"messages": result_prefix + [response]}
```

**Summary как AIMessage** — summary сохраняется как `AIMessage`, не `HumanMessage`. HumanMessage может заставить модель "отвечать" на summary вместо использования его как контекста. AIMessage семантически = "ассистент подытожил разговор".

**Graceful degradation summarization** — `try/except` с fallback на trim-only. Compaction — оптимизация, не критический путь. Если summarization-модель недоступна (сеть, rate limit) — пользователь не должен видеть ошибку.

#### Функция summarization

```python
async def _summarize(model: BaseChatModel, messages: list) -> str:
    prompt = SystemMessage(content=(
        "Summarize the following conversation concisely. "
        "Preserve: key decisions, unresolved questions, current focus, "
        "important facts and context. "
        "Discard: redundant tool outputs, intermediate reasoning, greetings."
    ))
    response = await model.ainvoke([prompt, *messages])
    return response.content
```

`summarization_model` создаётся в `main.py` lifespan из `agent_config.summarization` и передаётся в `build_graph`. Если `summarization` не сконфигурирован — compaction отключен, работает только trim.

**Файл:** `backend/app/infra/llm.py`

Добавить функцию `create_summarization_llm` (или параметризовать `create_llm`) для создания отдельного клиента для summarization-модели.

---

### Шаг 7: Ревью tool docstrings

**Файлы:**
- `backend/app/agent/tools/knowledge_sphere.py`
- `backend/app/agent/tools/skills.py`
- `backend/app/agent/tools/artifacts.py`

Проверить и при необходимости улучшить docstrings (descriptions) инструментов. Docstrings — это то, что видит LLM при bind_tools. Они должны быть информативными для агента:

Текущие docstrings и оценка:
- `get_section`: "Get full content of a Knowledge Sphere section." — **OK**, но можно добавить hint когда использовать
- `create_section`: "Create a new Knowledge Sphere section." — **минимально**, стоит уточнить что хранить
- `update_section`: **хороший** docstring с описанием двух режимов
- `delete_section`: "Delete a Knowledge Sphere section." — **OK**
- `load_skill`: **хороший** docstring
- `create_artifact`: **хороший** docstring с примерами типов

Подход: НЕ раздувать docstrings, но добавить 1-2 предложения guidance где это полезно. Без дублирования в system prompt.

---

### Шаг 8: Wiring в main.py

**Файл:** `backend/app/main.py`

Изменения в lifespan:
1. `load_agent_config` загружает текст промпта из TXT-файла
2. Создание `summarization_llm` из `agent_config.summarization` (если сконфигурирован)
3. Передача `based_prompt` и `summarization_model` в `build_graph`

---

### Шаг 9: Тестирование на use-cases

Ручное тестирование через API (POST messages → SSE stream):

| Кейс | Что проверяем |
|------|---------------|
| UC-1: Структурирование | Агент использует skill "structure", предлагает аутлайн, сохраняет как artifact |
| UC-2: Research | Агент использует Firecrawl (web search), возвращает результат со ссылками |
| UC-3: KS context | Агент читает KS index, подгружает секции, обновляет KS автономно |
| Long session (>50 msgs) | Compaction срабатывает, агент не теряет контекст |
| Tool error | Агент gracefully обрабатывает ошибку, сообщает пользователю |
| Тон и формат | Ответы соответствуют Based Prompt (expert-to-expert, direct) |

---

### Шаг 10: make check

```bash
make check  # ruff check + ruff format + mypy
```

Убедиться что всё проходит.

---

### Шаг 11: Документация итерации

- `doc/tasks/iterations/agent/feat-005-prompt-context/plan.md` — ссылка на этот план (или копия)
- Обновить `doc/tasks/tasklist-agent.md` — статус feat-005 → 🚧 In Progress

---

### Финальный шаг: Ревью архитектора

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.

## Файлы для изменения

| Файл | Тип изменения |
|------|---------------|
| `backend/pyproject.toml` | Добавить jinja2 |
| `configs/prompts/system.txt` | **Новый** — Based Prompt |
| `configs/agent.yaml` | Обновить структуру (system_file, summarization) |
| `backend/app/agent/config.py` | PromptConfig, SummarizationConfig, ContextConfig |
| `backend/app/agent/prompt_builder.py` | **Новый** — Jinja2 шаблон сборки system message |
| `backend/app/agent/graph.py` | Шаблон + compaction в agent_node |
| `backend/app/agent/tools/knowledge_sphere.py` | Ревью docstrings |
| `backend/app/agent/tools/skills.py` | Ревью docstrings |
| `backend/app/agent/tools/artifacts.py` | Ревью docstrings |
| `backend/app/infra/llm.py` | create_summarization_llm |
| `backend/app/main.py` | Wiring промпта и summarization model |

## Верификация

1. `make check` (ruff check + ruff format + mypy) — проходит
2. Сервер стартует без ошибок, `/health` → 200
3. Backward compatibility: при отсутствии `summarization` в конфиге — работает без compaction
4. E2E: отправить сообщение → агент отвечает с правильным тоном, использует tools по назначению
5. Compaction: симулировать длинный диалог (>50 сообщений), убедиться что compaction срабатывает и контекст не теряется
6. KS: агент обновляет KS автономно при получении значимой информации
