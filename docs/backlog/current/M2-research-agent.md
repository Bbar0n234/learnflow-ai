# Research Agent Specification

## 1. Overview

**Роль в M2**: External Sources Integration — поиск актуальной информации для обогащения генерируемых материалов.

**Проблема**: Некоторые темы требуют актуальных данных (новые фреймворки, текущие события), другие нет (математика, классические алгоритмы).

**Отличие от линейного поиска**:
- Линейный: генерируем N запросов → вызываем search → возвращаем результаты
- Агентный: итеративное погружение в источники, адаптация цели поиска, агрегация информации через несколько итераций

**Workflow integration**:
- Вызывается перед `planning_structure`
- Результаты передаются в `external_sources` placeholder для:
  - `planning_structure` — влияет на структуру документа
  - `section_generation` — обращение к конкретным источникам при генерации

---

## 2. Agent Architecture

### 2.1. Core Patterns

Применяем паттерны из `AGENT_PATTERNS.md`:

**Трехфазный цикл через LangGraph**:
```python
async def __call__(self, state: ResearchState, config):
    # Phase 1: Reasoning
    llm_reasoning = self.model.with_structured_output(ReasoningTool)
    reasoning = await llm_reasoning.ainvoke(messages)

    # Phase 2: Action Selection
    llm_action = self.model.with_structured_output(NextStepTools)
    action = await llm_action.ainvoke(messages)

    # Phase 3: Execution
    result = await self._execute_tool(action, state)

    # Continue or finish
    if reasoning.task_completed:
        return Command(goto="planning_structure", update={"final_report": result})
    else:
        return Command(goto="research_agent", update={"sources": result, "iteration": state.iteration + 1})
```

**Structured Output**: все решения через Pydantic schemas (constrained decoding), НЕ function calling.

**Conversation History**: LLM видит всю историю через state.feedback_messages.

**Resource Management**: динамические лимиты через условное формирование NextStepTools union.

### 2.2. ResearchState Model

```python
class ResearchState(BaseModel):
    """LangGraph state для research агента"""

    # Input
    input_content: str
    handwritten_notes: str = ""

    # Execution state
    iteration: int = 0
    agent_state: Literal["planning", "searching", "extracting", "synthesizing", "completed"] = "planning"

    # Accumulated knowledge (dict for deduplication, не через operator.add)
    sources: dict[str, SourceData] = Field(default_factory=dict)

    # History for LLM context
    feedback_messages: List[Any] = Field(default_factory=list)

    # Resource counters
    searches_used: int = 0
    extractions_used: int = 0

    # Results
    final_report: Optional[str] = None
```

**Эволюция state**:
- `sources` — растущая база знаний (URL как ключ → дедупликация)
- `feedback_messages` — conversation history для LLM
- Поля обновляются через Command(update={...})

### 2.3. LangGraph Implementation

**StateGraph structure**:
```python
from langgraph.graph import StateGraph
from langgraph.types import Command, interrupt

# Create graph
workflow = StateGraph(ResearchState)

# Single node with internal loop
workflow.add_node("research_agent", ResearchAgentNode())
workflow.set_entry_point("research_agent")

# Compile
graph = workflow.compile()
```

**Node pattern** (single monolithic node для MVP):
```python
class ResearchAgentNode(BaseWorkflowNode):
    async def __call__(self, state: ResearchState, config):
        # Initial planning
        if state.iteration == 0:
            plan = await self._generate_plan(state, config)
            return Command(
                goto="research_agent",
                update={"feedback_messages": [AIMessage(content=plan.json())], "iteration": 1}
            )

        # Iteration loop
        if state.iteration < MAX_ITERATIONS and not self._is_completed(state):
            action = await self._select_action(state, config)
            result = await self._execute_action(action, state)

            return Command(
                goto="research_agent",
                update={
                    "sources": result.sources,
                    "searches_used": state.searches_used + (1 if isinstance(action, WebSearchTool) else 0),
                    "iteration": state.iteration + 1
                }
            )

        # Finalization
        report = await self._create_report(state, config)
        return Command(
            goto=END,  # Or next node in main workflow
            update={"final_report": report}
        )
```

**HITL through interrupt()**:
```python
# When clarification needed
if isinstance(action, ClarificationTool):
    user_input = interrupt({"message": action.questions})

    return Command(
        goto="research_agent",
        update={
            "feedback_messages": state.feedback_messages + [
                AIMessage(content=action.json()),
                HumanMessage(content=user_input)
            ]
        }
    )
```

**Structured output через .with_structured_output()**:
```python
# All decisions via Pydantic schemas
NextStepTools = Union[WebSearchTool | ExtractTool | PlanTool | AdaptTool | ReportTool | FinalTool]

llm = self.model.with_structured_output(NextStepTools)
action = await llm.ainvoke(messages)  # Гарантированно валидный tool
```

---

## 3. Tools & Capabilities

### 3.1. MVP Tools (Tavily only)

**WebSearchTool**:
- Input: query, max_results
- Output: snippets (100 chars each), titles, URLs
- Обновляет: `context.sources` (добавляет новые с номерами [1], [2], [3])

**ExtractPageContentTool**:
- Input: urls (list)
- Output: full content страниц
- Обновляет: `context.sources[url].full_content` (enrichment существующих)

**GeneratePlanTool**:
- Input: reasoning
- Output: research_goal, planned_steps, search_strategies
- Создает: начальный план исследования

**AdaptPlanTool**:
- Input: reasoning, original_goal, new findings
- Output: new_goal, plan_changes, next_steps
- Адаптирует: план на основе противоречий/новых данных

