---
name: langgraph-patterns
description: >
  Продвинутые паттерны LangGraph: Command API, HITL (interrupt/resume),
  checkpointing с PostgreSQL, параллельное выполнение через Send,
  state accumulation с operator.add, streaming events.
  Используй когда: LangGraph, StateGraph, workflow, граф, Command,
  interrupt, HITL, human-in-the-loop, checkpointer, Send, fan-out.
---

# LangGraph: Ключевые паттерны

Документ фиксирует продвинутые концепты LangGraph, которые не очевидны из базовой документации.

## 1. Навигация: Command API vs Pre-defined Edges

В LangGraph есть два подхода к определению переходов между узлами:

**Pre-defined edges** — классический подход через `add_edge()` и `add_conditional_edges()` при построении графа. Переходы фиксированы на этапе компиляции.

**Command API** — динамический подход, где каждый узел сам определяет следующий шаг через возвращаемый `Command`. Более гибкий, позволяет менять маршрут на основе runtime-данных.

**Когда что использовать:**
- Pre-defined edges — простые линейные workflow с известной топологией
- Command API — сложные workflow с условной логикой, HITL, динамическим routing

```python
from langgraph.types import Command

async def my_node(state, config) -> Command:
    # Логика узла...

    if needs_refinement:
        # Conditional routing внутри узла
        return Command(goto="refine_node", update={"field": value})
    else:
        return Command(goto="next_node", update={"result": data})
```

**Ключевой инсайт:** Command объединяет переход (`goto`) и обновление состояния (`update`) в одном return. Это устраняет необходимость в `add_conditional_edges()` для большинства случаев.


## 2. Persistence & Checkpointing

LangGraph поддерживает персистентное состояние через checkpointers. Каждый `thread_id` получает изолированное состояние.

**Setup с PostgreSQL:**

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

async def run_workflow(thread_id: str, input_state):
    async with AsyncPostgresSaver.from_conn_string(DATABASE_URL) as saver:
        # Первый запуск — создание таблиц
        await saver.setup()

        # Компиляция графа с checkpointer
        graph = workflow.compile(checkpointer=saver)

        # Конфигурация с thread_id для изоляции
        cfg = {"configurable": {"thread_id": thread_id}}

        # Выполнение
        async for event in graph.astream(input_state, cfg, stream_mode="updates"):
            process_event(event)
```

**Получение состояния:**

```python
async def get_state(thread_id: str):
    async with AsyncPostgresSaver.from_conn_string(DATABASE_URL) as saver:
        graph = workflow.compile(checkpointer=saver)
        cfg = {"configurable": {"thread_id": thread_id}}
        return await graph.aget_state(cfg)
```

**Удаление thread:**

```python
async with AsyncPostgresSaver.from_conn_string(DATABASE_URL) as saver:
    await saver.adelete_thread(thread_id)
```

**Production considerations:**
- `from_conn_string()` создаёт connection pool под капотом
- Используй `async with` для корректного освобождения соединений
- Для SQLite есть `SqliteSaver` (для dev/testing)


## 3. Human-in-the-Loop (HITL)

HITL позволяет приостановить workflow, получить ввод от пользователя и продолжить выполнение.

**Механизм работы:**

1. Узел вызывает `interrupt()` — workflow останавливается
2. Состояние сохраняется в checkpointer
3. Внешний код получает interrupt data
4. Пользователь предоставляет ответ
5. Workflow продолжается через `Command(resume=...)`

```python
from langgraph.types import interrupt, Command

async def hitl_node(state, config) -> Command:
    # Генерируем контент для пользователя
    generated_content = await generate_something(state)

    # Отправляем пользователю и ждём ответа
    interrupt_data = {
        "message": [
            generated_content,
            "Всё верно? Напишите 'да' или опишите изменения."
        ]
    }
    user_response = interrupt(interrupt_data)

    # После resume — user_response содержит ответ пользователя
    if is_approved(user_response):
        return Command(goto="next_node", update={"approved": True})
    else:
        # Цикл уточнения — возвращаемся в тот же узел
        return Command(
            goto="hitl_node",  # self-loop
            update={"feedback": user_response}
        )
```

**Возобновление workflow:**

```python
# Получаем текущее состояние
state = await graph.aget_state(cfg)

if state.interrupts:
    # Есть прерывание — показываем пользователю
    interrupt_data = state.interrupts[0].value
    messages = interrupt_data.get("message", [])

    # ... показываем messages пользователю, получаем ответ ...

    # Продолжаем workflow с ответом
    resume_command = Command(resume=user_answer)
    async for event in graph.astream(resume_command, cfg, stream_mode="updates"):
        process_event(event)
```

**HITL Loop паттерн** (generate → feedback → refine):

```python
async def feedback_node(state, config) -> Command:
    is_first_run = len(state.feedback_messages) == 0

    if is_first_run:
        # Первая генерация
        content = await generate_initial(state)
        feedback_history = [AIMessage(content=content)]
    else:
        # Refinement на основе фидбека
        content = await refine_with_feedback(state)
        feedback_history = state.feedback_messages

    # Запрос фидбека
    user_feedback = interrupt({"message": [content, "Ваш фидбек?"]})

    # Добавляем в историю
    updated_history = feedback_history + [HumanMessage(content=user_feedback)]

    if is_approved(user_feedback):
        return Command(goto="next_node", update={"result": content})
    else:
        return Command(
            goto="feedback_node",
            update={"feedback_messages": updated_history}
        )
