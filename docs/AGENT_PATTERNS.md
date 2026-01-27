# 🧠 Архитектурные паттерны для построения AI-агентов

> **Системный анализ паттернов на основе SGR Deep Research**
>
> Документ описывает универсальные принципы построения интеллектуальных агентов, применимые к любым задачам (research, code generation, database queries, customer support, etc.)

---

## Содержание

1. [Трёхфазная архитектура цикла](#1-трёхфазная-архитектура-цикла)
2. [Эволюция контекста](#2-эволюция-контекста-ключевой-паттерн)
3. [Conversation History Pattern](#3-conversation-history-pattern)
4. [Structured Reasoning Pattern](#4-structured-reasoning-pattern)
5. [Adaptive Planning Pattern](#5-adaptive-planning-pattern)
6. [Resource Management Pattern](#6-resource-management-pattern)
7. [Interruption Pattern](#7-interruption-pattern-clarification-flow)
8. [Prompt Engineering Patterns](#8-prompt-engineering-patterns)
9. [Источники и цитирование](#9-источники-и-цитирование-pattern)
10. [Deterministic Execution Pattern](#10-deterministic-execution-pattern)
11. [Универсальные принципы](#-универсальные-принципы-для-любой-задачи)
12. [Примеры адаптации](#-примеры-адаптации-под-разные-задачи)

---

## 1. Трёхфазная архитектура цикла

### Паттерн: Thinking → Planning → Executing

```python
# Базовый цикл агента
while state not in FINISH_STATES:
    iteration += 1

    # ФАЗА 1: Reasoning (Что думает агент)
    reasoning = await self._reasoning_phase()

    # ФАЗА 2: Action Selection (Что делать)
    action_tool = await self._select_action_phase(reasoning)

    # ФАЗА 3: Execution (Выполнение)
    result = await self._action_phase(action_tool)

    # Обновление контекста
    context.iteration += 1
```

### Почему три фазы, а не одна?

```
❌ Плохо (Function Calling в один шаг):
User → LLM → [думает + выбирает инструмент одновременно] → Tool

Проблемы:
- LLM может выбрать инструмент, не продумав план
- Нет явного reasoning → сложно дебажить
- На маленьких моделях высокая вероятность ошибок в выборе

✅ Хорошо (SGR в три фазы):
User → LLM Reasoning → LLM Action Selection → Tool Execution

Преимущества:
- Явное мышление логируется и может быть проверено
- Можно валидировать reasoning перед действием
- Стабильнее на маленьких моделях (<32B параметров)
- Полная прозрачность процесса принятия решений
```

### Реализация фаз

```python
class BaseAgent:
    async def _reasoning_phase(self) -> ReasoningTool:
        """Фаза 1: Агент анализирует ситуацию и планирует."""
        # LLM генерирует структурированный reasoning
        return await llm.generate(response_format=ReasoningTool)

    async def _select_action_phase(self, reasoning: ReasoningTool) -> BaseTool:
        """Фаза 2: На основе reasoning выбирается конкретный инструмент."""
        # LLM выбирает tool из доступных
        return await llm.generate(response_format=Union[Tool1|Tool2|Tool3])

    async def _action_phase(self, tool: BaseTool) -> str:
        """Фаза 3: Детерминированное выполнение выбранного инструмента."""
        result = await tool(self.context)
        self.conversation.append({"role": "tool", "content": result})
        return result
```

**Применимость**: Любой агент с multi-step задачами

---

## 2. Эволюция контекста (ключевой паттерн)

### Паттерн: Context = Memory + State Machine

```python
class ResearchContext(BaseModel):
    # === STATE MACHINE ===
    state: AgentStatesEnum  # INITED → RESEARCHING → COMPLETED
    iteration: int          # Счётчик циклов

    # === ACCUMULATED KNOWLEDGE (растущая база знаний) ===
    searches: list[SearchResult]        # История поисков
    sources: dict[str, SourceData]      # Найденные источники (key=URL)

    # === RESOURCE COUNTERS ===
    searches_used: int
    clarifications_used: int

    # === CURRENT STEP ===
    current_step_reasoning: ReasoningTool  # Что агент думает СЕЙЧАС
    execution_result: str | None           # Финальный результат

    # === SYNCHRONIZATION (для interruption pattern) ===
    clarification_received: asyncio.Event
```

### Как контекст эволюционирует по итерациям:

```
Iteration 0: Инициализация
  context.state = INITED
  context.sources = {}
  context.searches = []
  context.iteration = 0

Iteration 1: После GeneratePlan
  context.current_step_reasoning = GeneratePlanTool(...)
  # План сохранён в conversation history

Iteration 2: После WebSearch
  context.sources = {
    "url1": SourceData(number=1, title="...", snippet="..."),
    "url2": SourceData(number=2, title="...", snippet="..."),
  }
  context.searches = [SearchResult(query="...", citations=[...])]
  context.searches_used = 1

Iteration 3: После ExtractPageContent
  context.sources["url1"].full_content = "полный текст страницы..."
  context.sources["url1"].char_count = 15000
  # Источник ОБНОВЛЁН, не перезаписан

Iteration 4: После CreateReport
  context.execution_result = "полный отчёт с цитатами [1][2]..."
  context.state = COMPLETED
```

### Принцип: **Context как растущая база знаний**

```python
# Каждый tool ЧИТАЕТ контекст И ОБНОВЛЯЕТ его
class WebSearchTool(BaseTool):
    async def __call__(self, context: ResearchContext) -> str:
        # 1. Читаем текущее состояние
        existing_sources = context.sources

        # 2. Выполняем действие
        new_sources = await self.search_service.search(self.query)

        # 3. ОБНОВЛЯЕМ контекст (не перезаписываем!)
        for source in new_sources:
            context.sources[source.url] = source
        context.searches_used += 1

        # 4. Возвращаем результат для conversation
        return self.format_results(new_sources)
```

### Ключевые принципы работы с контекстом:

1. **Иммутабельность на уровне ключей**: URL как ключ → нет дубликатов
2. **Мутабельность на уровне значений**: Обновление `full_content` существующего source
3. **Монотонное накопление**: Данные добавляются, но не удаляются
4. **Счётчики для управления**: `searches_used`, `clarifications_used`

**Применимость**: Любой агент, где нужна память о прошлых действиях

---

## 3. Conversation History Pattern

### Паттерн: LLM видит ВСЮ историю через conversation

```python
async def _prepare_context(self) -> list[dict]:
    """Подготовка контекста для LLM."""
    return [
        {"role": "system", "content": system_prompt},  # Инструкции
        *self.conversation,  # ВСЯ история взаимодействий
    ]
```

### Как строится conversation на протяжении выполнения:

```python
# Шаг 0: Инициализация
conversation = [
    {
        "role": "system",
        "content": "You are expert researcher with SGR capabilities..."
    },
    {
        "role": "user",
        "content": "Task: Research BMW X6 prices in Russia\nDate: 2025-01-10"
    }
]

# Шаг 1: Reasoning phase результат
conversation.append({
    "role": "assistant",
    "content": None,
    "tool_calls": [{
        "id": "1-reasoning",
        "function": {
            "name": "reasoning",
            "arguments": '{"reasoning_steps": [...], "remaining_steps": [...]}'
        }
    }]
})

# Шаг 2: Reasoning результат
conversation.append({
    "role": "tool",
    "content": '{"reasoning_steps": [...], "task_completed": false}',
    "tool_call_id": "1-reasoning"
})

# Шаг 3: Action selection
conversation.append({
    "role": "assistant",
    "content": "Search for BMW X6 pricing information",
    "tool_calls": [{
        "id": "1-action",
        "function": {
            "name": "websearch",
            "arguments": '{"query": "BMW X6 2025 Russia price", "max_results": 10}'
        }
    }]
})

# Шаг 4: Tool execution результат
conversation.append({
    "role": "tool",
    "content": "Search results:\n[1] BMW.com - $75,000\n[2] Auto.ru - 8,000,000₽\n...",
    "tool_call_id": "1-action"
})

# Шаг 5: Следующая итерация
# LLM видит ВСЁ: reasoning, tool calls, results
# Может ссылаться на sources [1], [2] в следующих действиях
```

### Принцип: **Conversation = Полная память агента**

```
Каждый шаг агента записывается в conversation:
- Reasoning → assistant message with tool_calls
- Tool selection → assistant message with tool_calls
- Tool result → tool message

LLM на каждой итерации видит:
✅ Что он думал раньше (reasoning history)
✅ Какие инструменты вызывал (tool_calls)
✅ Какие результаты получил (tool messages)
✅ Какие источники нашёл (через content в tool messages)
✅ Все предыдущие планы и адаптации

Это позволяет:
- Избегать повторных действий
- Ссылаться на прошлые результаты
- Строить на основе уже собранных данных
- Адаптировать план на основе истории
```

### Управление размером контекста:

```python
# Проблема: conversation растёт и может превысить context window

# Решение 1: Summarization
if len(conversation) > MAX_MESSAGES:
    summary = await llm.summarize(conversation[:N])
    conversation = [system, summary, *conversation[N:]]

# Решение 2: Sliding window
conversation = [system, *conversation[-MAX_MESSAGES:]]

# Решение 3: Selective retention (сохраняем важное)
important_messages = [m for m in conversation if is_important(m)]
recent_messages = conversation[-N:]
conversation = [system, *important_messages, *recent_messages]
```

**Применимость**: Любой multi-turn агент

---

## 4. Structured Reasoning Pattern

### Паттерн: ReasoningTool = Принудительное мышление

```python
class ReasoningTool(BaseTool):
    """Агент обязан заполнить все поля, что заставляет его думать структурированно."""

    # === CHAIN OF THOUGHT (принудительное пошаговое мышление) ===
    reasoning_steps: list[str] = Field(
        description="Step-by-step reasoning (brief, 1 sentence each)",
        min_length=2,  # Минимум 2 шага
        max_length=3   # Максимум 3 шага (лаконичность)
    )

    # === STATE ASSESSMENT (оценка текущей ситуации) ===
    current_situation: str = Field(
        description="Current research situation (2-3 sentences MAX)",
        max_length=300  # Заставляем быть лаконичным
    )

    plan_status: str = Field(
        description="Status of current plan (1 sentence)",
        max_length=150
    )

    enough_data: bool = Field(
        default=False,
        description="Sufficient data collected for comprehensive report?"
    )

    # === PLANNING (что дальше) ===
    remaining_steps: list[str] = Field(
        description="1-3 remaining steps (brief, action-oriented)",
        min_length=1,
        max_length=3
    )

    task_completed: bool = Field(
        description="Is the research task finished?"
    )
```

### Зачем нужна структурированная схема?

```
❌ Без структурированного reasoning (обычный text output):

LLM: "Надо поискать информацию о ценах"

Проблемы:
- Неясно ЧТО именно искать
- Неясно ЗАЧЕМ это нужно
- Неясно ЧТО делать дальше
- Нет оценки прогресса
- Сложно валидировать логику


✅ Со структурированным reasoning (Pydantic schema):

LLM: {
  "reasoning_steps": [
    "User asks about 2025 prices in Russia",
    "Need current market data from official sources",
    "Should verify if BMW X6 available in Russia"
  ],
  "current_situation": "No data collected yet. Need to start with web search for official BMW Russia pricing and availability.",
  "plan_status": "Initial planning complete, ready to search",
  "enough_data": false,
  "remaining_steps": [
    "Search BMW Russia official website",
    "Search major Russian car dealers",
    "Create price comparison report"
  ],
  "task_completed": false
}

Преимущества:
✅ Ясный пошаговый план
✅ Оценка текущей ситуации
✅ Статус выполнения плана
✅ Чёткие следующие шаги
✅ Можно программно проверить логику
✅ Полная прозрачность мышления
```

### Принцип: **Forced Introspection через схему**

```python
# Pydantic schema ЗАСТАВЛЯЕТ LLM:

1. Разбить мышление на шаги (reasoning_steps: min_length=2)
   → Нельзя ответить одним словом

2. Оценить текущую ситуацию (current_situation: max_length=300)
   → Должен быть краток и конкретен

3. Проверить статус плана (plan_status)
   → Осознанность текущего состояния

4. Решить, достаточно ли данных (enough_data: bool)
   → Явное решение о продолжении/завершении

5. Определить следующие шаги (remaining_steps: min/max)
   → Конкретный план действий

6. Оценить завершённость (task_completed: bool)
   → Явная точка выхода

Без схемы LLM может пропустить любой из этих шагов!
Схема = контракт на качество мышления
```

### Дополнительные техники для улучшения reasoning:

```python
# Техника 1: Ограничение длины → заставляет фокусироваться
reasoning_steps: list[str] = Field(max_length=3)  # Только главное

# Техника 2: Минимальные требования → заставляет думать глубже
reasoning_steps: list[str] = Field(min_length=2)  # Не менее 2 шагов

# Техника 3: Конкретные форматы в description
reasoning_steps: list[str] = Field(
    description="Step-by-step reasoning (format: 'Given X, therefore Y')"
)

# Техника 4: Множественные аспекты анализа
class DeepReasoning(BaseTool):
    what_i_know: list[str]      # Что уже известно
    what_i_dont_know: list[str] # Что неизвестно
    assumptions: list[str]       # Какие допущения делаю
    risks: list[str]            # Какие риски вижу
    next_steps: list[str]       # Что делать дальше
```

**Применимость**: Любой агент, где нужна прозрачность и качество мышления

---

## 5. Adaptive Planning Pattern

### Паттерн: GeneratePlan → Execute → AdaptPlan → Execute

```python
# Инструмент для создания начального плана
class GeneratePlanTool(BaseTool):
    """Generate initial research plan based on user request."""

    reasoning: str = Field(description="Justification for research approach")
    research_goal: str = Field(description="Primary research objective")
    planned_steps: list[str] = Field(
        description="List of 3-4 planned steps",
        min_length=3,
        max_length=4
    )
    search_strategies: list[str] = Field(
        description="Information search strategies",
        min_length=2,
        max_length=3
    )

# Инструмент для адаптации плана
class AdaptPlanTool(BaseTool):
    """Adapt research plan based on new findings."""

    reasoning: str = Field(
        description="Why plan needs adaptation based on new data"
    )
    original_goal: str = Field(description="Original research goal")
    new_goal: str = Field(description="Updated research goal")
    plan_changes: list[str] = Field(
        description="Specific changes made to plan",
        min_length=1,
        max_length=3
    )
    next_steps: list[str] = Field(
        description="Updated remaining steps",
        min_length=2,
        max_length=4
    )
```

### Пример эволюции плана:

```
Iteration 1: GeneratePlanTool
{
  "research_goal": "Find BMW X6 2025 prices in Russia",
  "planned_steps": [
    "Search BMW Russia official website",
    "Check major Russian car dealers (Avilon, Major, etc.)",
    "Compare prices across regions",
    "Create comprehensive price report"
  ],
  "search_strategies": [
    "Official manufacturer sources first",
    "Cross-verify with dealer networks",
    "Check automotive news for recent updates"
  ]
}

Iteration 2: WebSearchTool
→ Находит: "BMW officially exited Russian market in 2022 due to sanctions"

Iteration 3: AdaptPlanTool  ← КРИТИЧЕСКИЙ МОМЕНТ!
{
  "reasoning": "Initial plan assumed BMW X6 available in Russia. New data shows BMW exited market. Plan must shift from pricing to market exit analysis.",
  "original_goal": "Find BMW X6 2025 prices in Russia",
  "new_goal": "Explain BMW market exit and alternative purchase options",
  "plan_changes": [
    "Changed from price research to market situation analysis",
    "Added grey import market investigation",
    "Added information about parallel imports"
  ],
  "next_steps": [
    "Research BMW market exit details and timeline",
    "Search grey market import options",
    "Find parallel import dealers",
    "Explain legal and warranty implications"
  ]
}

Iteration 4-7: Execute new plan
→ Собирает данные по новому плану
→ Создаёт релевантный отчёт
```

### Почему план должен адаптироваться?

```
Начальный план = ГИПОТЕЗА основанная на вопросе пользователя
Реальные данные = ПРАВДА которая может противоречить гипотезе

Примеры несоответствий:
1. План: "Find prices"
   Данные: "Product discontinued"
   → Adapt: "Explain discontinuation and alternatives"

2. План: "Compare features of Product A vs B"
   Данные: "Product A and B merged"
   → Adapt: "Explain merger and new product line"

3. План: "Research company X financials"
   Данные: "Company X acquired by Y"
   → Adapt: "Explain acquisition and new structure"

Без адаптации агент будет:
❌ Следовать неактуальному плану
❌ Искать несуществующие данные
❌ Игнорировать важные новые находки
❌ Давать нерелевантные ответы
```

### Принцип: **План как гипотеза, данные как правда**

```python
# Pseudo-code для агента

initial_plan = generate_plan(user_question)  # Гипотеза

for step in initial_plan.steps:
    data = execute_step(step)

    if data_contradicts_plan(data, initial_plan):
        # Данные опровергли гипотезу
        adapted_plan = adapt_plan(
            original=initial_plan,
            new_findings=data,
            contradiction=explain_contradiction(data)
        )
        initial_plan = adapted_plan  # Обновляем гипотезу
```

### Когда триггерить адаптацию плана:

```python
class AdaptationTriggers:
    """Условия для адаптации плана."""

    @staticmethod
    def should_adapt(context: Context) -> bool:
        return any([
            # 1. Данные противоречат плану
            context.found_contradictory_data,

            # 2. Обнаружена новая важная информация
            context.discovered_new_aspect,

            # 3. Исходный подход не работает
            context.consecutive_failed_searches > 2,

            # 4. Scope изменился
            context.user_provided_clarification,

            # 5. Временные ограничения
            context.searches_remaining < 2 and not context.enough_data,
        ])
```

**Применимость**: Любая задача где план может устареть при получении новых данных

---

## 6. Resource Management Pattern

### Паттерн: Лимиты через счётчики + динамическое управление инструментами

```python
class SGRResearchAgent(BaseAgent):
    def __init__(
        self,
        task: str,
        max_searches: int = 4,
        max_clarifications: int = 3,
        max_iterations: int = 10,
    ):
        self.max_searches = max_searches
        self.max_clarifications = max_clarifications
        self.max_iterations = max_iterations
        self.toolkit = [
            WebSearchTool,
            ExtractPageContentTool,
            ClarificationTool,
            GeneratePlanTool,
            AdaptPlanTool,
            CreateReportTool,
            FinalAnswerTool,
        ]

    async def _prepare_tools(self):
        """Динамическое управление доступными инструментами."""
        tools = set(self.toolkit)

        # КРИТИЧЕСКОЕ ОГРАНИЧЕНИЕ: Максимум итераций
        if self._context.iteration >= self.max_iterations:
            # Агент ОБЯЗАН завершить работу
            tools = {CreateReportTool, FinalAnswerTool}
            return tools

        # Ограничение на clarifications
        if self._context.clarifications_used >= self.max_clarifications:
            tools -= {ClarificationTool}
            # Больше не может спрашивать, должен додумать сам

        # Ограничение на searches
        if self._context.searches_used >= self.max_searches:
            tools -= {WebSearchTool}
            # Должен работать с уже собранными данными

        return tools
```

### Как работает механизм ограничений:

```
Iteration 1: searches_used=0, clarifications_used=0
  Available tools: [WebSearch, Extract, Clarification, Plan, Adapt, Report, Final]
  → Агент может делать всё

Iteration 2: searches_used=1
  Available tools: [WebSearch, Extract, Clarification, Plan, Adapt, Report, Final]
  → Ещё 3 поиска доступны

Iteration 3: searches_used=4 (достигнут лимит)
  Available tools: [Extract, Clarification, Plan, Adapt, Report, Final]
  → WebSearchTool ИСЧЕЗАЕТ из списка!
  → LLM не может выбрать поиск
  → Вынужден работать с существующими данными

Iteration 4: clarifications_used=3 (достигнут лимит)
  Available tools: [Extract, Plan, Adapt, Report, Final]
  → ClarificationTool ИСЧЕЗАЕТ
  → Больше не может спрашивать пользователя

Iteration 10: iteration >= max_iterations (критический лимит)
  Available tools: [Report, Final]
  → ВСЕ инструменты кроме завершающих УДАЛЕНЫ
  → Агент ОБЯЗАН завершить работу
```

### Зачем ограничения?

```
БЕЗ ограничений (problems):
❌ Агент может искать бесконечно → расходы на API ↑↑↑
❌ Агент может задавать вопросы вечно → плохой UX
❌ Агент может зациклиться на одном действии → не завершит задачу
❌ Нет гарантии завершения → агент может работать часами

С ограничениями (benefits):
✅ После N поисков → должен анализировать собранное
✅ После M clarifications → должен работать с тем что есть
✅ После K итераций → ОБЯЗАН выдать результат
✅ Предсказуемая стоимость выполнения
✅ Гарантированное завершение
✅ Формирует дисциплинированное поведение
```

### Принцип: **Ограничения формируют поведение через окружение**

```python
# Это НЕ жёсткие правила ("не делай X"), а мягкое управление через доступность

# ❌ Жёсткие правила (хрупкие):
if action == WebSearchTool and searches_used >= MAX:
    raise Error("Too many searches!")
# Проблема: LLM всё равно может попытаться, нужна обработка ошибок

# ✅ Ограничения через окружение (robust):
available_tools = all_tools - {WebSearchTool}
action = llm.choose(available_tools)
# LLM физически не может выбрать WebSearchTool
# Автоматически выбирает из доступных альтернатив
```

### Продвинутые стратегии управления ресурсами:

```python
# Стратегия 1: Прогрессивное ограничение
def _prepare_tools(self):
    tools = set(self.toolkit)

    # Ранние итерации: все инструменты доступны
    if self.context.iteration < 3:
        return tools

    # Средние итерации: ограничиваем дорогие операции
    if self.context.iteration < 7:
        if self.context.searches_used >= 3:
            tools -= {WebSearchTool}
        return tools

    # Поздние итерации: только завершение
    return {CreateReportTool, FinalAnswerTool}


# Стратегия 2: Динамические лимиты на основе progress
def _prepare_tools(self):
    tools = set(self.toolkit)

    # Если прогресс хороший → разрешаем больше поисков
    if self.context.sources_count > 10 and self.context.enough_data:
        # Уже достаточно данных, ограничиваем поиск
        tools -= {WebSearchTool}

    # Если прогресс плохой → строже с ресурсами
    if self.context.iteration > 5 and self.context.sources_count < 3:
        # Много итераций но мало данных → что-то не так
        # Заставляем завершить с тем что есть
        tools = {CreateReportTool, FinalAnswerTool}

    return tools


# Стратегия 3: Cost-based management
def _prepare_tools(self):
    tools = set(self.toolkit)

    # Трекинг стоимости
    estimated_cost = (
        self.context.searches_used * SEARCH_COST +
        self.context.llm_calls * LLM_COST +
        self.context.extractions * EXTRACT_COST
    )

    # Если близки к бюджету → только дешёвые операции
    if estimated_cost > BUDGET * 0.8:
        expensive_tools = {WebSearchTool, ExtractPageContentTool}
        tools -= expensive_tools

    return tools
```

**Применимость**: Любой агент с ограничениями на стоимость, время или ресурсы

---

## 7. Interruption Pattern (Clarification Flow)

### Паттерн: Agent Pause → Wait → Resume

```python
# Execution loop с поддержкой interruption
async def execute(self):
    while self._context.state not in FINISH_STATES:
        self._context.iteration += 1

        reasoning = await self._reasoning_phase()
        action_tool = await self._select_action_phase(reasoning)
        await self._action_phase(action_tool)

        # КРИТИЧЕСКИЙ МОМЕНТ: Проверка на clarification
        if isinstance(action_tool, ClarificationTool):
            self.logger.info("⏸️ Research paused - waiting for user input")

            # Изменяем состояние
            self._context.state = AgentStatesEnum.WAITING_FOR_CLARIFICATION

            # Сбрасываем event flag
            self._context.clarification_received.clear()

            # БЛОКИРУЕМ выполнение до получения ответа
            await self._context.clarification_received.wait()

            # После получения ответа продолжаем
            continue

# Метод для предоставления clarification извне
async def provide_clarification(self, clarifications: str):
    """Вызывается внешним кодом (API, UI) для продолжения работы."""

    # Добавляем ответ пользователя в conversation
    self.conversation.append({
        "role": "user",
        "content": f"CLARIFICATIONS:\n{clarifications}"
    })

    # Обновляем счётчики
    self._context.clarifications_used += 1

    # РАЗБУЖИВАЕМ агента
    self._context.clarification_received.set()

    # Возвращаем в рабочее состояние
    self._context.state = AgentStatesEnum.RESEARCHING

    self.logger.info(f"✅ Clarification received, resuming research")
```

### Диаграмма состояний:

```
┌─────────────────┐
│   RESEARCHING   │
└────────┬────────┘
         │
         │ Agent calls ClarificationTool
         │
         v
┌──────────────────────────────┐
│ WAITING_FOR_CLARIFICATION    │ ← Agent blocked on await event.wait()
│                              │
│ Context preserved:           │
│ - conversation history       │
│ - collected sources          │
│ - search results             │
│ - current plan               │
└──────────────┬───────────────┘
               │
               │ External call: provide_clarification()
               │ → event.set()
               │
               v
┌─────────────────┐
│   RESEARCHING   │ ← Agent resumes from next iteration
└─────────────────┘
```

### Пример использования через API:

```python
# Client-side code
import asyncio
from openai import OpenAI

client = OpenAI(base_url="http://localhost:8010/v1", api_key="dummy")

# Step 1: Start research
print("Starting research...")
response = client.chat.completions.create(
    model="sgr-agent",
    messages=[{"role": "user", "content": "Research AI market trends"}],
    stream=True
)

agent_id = None
questions = []

# Process streaming response
for chunk in response:
    # Извлекаем agent_id из model field
    if chunk.model and "_" in chunk.model:
        agent_id = chunk.model

    # Проверяем на clarification request
    if chunk.choices[0].delta.tool_calls:
        for tc in chunk.choices[0].delta.tool_calls:
            if tc.function.name == "clarification":
                questions = json.loads(tc.function.arguments)["questions"]

    # Выводим content
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")

# Step 2: If clarification needed, provide it
if questions and agent_id:
    print(f"\n\nAgent asked: {questions}")

    user_answer = "Focus on LLM market, global perspective, 2024-2025"

    # Continue with SAME agent_id as model
    response = client.chat.completions.create(
        model=agent_id,  # ВАЖНО: используем agent_id!
        messages=[{"role": "user", "content": user_answer}],
        stream=True
    )

    for chunk in response:
        if chunk.choices[0].delta.content:
            print(chunk.choices[0].delta.content, end="")
```

### Принцип: **Agent как долгоживущий процесс**

```python
# Agent НЕ завершается при необходимости clarification
# Он ПРИОСТАНАВЛИВАЕТСЯ и ЖДЁТ внешнего ввода через asyncio.Event

# Это позволяет:

1. Сохранить весь контекст:
   - Conversation history
   - Collected sources
   - Search results
   - Current reasoning
   - Execution plan

2. Продолжить с того же места:
   - Следующая итерация цикла
   - С обновлённым conversation (добавлен ответ пользователя)
   - Со всеми накопленными данными

3. Реализовать multi-turn interaction:
   - Агент может спросить несколько раз
   - Может адаптировать вопросы на основе ответов
   - Может уточнять детали по мере работы

4. Поддерживать асинхронность:
   - Agent живёт в background task
   - API endpoint возвращает streaming response
   - User может ответить когда удобно
   - Agent продолжит автоматически
```

### Synchronization через asyncio.Event:

```python
# Внутри ResearchContext
class ResearchContext(BaseModel):
    clarification_received: asyncio.Event = Field(
        default_factory=asyncio.Event
    )

# Agent execution loop
await self._context.clarification_received.wait()
# Блокируется здесь до тех пор пока event не будет set()

# External API call
self._context.clarification_received.set()
# Разблокирует агента
```

**Применимость**: Любой интерактивный агент, требующий пользовательского ввода

---

## 8. Prompt Engineering Patterns

### Паттерн 1: Системный промпт как поведенческий контракт

```python
# prompts/system_prompt.txt

# Структура промпта:
# 1. Main Task Guidelines
# 2. Language Adaptation
# 3. Core Principles
# 4. Precision Guidelines
# 5. Tool Usage Guidelines
```

#### Пример ключевых секций:

```text
<MAIN_TASK_GUIDELINES>
You are an expert researcher with adaptive planning and schema-guided-reasoning capabilities.
You get the research task and you need to do research and generate answer.
</MAIN_TASK_GUIDELINES>

<DATE_GUIDELINES>
PAY ATTENTION TO THE DATE INSIDE THE USER REQUEST
DATE FORMAT: YYYY-MM-DD HH:MM:SS (ISO 8601)
IMPORTANT: The date above is in YYYY-MM-DD format (Year-Month-Day).
For example, 2025-10-03 means October 3rd, 2025, NOT March 10th.
</DATE_GUIDELINES>

<IMPORTANT_LANGUAGE_GUIDELINES>
LANGUAGE ADAPTATION: Always respond and create reports in the SAME LANGUAGE as the user's request.
If user writes in Russian - respond in Russian, if in English - respond in English.
</IMPORTANT_LANGUAGE_GUIDELINES>

<CORE_PRINCIPLES>
1. Memorize plan you generated in first step and follow the task inside your plan
2. Adapt plan when new data contradicts initial assumptions
3. Search queries in SAME LANGUAGE as user request
4. Final Answer ENTIRELY in SAME LANGUAGE as user request
</CORE_PRINCIPLES>

<PRECISION_GUIDELINES>
CRITICAL FOR FACTUAL ACCURACY:
When answering questions about specific dates, numbers, versions, or names:
1. EXACT VALUES: Extract the EXACT value from sources (day, month, year for dates)
2. VERIFY YEAR: If question mentions a specific year, verify content is about SAME year
3. CROSS-VERIFICATION: When sources contradict, prefer:
   - Official sources and primary documentation
   - Search result snippets that DIRECTLY answer the question
   - Multiple independent sources confirming same fact
4. DATE PRECISION: Pay attention to exact dates (October 21 ≠ October 22)
5. NUMBER PRECISION: For numbers/versions, exact match required
6. SNIPPET PRIORITY: If snippet clearly states answer, trust it unless extract proves wrong
7. TEMPORAL VALIDATION: When extracting page content, check if page shows data for correct time period
</PRECISION_GUIDELINES>
```

### Паттерн 2: Tool descriptions как micro-prompts

```python
class WebSearchTool(BaseTool):
    """Search the web for real-time information about any topic.

    Use this tool when you need up-to-date information that might not be available
    in your training data, or when you need to verify current facts.

    The search results will include relevant snippets and URLs from web pages.

    Use for: Public information, news, market trends, external APIs, general knowledge
    Returns: Page titles, URLs, and short snippets (100 characters)
    Best for: Quick overview, finding relevant pages

    Usage:
        - Use SPECIFIC terms and context in queries
        - For acronyms, add context: "SGR Schema-Guided Reasoning"
        - Use quotes for exact phrases: "Structured Output OpenAI"
        - Search queries in SAME LANGUAGE as user request
        - For date/number questions, include specific year/context in query
        - Use ExtractPageContentTool to get full content from found URLs

    IMPORTANT FOR FACTUAL QUESTIONS:
        - Search snippets often contain direct answers - check them carefully
        - For questions with specific dates/numbers, snippets may be more accurate than full pages
        - If snippet directly answers the question, you may not need to extract full page
    """

    reasoning: str = Field(description="Why this search is needed and what to expect")
    query: str = Field(description="Search query in same language as user request")
    max_results: int = Field(default=10, description="Maximum results", ge=1, le=10)
```

### Паттерн 3: Field descriptions как inline guidance

```python
class ReasoningTool(BaseTool):
    reasoning_steps: list[str] = Field(
        description="Step-by-step reasoning (brief, 1 sentence each)",
        # ↑ Говорит КАК форматировать: кратко, по 1 предложению
        min_length=2,
        max_length=3
    )

    current_situation: str = Field(
        description="Current research situation (2-3 sentences MAX)",
        # ↑ Явное ограничение на длину в описании
        max_length=300
    )

    remaining_steps: list[str] = Field(
        description="1-3 remaining steps (brief, action-oriented)",
        # ↑ Указывает формат: краткий, действия
        min_length=1,
        max_length=3
    )
```

### Принцип: **Многоуровневая система промптов**

```
Level 1: System Prompt (global behavior)
  → Общие правила поведения агента
  → Язык, стиль, принципы
  → Применяется ко всем действиям

Level 2: Tool Description (tool-specific behavior)
  → Правила использования конкретного инструмента
  → Когда использовать, как использовать
  → Применяется при выборе и использовании tool

Level 3: Field Description (field-specific format)
  → Правила заполнения конкретного поля
  → Формат, длина, стиль
  → Применяется к каждому полю

Вместе они формируют:
- КАК агент думает (reasoning patterns)
- ЧТО агент делает (tool selection logic)
- КАК агент обрабатывает данные (precision rules)
- КАК агент форматирует output (formatting rules)
```

### Техники эффективного промптинга:

```python
# Техника 1: Explicit constraints в описании
"""
description="Current situation (2-3 sentences MAX)"
# Вместо: "Current situation"
# Явно указываем ограничение
```

# Техника 2: Примеры в описании
"""
description="Reasoning steps (format: 'Given X, therefore Y')"
# Показываем желаемый формат
```

# Техника 3: Negative instructions
"""
IMPORTANT FOR FACTUAL QUESTIONS:
- If snippet directly answers, you may NOT need to extract full page
# Говорим что НЕ делать
```

# Техника 4: Priority guidelines
"""
CROSS-VERIFICATION: When sources contradict, prefer:
1. Official sources (highest priority)
2. Search snippets with direct answers
3. Multiple independent confirmations
# Явная иерархия приоритетов
```

# Техника 5: Context-specific rules
"""
<DATE_GUIDELINES>
DATE FORMAT: YYYY-MM-DD (Year-Month-Day)
IMPORTANT: 2025-10-03 means October 3rd, NOT March 10th
</DATE_GUIDELINES>
# Предотвращаем типичные ошибки
```

**Применимость**: Любой агент с LLM

---

## 9. Источники и цитирование Pattern

### Паттерн: Numbered sources + inline citations

```python
class SourceData(BaseModel):
    """Модель для хранения источника информации."""
    number: int  # [1], [2], [3] - для цитирования
    title: str | None = Field(default="Untitled")
    url: str
    snippet: str = Field(default="")        # Из search results
    full_content: str = Field(default="")   # Из extract
    char_count: int = Field(default=0)

    def __str__(self):
        return f"[{self.number}] {self.title} - {self.url}"
```

### Workflow управления источниками:

```python
# Шаг 1: WebSearch создаёт источники с номерами
class WebSearchTool:
    async def __call__(self, context: ResearchContext) -> str:
        # Получаем results из API
        raw_sources = await self._search_service.search(self.query)

        # ВАЖНО: Нумерация продолжается, не начинается заново
        sources = rearrange_sources(
            raw_sources,
            starting_number=len(context.sources) + 1
        )

        # Сохраняем в контекст (URL как ключ)
        for source in sources:
            context.sources[source.url] = source

        # Возвращаем formatted results
        return self.format_results(sources)

# Результат:
# Search 1: creates sources [1], [2], [3]
# Search 2: creates sources [4], [5], [6]  ← Продолжает нумерацию!
```

```python
# Шаг 2: ExtractPageContent обогащает источники
class ExtractPageContentTool:
    async def __call__(self, context: ResearchContext) -> str:
        # Получаем полный контент
        enriched_sources = await self._search_service.extract(self.urls)

        # ОБНОВЛЯЕМ существующие sources, не создаём новые
        for source in enriched_sources:
            if source.url in context.sources:
                # URL уже существует - UPDATE
                existing = context.sources[source.url]
                existing.full_content = source.full_content
                existing.char_count = source.char_count
            else:
                # Новый URL (edge case) - ADD
                source.number = len(context.sources) + 1
                context.sources[source.url] = source

        return self.format_content(enriched_sources)

# Результат:
# Source [1] теперь имеет:
# - .snippet (из search)
# - .full_content (из extract)
# Номер остался тот же!
```

```python
# Шаг 3: CreateReport использует numbered citations
class CreateReportTool:
    content: str = Field(
        description="""
        Write comprehensive report with inline citations [1], [2], [3].
        MANDATORY: Include citation after EVERY factual claim.
        Example: 'The system uses Vue.js [1] and Python [2].'
        NOT: 'The system uses Vue.js and Python.'
        """
    )

    async def __call__(self, context: ResearchContext) -> str:
        # LLM генерирует content с inline citations
        report_content = self.content  # "BMW X6 costs $75,000 [1] in US [2]"

        # Добавляем список источников
        sources_section = "\n".join([
            str(source) for source in context.sources.values()
        ])

        full_report = f"""
{report_content}

---

## Источники / Sources

{sources_section}
"""
        return full_report
```

### Принцип: **Sources как иммутабельный словарь с mutable значениями**

```python
# URL как ключ → предотвращает дубликаты
context.sources = {
    "https://bmw.com/x6": SourceData(
        number=1,
        title="BMW X6 Official",
        url="https://bmw.com/x6",
        snippet="Starting at $75,000...",
        full_content=""  # Пока пусто
    ),
    "https://auto.ru/bmw": SourceData(
        number=2,
        title="Auto.ru BMW",
        url="https://auto.ru/bmw",
        snippet="В России не продаётся...",
        full_content=""
    )
}

# После extract того же URL - UPDATE, не ADD
context.sources["https://bmw.com/x6"].full_content = "Full page text..."
# number остаётся = 1!

# Преимущества:
# ✅ Нет дубликатов URL
# ✅ Стабильные номера для цитирования
# ✅ Можно обогащать source в несколько этапов
# ✅ LLM может ссылаться на [1] на любой итерации
```

### Правила нумерации:

```python
def rearrange_sources(
    sources: list[SourceData],
    starting_number: int
) -> list[SourceData]:
    """
    Правила:
    1. Нумерация глобальная, не per-search
    2. Начинается с len(existing_sources) + 1
    3. Монотонно возрастает
    4. Никогда не переиспользуется
    """
    for i, source in enumerate(sources):
        source.number = starting_number + i
    return sources
```

### Валидация citations в отчёте:

```python
def validate_citations(report: str, sources: dict) -> bool:
    """Проверка что все цитаты валидны."""
    # Найти все [N] в тексте
    citations = re.findall(r'\[(\d+)\]', report)

    # Проверить что все цитаты существуют
    for citation in citations:
        citation_num = int(citation)
        if not any(s.number == citation_num for s in sources.values()):
            return False

    return True
```

**Применимость**: Любой агент, генерирующий контент с ссылками на источники

---

## 10. Deterministic Execution Pattern

### Паттерн: Structured Output гарантирует валидный выбор

```python
# ФАЗА 1: Reasoning (LLM думает)
async def _reasoning_phase(self) -> NextStepToolStub:
    response = await llm.generate(
        response_format=NextStepTools  # Union[Tool1 | Tool2 | Tool3 | ...]
    )
    return response.parsed  # ВСЕГДА один из валидных Tool objects

# ФАЗА 2: Execute (ДЕТЕРМИНИРОВАННО, без второго LLM call)
async def _action_phase(self, tool: BaseTool) -> str:
    result = await tool(context)  # Просто вызываем метод
    return result
```

### Сравнение с традиционным Function Calling:

```python
# ❌ Function Calling с tool_choice="auto" (недетерминированно)

response = await llm.generate(
    tools=[Tool1, Tool2, Tool3],
    tool_choice="auto"  # LLM САМА решает вызывать ли tool
)

# Возможные результаты:
# 1. {"tool_calls": [Tool1(...)]}  ✅ OK
# 2. {"tool_calls": null, "content": "Let me think..."}  ❌ Не вызвал tool
# 3. {"tool_calls": [InvalidTool(...)]}  ❌ Несуществующий tool
# 4. {"tool_calls": [Tool1(param=invalid)]}  ❌ Невалидные параметры

# Проблемы с маленькими моделями (<32B):
# - ~15-25% случаев: tool_calls=null (модель решила не вызывать)
# - ~10% случаев: невалидные параметры
# - Нужна обработка всех edge cases

# ✅ Structured Output (детерминированно)

NextStepTools = Union[Tool1 | Tool2 | Tool3]  # Discriminated union

response = await llm.generate(
    response_format=NextStepTools  # ОБЯЗАН вернуть один из tools
)

# Гарантированный результат:
# - Всегда валидный Tool object
# - Pydantic валидация всех полей
# - Невозможно вернуть null
# - Невозможно вернуть текст вместо tool
# - Невозможно вернуть tool который не в union

# Даже маленькие модели:
# - Не могут "отказаться" вызвать tool
# - Не могут вернуть невалидные параметры
# - Pydantic выбросит ошибку ДО выполнения
```

### Как работает NextStepToolsBuilder:

```python
class NextStepToolsBuilder:
    """Динамическое построение Union type из списка tools."""

    @classmethod
    def _create_discriminant_tool(cls, tool_class: Type[T]) -> Type[BaseModel]:
        """Добавляет discriminator field к tool."""
        return create_model(
            f"D_{tool_class.__name__}",
            __base__=(tool_class, DiscriminantToolMixin),
            tool_name_discriminator=(
                Literal[tool_class.tool_name],
                Field(..., description="Tool name")
            )
        )

    @classmethod
    def _create_tool_types_union(cls, tools_list: list[Type[T]]) -> Type:
        """Создаёт Union из всех tools."""
        discriminant_tools = [
            cls._create_discriminant_tool(tool) for tool in tools_list
        ]
        # Используем reduce для создания Union
        union = reduce(operator.or_, discriminant_tools)
        return Annotated[union, Field(discriminator="tool_name_discriminator")]

    @classmethod
    def build_NextStepTools(cls, tools_list: list[Type[T]]):
        """Финальный builder."""
        return create_model(
            "NextStepTools",
            __base__=NextStepToolStub,
            function=(
                cls._create_tool_types_union(tools_list),
                Field(description="Select appropriate tool")
            )
        )

# Использование:
NextStepTools = NextStepToolsBuilder.build_NextStepTools([
    WebSearchTool,
    ExtractPageContentTool,
    CreateReportTool,
    FinalAnswerTool
])

# Результат: Pydantic model с Union type
# LLM должен вернуть JSON который матчится с ОДНИМ из tools
```

### Преимущества Structured Output:

```python
# 1. Гарантированная валидность
try:
    tool = NextStepTools.model_validate(llm_response)
    # Если дошли сюда - tool 100% валидный
except ValidationError as e:
    # Поймаем ДО выполнения, а не после
    handle_error(e)

# 2. Автоматическая типизация
tool: BaseTool = response.function
# IDE знает что это BaseTool, есть autocomplete

# 3. Discriminated union для правильного парсинга
{
  "tool_name_discriminator": "websearch",  # LLM указывает какой tool
  "query": "BMW X6 price",
  "max_results": 10
}
# Pydantic автоматически выберет WebSearchTool

# 4. Невозможно пропустить обязательные поля
class WebSearchTool:
    query: str  # Required, нет default

# LLM ОБЯЗАН заполнить query, иначе ValidationError

# 5. Автоматические constraints
class WebSearchTool:
    max_results: int = Field(ge=1, le=10)

# LLM не может вернуть max_results=100
# Pydantic выбросит ValidationError
```

### Принцип: **Structured Output как контракт выполнения**

```
LLM НЕ МОЖЕТ:
❌ Вернуть None вместо tool
❌ Вернуть текст вместо JSON
❌ Вернуть tool который не в union
❌ Пропустить required поля
❌ Нарушить constraints (ge, le, max_length, etc.)
❌ Вернуть невалидный тип (str вместо int)

Pydantic ГАРАНТИРУЕТ:
✅ Валидный Tool object
✅ Все required поля заполнены
✅ Все типы корректны
✅ Все constraints соблюдены
✅ Можно сразу выполнять, без проверок

Результат:
- Нет defensive programming
- Нет try/except для каждого поля
- Код чище и надёжнее
- Работает даже на маленьких моделях
```

**Применимость**: Любой агент на маленьких моделях или требующий гарантий валидности

---

## 📚 Универсальные принципы для любой задачи

### 1. Трёхфазный цикл execution

```python
class UniversalAgent:
    async def execute(self):
        while not self.is_done():
            # Phase 1: Think - что делать?
            reasoning = await self.think(self.context)

            # Phase 2: Plan - какой инструмент использовать?
            action = await self.select_action(reasoning)

            # Phase 3: Execute - выполнить
            result = await action.execute(self.context)

            # Phase 4: Update - обновить знания
            self.context.update(result)
            self.iteration += 1
```

**Применимо к**: Code agent, DB agent, customer support, DevOps agent, любому агенту

---

### 2. Context = Growing Knowledge Base

```python
class UniversalContext(BaseModel):
    # State machine
    state: StateEnum
    iteration: int

    # Accumulated artifacts (растущая база знаний)
    # ↓ Настройте под свою domain
    artifacts: dict[str, Any]

    # Resource counters для управления
    resource_usage: dict[str, int]

    # Current step для прозрачности
    current_reasoning: Any

    # Final result
    result: Any | None
```

**Примеры адаптации**:
- **Code agent**: `artifacts = {filepath: CodeFile}`
- **DB agent**: `artifacts = {query_id: QueryResult}`
- **Support agent**: `artifacts = {ticket_id: Conversation}`
- **DevOps agent**: `artifacts = {server_id: ServerState}`

---

### 3. Conversation = Full Memory

```python
class UniversalAgent:
    def __init__(self):
        self.conversation = []

    async def _prepare_llm_context(self):
        return [
            {"role": "system", "content": self.instructions},
            *self.conversation  # LLM видит ВСЮ историю
        ]

    async def _add_to_history(self, role, content):
        self.conversation.append({
            "role": role,
            "content": content
        })
```

**Применимо к**: Любой multi-turn агент

---

### 4. Structured Reasoning для прозрачности

```python
class DomainReasoning(BaseModel):
    # Что я анализирую
    analysis: list[str] = Field(min_length=2, max_length=4)

    # Что я знаю / не знаю
    known_facts: list[str]
    unknowns: list[str]

    # Текущее состояние
    current_state: str = Field(max_length=300)

    # План действий
    next_steps: list[str] = Field(min_length=1, max_length=3)

    # Готовность завершить
    ready_to_complete: bool
    completion_confidence: Literal["high", "medium", "low"]
```

**Применимо к**: Любой агент где нужна прозрачность мышления

---

### 5. Adaptive Planning

```python
class InitialPlan(BaseTool):
    goal: str
    approach: str
    steps: list[str]
    expected_challenges: list[str]

class AdaptPlan(BaseTool):
    original_goal: str
    new_goal: str
    reason_for_adaptation: str
    discovered_facts: list[str]
    plan_changes: list[str]
    updated_steps: list[str]
```

**Применимо к**: Любая задача где план может устареть

---

### 6. Resource Management через dynamic tools

```python
class ResourceManagedAgent:
    async def _prepare_tools(self, context):
        tools = set(self.all_tools)

        # Динамическое отключение по лимитам
        if context.expensive_calls >= MAX_EXPENSIVE:
            tools -= {ExpensiveTool}

        if context.iteration >= MAX_ITERATIONS:
            tools = {FinalAnswerTool}  # Только завершение

        # Динамическое включение по progress
        if context.has_enough_data():
            tools.add(CreateReportTool)

        return tools
```

**Применимо к**: Любой агент с ограничениями

---

### 7. Interruption для интерактивности

```python
class InteractiveAgent:
    async def execute(self):
        while not self.done:
            action = await self.decide_action()

            if isinstance(action, AskUserTool):
                # Pause and wait
                self.state = "WAITING_FOR_USER"
                self.user_input_event.clear()
                await self.user_input_event.wait()

            await action.execute()

    async def provide_input(self, user_input: str):
        self.conversation.append({
            "role": "user",
            "content": user_input
        })
        self.user_input_event.set()
```

**Применимо к**: Любой интерактивный агент

---

### 8. Deterministic Execution через Structured Output

```python
# Определяем union всех возможных действий
ActionUnion = Union[
    SearchAction,
    AnalyzeAction,
    CreateAction,
    CompleteAction
]

# LLM обязана выбрать одно из действий
async def decide_action(self):
    response = await llm.generate(
        response_format=ActionUnion
    )
    return response.parsed  # Гарантированно валидный Action
```

**Применимо к**: Любой агент, особенно на маленьких моделях

---

## 🔧 Примеры адаптации под разные задачи

### Пример 1: SQL Query Generator Agent

```python
# === Context ===
class SQLContext(BaseModel):
    state: StateEnum
    iteration: int

    # Domain-specific artifacts
    schema: dict[str, TableSchema]  # Вместо sources
    queries: list[GeneratedQuery]   # Вместо searches
    query_results: dict[str, DataFrame]

    # Resource counters
    schema_inspections: int
    query_attempts: int

# === Tools ===
class InspectSchemaTool(BaseTool):
    """Аналог WebSearchTool - исследование domain."""
    table_names: list[str]

    async def __call__(self, context: SQLContext):
        schema = await db.get_schema(self.table_names)
        context.schema.update(schema)
        context.schema_inspections += 1
        return self.format_schema(schema)

class GenerateQueryTool(BaseTool):
    """Аналог CreateReportTool - финальный артефакт."""
    reasoning: str
    sql_query: str
    expected_columns: list[str]

    async def __call__(self, context: SQLContext):
        result = await db.execute(self.sql_query)
        context.queries.append(GeneratedQuery(
            sql=self.sql_query,
            result=result
        ))
        context.query_attempts += 1
        return self.format_result(result)

class AskUserClarification(BaseTool):
    """То же что ClarificationTool."""
    questions: list[str]
    unclear_columns: list[str]

# === Reasoning ===
class SQLReasoning(BaseTool):
    analysis: list[str] = Field(min_length=2, max_length=3)
    schema_understood: bool
    query_ready: bool
    remaining_steps: list[str]
    task_completed: bool

# === Agent ===
class SQLAgent(BaseAgent):
    name = "sql_agent"

    def __init__(self, question: str):
        self.context = SQLContext()
        self.toolkit = [
            InspectSchemaTool,
            GenerateQueryTool,
            AskUserClarification,
            SQLReasoning,
            FinalAnswerTool
        ]
        self.max_schema_inspections = 5
        self.max_query_attempts = 3

    async def _prepare_tools(self):
        tools = set(self.toolkit)

        # Resource management
        if self.context.schema_inspections >= self.max_schema_inspections:
            tools -= {InspectSchemaTool}

        if self.context.query_attempts >= self.max_query_attempts:
            tools = {FinalAnswerTool}

        return tools

# Использование:
agent = SQLAgent(question="Show me top 5 customers by revenue in 2024")
await agent.execute()
print(agent.context.queries[-1].sql)  # Финальный SQL запрос
```

---

### Пример 2: Code Review Agent

```python
# === Context ===
class CodeReviewContext(BaseModel):
    state: StateEnum
    iteration: int

    # Domain artifacts
    files_analyzed: dict[str, FileAnalysis]
    issues_found: list[Issue]
    suggestions: list[Suggestion]

    # Counters
    files_read: int
    static_analysis_runs: int

# === Tools ===
class ReadFileTool(BaseTool):
    """Аналог WebSearch - сбор данных."""
    file_paths: list[str]

    async def __call__(self, context: CodeReviewContext):
        for path in self.file_paths:
            content = await read_file(path)
            context.files_analyzed[path] = FileAnalysis(
                path=path,
                content=content,
                loc=len(content.splitlines())
            )
        context.files_read += len(self.file_paths)
        return self.format_files(context.files_analyzed)

class StaticAnalysisTool(BaseTool):
    """Аналог ExtractPageContent - глубокий анализ."""
    file_paths: list[str]
    analyzers: list[str] = ["pylint", "mypy", "ruff"]

    async def __call__(self, context: CodeReviewContext):
        for path in self.file_paths:
            issues = await run_static_analysis(path, self.analyzers)
            context.issues_found.extend(issues)
        context.static_analysis_runs += 1
        return self.format_issues(context.issues_found)

class GenerateReviewTool(BaseTool):
    """Аналог CreateReport - финальный output."""
    summary: str
    critical_issues: list[str]
    recommendations: list[str]
    approval_status: Literal["approved", "needs_changes", "rejected"]

# === Reasoning ===
class CodeReviewReasoning(BaseTool):
    analysis: list[str]
    files_understood: bool
    critical_issues_found: bool
    enough_analysis: bool
    next_steps: list[str]

# === Agent ===
class CodeReviewAgent(BaseAgent):
    name = "code_review_agent"

    def __init__(self, pr_files: list[str]):
        self.context = CodeReviewContext()
        self.toolkit = [
            ReadFileTool,
            StaticAnalysisTool,
            GenerateReviewTool,
            CodeReviewReasoning,
            FinalAnswerTool
        ]
        self.max_files = 20
        self.max_static_analysis = 3
```

---

### Пример 3: Customer Support Agent

```python
# === Context ===
class SupportContext(BaseModel):
    state: StateEnum
    iteration: int

    # Domain artifacts
    user_messages: list[Message]
    knowledge_base_articles: dict[str, Article]
    previous_tickets: list[Ticket]

    # Counters
    kb_searches: int
    escalations: int

# === Tools ===
class SearchKnowledgeBaseTool(BaseTool):
    """Поиск в базе знаний."""
    query: str
    max_results: int = 5

    async def __call__(self, context: SupportContext):
        articles = await kb.search(self.query, self.max_results)
        for article in articles:
            context.knowledge_base_articles[article.id] = article
        context.kb_searches += 1
        return self.format_articles(articles)

class SearchSimilarTicketsTool(BaseTool):
    """Поиск похожих обращений."""
    issue_description: str

    async def __call__(self, context: SupportContext):
        tickets = await ticket_db.search_similar(self.issue_description)
        context.previous_tickets.extend(tickets)
        return self.format_tickets(tickets)

class GenerateResponseTool(BaseTool):
    """Генерация ответа клиенту."""
    response: str = Field(description="Friendly, helpful response")
    cited_articles: list[str] = Field(description="KB article IDs used")
    resolution_status: Literal["resolved", "needs_escalation", "needs_info"]

class EscalateTool(BaseTool):
    """Эскалация к человеку."""
    reason: str
    priority: Literal["low", "medium", "high", "critical"]
    suggested_team: str

# === Agent ===
class SupportAgent(BaseAgent):
    name = "support_agent"

    def __init__(self, user_message: str):
        self.context = SupportContext()
        self.toolkit = [
            SearchKnowledgeBaseTool,
            SearchSimilarTicketsTool,
            GenerateResponseTool,
            EscalateTool,
            AskUserClarificationTool,
            SupportReasoning
        ]
        self.max_kb_searches = 3
        self.max_iterations = 8

    async def _prepare_tools(self):
        tools = set(self.toolkit)

        # Если слишком сложно - разрешаем только эскалацию
        if self.context.iteration > 5 and not self.context.has_solution():
            tools = {EscalateTool, GenerateResponseTool}

        return tools
```

---

## 🎯 Ключевые выводы

### Универсальные паттерны работают везде:

1. **Трёхфазный цикл** (Think → Plan → Execute) - любой multi-step агент
2. **Context = растущие знания** - адаптируйте `artifacts` под domain
3. **Conversation = память** - LLM видит всю историю
4. **Structured Reasoning** - прозрачность через Pydantic схемы
5. **Adaptive Planning** - план адаптируется к данным
6. **Resource Management** - dynamic tools на основе лимитов
7. **Interruption** - для interactive agents
8. **Deterministic Execution** - Structured Output для надёжности

### Что адаптировать под задачу:

- **Context.artifacts**: sources → code files, database records, tickets, etc.
- **Tools**: WebSearch → ReadFile, DatabaseQuery, APICall, etc.
- **Reasoning fields**: research_goal → code_understanding_level, query_correctness, etc.
- **Resource limits**: searches → file_reads, api_calls, compute_time, etc.

### Что остаётся универсальным:

- Трёхфазная архитектура цикла
- Conversation history management
- State machine для состояний
- Resource counting и management
- Interruption через asyncio.Event
- Structured Output для надёжности

---

*Документ создан на основе анализа SGR Deep Research архитектуры*
*Применим к любым агентным системам: research, code, database, support, DevOps, etc.*