**CreateReportTool**:
- Input: content (с inline citations [1], [2])
- Output: aggregated report + sources list
- Финализирует: исследование в структурированный отчет

**ReasoningTool**:
- Input: reasoning_steps, current_situation, enough_data, next_steps, task_completed
- Output: structured reasoning для прозрачности

**FinalAnswerTool**:
- Завершение работы агента

### 3.2. Extensibility (будущее)

**Базовая расширяемость** без изменения архитектуры:

```python
class BaseSourceTool(BaseTool):
    """Unified interface для любых источников"""
    async def search(query: str) -> list[SourceData]: ...
    async def extract(identifier: str) -> SourceData: ...

# MVP
class WebSearchTool(BaseSourceTool): ...  # Tavily

# Future
class RAGSearchTool(BaseSourceTool): ...  # Telegram channels
class DocumentSearchTool(BaseSourceTool): ...  # PDF, методички
```

Агент работает с `BaseSourceTool` → любой источник подключается без изменения логики.

---

## 4. Reasoning & Planning

### 4.1. Structured Reasoning

```python
class ReasoningTool(BaseModel):
    reasoning_steps: list[str] = Field(min_length=2, max_length=3)
    current_situation: str = Field(max_length=300)
    enough_data: bool
    next_steps: list[str] = Field(min_length=1, max_length=3)
    task_completed: bool
```

Принудительное мышление: Pydantic constraints заставляют LLM думать структурированно.

### 4.2. Adaptive Planning

**Когда адаптировать план**:
- Найденные данные противоречат гипотезе
- Обнаружены новые важные аспекты
- Consecutive failed searches > 2
- Searches remaining < 2 and not enough_data

**Как адаптировать**:
```python
AdaptPlanTool:
    original_goal: "Find BMW X6 prices in Russia"
    new_goal: "Explain BMW market exit and grey import options"
    plan_changes: [
        "Changed from price research to market situation analysis",
        "Added grey import investigation"
    ]
```

### 4.3. Resource Management

```python
def prepare_tools(context):
    tools = {WebSearch, Extract, Plan, Adapt, Report, Reasoning, Final}

    # Dynamic removal при достижении лимитов
    if context.searches_used >= MAX_SEARCHES:
        tools.remove(WebSearchTool)

    if context.iteration >= MAX_ITERATIONS:
        tools = {CreateReportTool, FinalAnswerTool}  # Forced completion

    return tools
```

---

## 5. Source Management & Citations

### 5.1. SourceData Model

```python
class SourceData(BaseModel):
    number: int           # [1], [2], [3] для citations
    title: str
    url: str
    snippet: str          # Из search
    full_content: str     # Из extract (опционально)
    char_count: int
```

### 5.2. Source Lifecycle

```
1. WebSearch → creates sources [1], [2], [3]
   context.sources = {
       "url1": SourceData(number=1, snippet="...", full_content=""),
       "url2": SourceData(number=2, snippet="...", full_content="")
   }

2. ExtractPageContent → enriches existing sources
   context.sources["url1"].full_content = "..."
   # number остается 1!

3. CreateReport → inline citations
   "BMW X6 costs $75,000 [1] in US market [2]"
```

**Ключевые принципы**:
- URL как ключ → дедупликация
- Глобальная нумерация → стабильные citations
- Обновление без перезаписи → enrichment

---

## 6. Integration с LearnFlow

**Вызывается перед `planning_structure`** — детали интеграции прорабатываются отдельно.

**Input**:
- `input_content`: тема/вопрос пользователя
- `handwritten_notes`: распознанный текст (НЕ обрабатывается агентом, передается AS IS)

**Output**:
- `final_report`: текстовый отчет с inline citations [1], [2], [3]
- `sources`: список источников (для доступа из downstream узлов)

**Использование результатов**:
- `planning_structure` — учитывает research results при формировании структуры
- `section_generation` — обращается к конкретным источникам при генерации контента

---

## 7. MVP Scope

**Что реализуем**:
- Только Tavily web search (WebSearchTool + ExtractPageContentTool)
- Базовые reasoning и planning tools
- Structured output для всех decisions
- Source management с citations
- Интеграция в один узел перед `planning_structure`

**Что НЕ реализуем в MVP**:
- RAG по Telegram
- Document search (PDF, методички)
- Advanced trigger logic для определения необходимости поиска
- Multi-source synthesis strategies

---

## 8. Extensibility Design

Текущая архитектура позволяет добавление новых источников без изменения core logic:

**Расширение через BaseSourceTool**:
1. Создаем новый tool (например, `RAGSearchTool`)
2. Наследуем от `BaseSourceTool`
3. Реализуем `search()` и `extract()`
4. Добавляем в toolkit агента

**Расширение через новые tools**:
1. Определяем Pydantic schema нового tool
2. Добавляем в `NextStepTools` union
3. Реализуем `execute()` метод
4. Агент автоматически получает доступ

**Ключевой момент**: архитектура не "загнется" при добавлении источников — все через унифицированный интерфейс `BaseSourceTool` и динамический `NextStepTools` union.

---

## Summary

Research-агент — это **итеративный поисковик с адаптивным планированием**, который:
- Ищет актуальную информацию через Tavily (MVP)
- Адаптирует план на основе находок
- Агрегирует результаты с citations
- Передает результаты для влияния на структуру и генерацию
- Расширяется на другие источники через `BaseSourceTool` без изменения логики

**Реализация**: LangGraph node с внутренним циклом итераций через Command(goto="research_agent").