```


## 4. State с аккумуляцией (operator.add)

По умолчанию обновление поля заменяет значение. Для параллельной обработки нужна **аккумуляция** — результаты от нескольких worker'ов объединяются.

```python
import operator
from typing import Annotated, List
from pydantic import BaseModel, Field

class GeneratedSection(BaseModel):
    section_order: int
    content: str

class WorkflowState(BaseModel):
    input_content: str = ""

    # Обычное поле — replace semantics
    current_step: str = ""

    # Аккумулирующее поле — append semantics
    generated_sections: Annotated[List[GeneratedSection], operator.add] = Field(
        default_factory=list
    )

    # Ещё один пример аккумуляции
    questions_and_answers: Annotated[List[str], operator.add] = Field(
        default_factory=list
    )
```

**Как это работает:**

```python
# Worker 1 возвращает:
Command(update={"generated_sections": [section_1]})

# Worker 2 возвращает:
Command(update={"generated_sections": [section_2]})

# Результат в state (после operator.add):
state.generated_sections == [section_1, section_2]
```

**Важно:** Без `Annotated[..., operator.add]` второй worker перезаписал бы результат первого.


## 5. Параллельное выполнение (Send)

`Send` позволяет запустить несколько экземпляров узла параллельно с разными данными.

**Fan-out паттерн:**

```python
from langgraph.constants import Send

async def master_node(state, config) -> Command:
    sections = state.document_structure.sections

    # Создаём Send для каждой секции
    send_commands = []
    for i, section in enumerate(sections):
        send_commands.append(
            Send(
                "generate_section",  # имя worker-узла
                {
                    # Payload — данные для конкретного worker'а
                    "section": section.model_dump(),
                    "section_index": i,
                    "input_content": state.input_content,
                }
            )
        )

    # Возвращаем список Send — все запустятся параллельно
    return send_commands
```

**Worker node — получает payload, не full state:**

```python
from typing_extensions import TypedDict

class SectionWorkerState(TypedDict):
    """Payload от Send, не полный GeneralState"""
    section: dict
    section_index: int
    input_content: str

async def generate_section(state: SectionWorkerState, config) -> Command:
    section_data = state["section"]  # Из payload

    content = await generate_content(section_data)

    result = GeneratedSection(
        section_order=state["section_index"],
        content=content
    )

    # Возвращаем в аккумулирующее поле
    return Command(
        update={"generated_sections": [result]},
        goto="check_assembly_ready"  # Или специальный gate-узел
    )
```

**Fan-in через gate function:**

```python
def check_assembly_ready(state) -> str:
    """Gate: ждём пока все секции сгенерированы"""
    total_sections = len(state.document_structure.sections)
    generated_count = len(state.generated_sections)

    if generated_count >= total_sections:
        return "document_assembly"
    else:
        # Ещё не все готовы — ждём
        return "__end__"  # Или специальный wait-узел
```


## 6. RunnableConfig & Metadata

`config` передаётся в каждый узел и содержит runtime-контекст.

```python
async def my_node(state, config) -> Command:
    # Извлечение thread_id
    thread_id = config["configurable"]["thread_id"]

    # ... логика узла ...
```

**Передача callbacks и metadata:**

```python
from langfuse.callback import CallbackHandler

langfuse_handler = CallbackHandler()

cfg = {
    "configurable": {"thread_id": thread_id},
    "callbacks": [langfuse_handler],
    "metadata": {
        "langfuse_session_id": session_id,
        "langfuse_user_id": user_id,
        "custom_field": "value"
    }
}

async for event in graph.astream(input_state, cfg, stream_mode="updates"):
    ...
```

**Передача данных через Send payload:**
Если нужно передать данные конкретному worker'у (не через state), используй payload в Send:

```python
Send("worker_node", {
    "section": section_data,
    "extra_context": some_context
})
```

Worker получит это в `state` параметре (но это будет payload, не полный state).


## 7. Streaming & Events

`astream()` с `stream_mode="updates"` даёт event-by-event обработку.

```python
async for event in graph.astream(input_state, cfg, stream_mode="updates"):
    # event — dict: {node_name: node_output}
    for node_name, node_data in event.items():
        print(f"Node {node_name} produced: {node_data}")

        # Можно реагировать на конкретные узлы
        if node_name == "generating_content":
            save_content(node_data.get("generated_material"))
```

**Обработка interrupts в stream:**

```python
async def run_with_interrupts(thread_id, input_data):
    cfg = {"configurable": {"thread_id": thread_id}}

    async with AsyncPostgresSaver.from_conn_string(DB_URL) as saver:
        graph = workflow.compile(checkpointer=saver)

        async for event in graph.astream(input_data, cfg, stream_mode="updates"):
            process_event(event)

        # После stream — проверяем interrupt
        final_state = await graph.aget_state(cfg)

        if final_state.interrupts:
            interrupt_data = final_state.interrupts[0].value
            return {"status": "interrupted", "data": interrupt_data}
        else:
            return {"status": "completed", "result": final_state.values}
```


## Типичные ошибки

1. **Забыть `operator.add`** для parallel workers — результаты перезаписываются вместо накопления

2. **Использовать full state в worker** — Send передаёт payload, не весь state. Worker должен ожидать TypedDict с нужными полями

3. **Не проверять interrupts** после astream — workflow может остановиться на interrupt, а код продолжит выполнение

4. **Создавать checkpointer без `async with`** — утечка соединений к БД

5. **Возвращать просто dict вместо Command** — работает, но теряешь возможность указать `goto`
