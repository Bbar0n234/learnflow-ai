# Implementation Plan: Edit Agent Integration

## Overview

Minimal integration of an edit agent into LearnFlow AI workflow for MVP. The agent allows users to iteratively edit synthesized educational material through the existing Telegram bot interface. 

**Key principles:**
- Port working code from Jupyter notebook with minimal changes
- Reuse existing HITL patterns from recognition/questions nodes  
- No new infrastructure (no WebSocket, SSE, or complex versioning)
- 4-6 days implementation timeline

## Architecture Design

### 1. Node Architecture

#### 1.1 New EditMaterialNode

**Location**: `learnflow/nodes/edit_material.py`

**Base Class**: Extends `BaseWorkflowNode` (using existing HITL pattern from recognition/questions nodes)

**Core Components**:
- Reuses `synthesized_material` from ExamState as document to edit
- Fuzzy text matching using `fuzzysearch` library (direct port from Jupyter notebook)
- Action-based workflow (edit, message, complete)
- Auto-save to LocalArtifactsManager after each edit

#### 1.2 Minimal State Extensions

**Modified State**: `learnflow/core/state.py`

Add only these fields to existing `ExamState`:

```python
# Minimal additions to ExamState
edit_count: int = Field(default=0, description="Total number of edits performed")
needs_user_input: bool = Field(default=True, description="Flag for HITL interaction")
agent_message: Optional[str] = Field(default=None, description="Message from edit agent to user")
last_action: Optional[str] = Field(default=None, description="Type of last action (edit/message/complete)")
```

**Important clarifications**:
- We reuse existing `feedback_messages` field for edit history tracking (already in state)
- We reuse existing `synthesized_material` field as the document to edit (no need for separate `document` field)
- This means we're adding exactly 4 new fields, not 6 as in the Jupyter notebook

### 2. Data Flow Integration

#### 2.1 Workflow Modification

**Current Flow**:
```
synthesis_material -> generating_questions
```

**New Flow**:
```
synthesis_material -> edit_material -> generating_questions
```

**Skip condition**: If user doesn't want to edit, node immediately transitions to `generating_questions`

#### 2.2 Node Transitions

- `synthesis_material` sets `synthesized_material` in state
- `edit_material` works with `synthesized_material` directly (no document copying)
- Uses existing HITL pattern with `interrupt()` for user input
- On "complete" action or skip, updates `synthesized_material` and goes to `generating_questions`
- Each edit triggers auto-save via LocalArtifactsManager

### 3. Storage and Persistence

#### 3.1 Auto-save Mechanism

**Integration with LocalArtifactsManager**:
- After each successful edit, update the single document: `{session_path}/edited_material.md`
- Maintain lightweight edit history in JSON: `{session_path}/edit_history.json`
- Use existing `save_artifact()` method from LocalArtifactsManager

**Important**: Only the successfully matched delta (old_text/new_text pair) is sent to artifacts service via REST API, not the entire document. Fuzzy matching happens in the edit agent node before any API call.

**Edit history JSON structure** (minimal overhead):
```json
{
  "edits": [
    {
      "timestamp": "2024-01-15T10:30:00Z",
      "edit_number": 1,
      "old_text_preview": "First 50 chars of replaced text...",
      "new_text_preview": "First 50 chars of new text...",
      "similarity": 0.95
    }
  ],
  "total_edits": 5,
  "last_modified": "2024-01-15T10:35:00Z"
}
```

#### 3.2 Simple REST API Approach

**No real-time needed for MVP**:
- Telegram bot polls for updates via existing REST endpoints
- Web UI (if added later) can poll `/document/{thread_id}` endpoint
- Each edit is immediately persisted, so clients always get latest version

### 4. Minimal File Changes

**New files (only 2)**:
```
learnflow/
├── nodes/
│   └── edit_material.py         # New edit node (ports logic from Jupyter)
└── utils/
    └── fuzzy_matcher.py         # Fuzzy matching function from notebook
```

**Modified files (3)**:
```
learnflow/
├── core/
│   ├── state.py                 # Add 4 fields to ExamState
│   └── graph.py                 # Add edit_material node to workflow
└── nodes/
    └── __init__.py              # Export EditMaterialNode
```

**Optional API additions** (can be added later if needed):
```
learnflow/api/
└── main.py                      # Add 2 simple endpoints for manual edit control
```

## Детальная логика работы агента редактирования

### Двухшаговый процесс принятия решений

Агент работает в два этапа для каждой итерации:

#### Шаг 1: Определение типа действия (ActionDecision)

На первом шаге модель анализирует:
- Текущее состояние документа
- Историю сообщений и правок
- Обратную связь от пользователя

И принимает решение о типе действия:
- **edit** - внести конкретную правку в документ
- **message** - задать уточняющий вопрос пользователю
- **complete** - завершить редактирование

```python
class ActionDecision(BaseModel):
    """Step 1: Decide what action to take"""
    action_type: Literal["edit", "message", "complete"] = Field(
        description="Type of action to perform"
    )
```

#### Шаг 2: Получение деталей действия

В зависимости от выбранного типа действия, модель возвращает соответствующую структуру:

**Для edit**:
```python
class EditDetails(BaseModel):
    """Details for edit action"""
    old_text: str = Field(description="Exact text to replace")
    new_text: str = Field(description="Replacement text")
    continue_editing: bool = Field(
        default=True,
        description="Continue editing autonomously after this edit"
    )
```

**Для message**:
```python
class MessageDetails(BaseModel):
    """Details for message action"""
    content: str = Field(description="Message to send to user")
```

### Алгоритм нечёткого поиска и замены

Ключевая особенность агента - использование нечёткого поиска через библиотеку `fuzzysearch`:

```python
def fuzzy_find_and_replace(
    document: str, 
    target: str, 
    replacement: str, 
    threshold: float = 0.85
) -> Tuple[str, bool, Optional[str], float]:
    """
    Нечёткий поиск и замена текста в документе.
    
    Returns: (new_document, success, found_text, similarity)
    """
    # Для коротких строк (< 10 символов) - только точное совпадение
    if len(target) < 10:
        if target in document:
            idx = document.index(target)
            new_doc = document[:idx] + replacement + document[idx + len(target):]
            return new_doc, True, target, 1.0
        return document, False, None, 0.0
    
    # Вычисляем максимальную дистанцию Левенштейна
    max_distance = max(1, int(len(target) * (1 - threshold)))
    
    # Для длинных строк (> 100 символов) ограничиваем дистанцию
    if len(target) > 100:
        max_distance = min(max_distance, 15)
    
    # Поиск с помощью fuzzysearch
    matches = find_near_matches(
        target, 
        document, 
        max_l_dist=max_distance
    )
    
    if not matches:
        return document, False, None, 0.0
    
    # Берём первое совпадение
    match = matches[0]
    similarity = 1 - (match.dist / len(target))
    
    # Выполняем замену
    new_document = (
        document[:match.start] + 
        replacement + 
        document[match.end:]
    )
    
    return new_document, True, match.matched, similarity
```

**Важные особенности**:
- Threshold по умолчанию = 0.85 (85% сходство)
- Для коротких текстов (<10 символов) используется только точное совпадение
- Для длинных текстов (>100 символов) максимальная дистанция ограничена 15 символами
- Берётся первое найденное совпадение

### Обработка ошибок поиска

Если текст не найден (similarity < threshold), агент:
1. Возвращает простое сообщение об ошибке без деталей
2. Позволяет модели попробовать другой фрагмент текста
3. При необходимости запрашивает уточнение у пользователя

```python
if not success:
    error_msg = f"Error: Text not found in document (similarity < {threshold})."
    messages.append(SystemMessage(
        content=f"[EDIT ERROR]: {error_msg}"
    ))
    # Модель получит эту ошибку и попробует другой подход
```

## Основная функция узла редактирования

Полный код главной функции из Jupyter Notebook с адаптацией под архитектуру проекта:

```python
def main_node(state: GeneralState) -> Command[Literal["main_node", "__end__"]]:
    """
    Основной узел агента редактирования.
    Адаптация: в проекте это будет EditMaterialNode.process()
    """
    messages = state.messages
    
    # Запрашиваем ввод пользователя только если нужно
    if state.needs_user_input:
        msg_to_user = state.agent_message or "Какие правки внести?"
        
        # HITL interrupt - ожидание ввода пользователя
        user_feedback = interrupt(value=msg_to_user)
        
        if user_feedback:
            messages.append(HumanMessage(content=user_feedback))
            
            return Command(
                goto="main_node",
                update={
                    "messages": messages,
                    "agent_message": None,
                    "needs_user_input": False  # Переходим к обработке
                }
            )
    
    # Шаг 1: Определяем тип действия
    decision = model.with_structured_output(ActionDecision).invoke(
        [SystemMessage(content=SYSTEM_PROMPT)] + messages
    )
    
    messages.append(AIMessage(content=decision.model_dump_json()))
    
    # Шаг 2: Получаем детали в зависимости от типа
    if decision.action_type == "edit":
        details = model.with_structured_output(EditDetails).invoke(
            [SystemMessage(content=SYSTEM_PROMPT)] + messages
        )
        return handle_edit_action(state, details, messages)
        
    elif decision.action_type == "message":
        details = model.with_structured_output(MessageDetails).invoke(
            [SystemMessage(content=SYSTEM_PROMPT)] + messages
        )
        return handle_message_action(state, details, messages)
        
    elif decision.action_type == "complete":
        return handle_complete_action(state)
```

### Обработчик действия редактирования

```python
def handle_edit_action(state: GeneralState, action: EditDetails, messages: list) -> Command:
    """Обработка действия редактирования с нечётким поиском"""
    document = state.document
    
    # Используем fuzzy_find_and_replace
    new_document, success, found_text, similarity = fuzzy_find_and_replace(
        document, action.old_text, action.new_text
    )
    
    if not success:
        # Текст не найден
        error_msg = f"Error: Text not found in document (similarity < 0.85)."
        messages.append(SystemMessage(content=f"[EDIT ERROR]: {error_msg}"))
        
        return Command(
            goto="main_node",
            update={
                "messages": messages,
                "needs_user_input": False,
                "last_action": "edit_error"
            }
        )
    
    # Успешное редактирование
    document = new_document
    edit_count = state.edit_count + 1
    
    messages.append(SystemMessage(
        content=f"[EDIT SUCCESS #{edit_count}]: Text replaced (similarity: {similarity:.2f})."
    ))
    
    # Определяем нужен ли пользовательский ввод
    needs_input = not action.continue_editing
    agent_msg = "Я внёс правки, что дальше?" if not action.continue_editing else None
    
    return Command(
        goto="main_node",
        update={
            "document": document,
            "messages": messages,
            "needs_user_input": needs_input,
            "edit_count": edit_count,
            "agent_message": agent_msg,
            "last_action": "edit"
        }
    )
```

### 5. API Endpoints (Optional for MVP)

**Note**: The edit node works through LangGraph's HITL mechanism. These endpoints are optional for external control.

#### 5.1 Minimal REST Endpoints

**GET** `/document/{thread_id}`
- Returns current `synthesized_material` from state
- Response: `{"document": "...", "edit_count": 0, "status": "editing|completed"}`

**POST** `/edit/{thread_id}/patch` 
- Apply a validated edit patch (after successful fuzzy matching in agent node)
- Request body: 
```json
{
  "old_text": "exact text that was found and validated",
  "new_text": "replacement text",
  "edit_metadata": {
    "similarity": 0.95,
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```
- Response: `{"success": true, "edit_count": 1, "document_updated": true}`

**Important flow**:
1. Agent node performs fuzzy matching locally (using logic from Jupyter notebook)
2. If successful match found, sends validated patch to artifacts service
3. Artifacts service applies simple replacement (no fuzzy logic needed)
4. If no match or poor similarity, agent logs error and retries with user feedback

Note: The fuzzy matching logic from `_experiments/notebooks/learnflow_edit_agent.ipynb` already handles uniqueness - it takes the first match from `fuzzysearch.find_near_matches()`

**Note**: Primary interaction happens through Telegram bot using existing workflow mechanisms.

## System Prompt для агента редактирования

Адаптированный промпт из Jupyter Notebook для использования в проекте:

```python
EDIT_AGENT_SYSTEM_PROMPT = """
<role>
You are a university-level cryptography professor, refining educational material 
for exam preparation. Your mission is to produce thorough, comprehensive, and 
absolutely exhaustive educational content.
</role>

<current_phase>
You are in an iterative refinement cycle, improving the previously generated 
educational material based on student feedback.
</current_phase>

<generated_material>
{{ synthesized_material }}
</generated_material>

<editing_standards>
When making edits, ensure your modifications maintain:
1. **Comprehensiveness**: Cover all necessary angles - definitions, theory, practical relevance
2. **Clarity**: Use precise, unambiguous language 
3. **Mathematics**: Add detailed step-by-step derivations with proper LaTeX formatting
4. **Examples**: Add intuitive analogies and illustrative examples
5. **Self-sufficiency**: Material must be self-contained
6. **Language**: All content in Russian, academic style
</editing_standards>

<editing_instructions>
1. **Understand Intent**: Analyze student feedback to understand what needs improvement
2. **Precise Matching**: The old_text must match a fragment from the material
3. **Maintain Quality**: Enhance, not diminish, educational value
4. **Autonomous Editing**: Use continue_editing: true for consecutive edits
5. **Communication**: Use "message" action when you need clarification
6. **Completion**: Use "complete" when all improvements are done
</editing_instructions>
"""
```

## Примеры взаимодействия агента с пользователем

### Пример 1: Успешное редактирование

```
User: "Добавь более подробное объяснение коммутативности шифрования"

Agent (Step 1 - ActionDecision): 
{
    "action_type": "edit"
}

Agent (Step 2 - EditDetails):
{
    "old_text": "Шифр E_k называется коммутативным, если для любых ключей k_1, k_2 и сообщения m:",
    "new_text": "Шифр E_k называется коммутативным, если для любых ключей k_1, k_2 и сообщения m выполняется свойство, что порядок применения операций шифрования не влияет на результат. Это критически важно для ментального покера, так как позволяет игрокам независимо шифровать и расшифровывать карты:",
    "continue_editing": true
}

System: [EDIT SUCCESS #1]: Text replaced (similarity: 0.95).

Agent (continuing autonomously, Step 1):
{
    "action_type": "edit"
}

Agent (Step 2):
{
    "old_text": "Коммутативность:",
    "new_text": "Математическое доказательство коммутативности:",
    "continue_editing": false
}

System: [EDIT SUCCESS #2]: Text replaced (similarity: 0.88).

Agent Message: "Я добавил подробное объяснение коммутативности шифрования. Что дальше?"
```

### Пример 2: Обработка ошибки поиска

```
User: "Исправь опечатку в формуле Эйлера"

Agent (Step 1):
{
    "action_type": "edit"  
}

Agent (Step 2):
{
    "old_text": "формула Эйлера: φ(N) = (p-1)(q-1)",
    "new_text": "функция Эйлера: φ(N) = (p-1)(q-1)",
    "continue_editing": false
}

System: [EDIT ERROR]: Error: Text not found in document (similarity < 0.85).

Agent (Step 1 - retry):
{
    "action_type": "message"
}

Agent (Step 2):
{
    "content": "Не могу найти упоминание 'формулы Эйлера' в тексте. Можете указать точнее, где находится опечатка?"
}
```

### Пример 3: Завершение редактирования

```
User: "Всё отлично, больше правок не нужно"

Agent (Step 1):
{
    "action_type": "complete"
}

System: Document saved to artifacts. Editing session completed.
```

## Implementation Tasks (MVP - 4-6 days)

### Day 1-2: Setup and Core Logic

1. **Add dependency**
   - Run: `uv add fuzzysearch --package learnflow-core --group prod`

2. **Port fuzzy matcher from notebook**
   - Create `learnflow/utils/fuzzy_matcher.py`
   - Copy `fuzzy_find_and_replace()` function from Jupyter
   - Add basic tests

3. **Extend ExamState**
   - Add 4 fields to `learnflow/core/state.py`:
     - `edit_count: int = 0`
     - `needs_user_input: bool = True`
     - `agent_message: Optional[str] = None`
     - `last_action: Optional[str] = None`

### Day 3-4: Create Edit Node

4. **Implement EditMaterialNode**
   - Create `learnflow/nodes/edit_material.py`
   - Port main logic from Jupyter's `main_node()` function
   - Adapt to use `synthesized_material` instead of separate document
   - Add auto-save using existing LocalArtifactsManager
   
   **Адаптация под архитектуру проекта**:
   ```python
   class EditMaterialNode(BaseWorkflowNode):
       """Node for iterative editing of synthesized material"""
       
       def __init__(self):
           super().__init__(logger)
           self.model = self.create_model()  # Создаём модель через базовый метод
       
       def get_node_name(self) -> str:
           """Возвращает имя узла для поиска конфигурации"""
           return "edit_material"
       
       async def process(self, state: ExamState) -> Command:
           """Process edit request with HITL pattern"""
           
           # Работа с synthesized_material из state
           document = state.synthesized_material
           messages = state.feedback_messages or []
           
           # Логика из main_node() Jupyter notebook
           if state.needs_user_input:
               # HITL interrupt pattern (как в recognition/questions nodes)
               user_feedback = interrupt(value=state.agent_message or "Какие правки?")
               # ... продолжение логики
           
           # Двухшаговый процесс с моделью
           decision = self.model.with_structured_output(ActionDecision).invoke(...)
           # ... обработка действий
           
           # Сохранение артефактов через graph_manager
           # (обычно это делается на уровне workflow после завершения узла)
   ```

5. **Define action models**
   - Add Pydantic models for ActionDecision, EditDetails, MessageDetails
   - Reuse from Jupyter notebook with minimal changes
   
   **Размещение моделей**:
   ```python
   # learnflow/nodes/edit_material.py
   
   class ActionDecision(BaseModel):
       """Step 1: Decide what action to take"""
       action_type: Literal["edit", "message", "complete"]
   
   class EditDetails(BaseModel):
       """Details for edit action"""
       old_text: str
       new_text: str
       continue_editing: bool = True
   
   class MessageDetails(BaseModel):
       """Details for message action"""
       content: str
   ```

### Day 5: Integration

6. **Wire into workflow**
   - Modify `learnflow/core/graph.py`:
     - Import EditMaterialNode
     - Add node: `workflow.add_node("edit_material", edit_node)`
     - Update flow navigation through Command returns
   - Update `learnflow/nodes/__init__.py` to export EditMaterialNode
   
   **Интеграция в граф**:
   ```python
   # learnflow/core/graph.py
   
   # В функции create_workflow():
   from ..nodes import EditMaterialNode
   
   # Создание узла
   edit_node = EditMaterialNode()
   workflow.add_node("edit_material", edit_node)
   
   # Навигация через Command:
   # - synthesis_material возвращает Command(goto="edit_material")
   # - edit_material возвращает Command(goto="generating_questions") при завершении
   ```

7. **Test with existing bot**
   - Run full workflow with Telegram bot
   - Verify HITL interrupts work
   - Check auto-save functionality

### Day 6: Polish and Optional API

8. **Add optional REST endpoints** (if time permits)
   - `GET /document/{thread_id}` - return current document
   - `POST /edit/{thread_id}` - manual edit trigger
   - Can be skipped for MVP since bot handles everything

9. **Basic testing**
   - Test fuzzy matching edge cases
   - Test workflow continuity
   - Test save/load of edited documents

## Testing Strategy (Simplified for MVP)

### Manual Testing Checklist

1. **Fuzzy Matching**:
   - Test with exact match
   - Test with minor typos (1-2 chars difference)
   - Test with whitespace differences
   - Test when text not found

2. **Edit Flow**:
   - Test edit -> continue editing -> edit -> complete
   - Test edit -> complete immediately
   - Test message -> user response -> edit
   - Test skip editing (go directly to questions)

3. **Integration**:
   - Full workflow through Telegram bot
   - Verify saves appear in artifacts folder
   - Check edited document is used for question generation

## Deployment (MVP)

### Configuration

### Docker

**No changes needed** - fuzzysearch will be added via UV, no new ports or volumes required.

## Важные детали интеграции с существующей архитектурой

### Использование существующих паттернов HITL

Агент редактирования использует те же паттерны HITL, что уже реализованы в узлах `recognition_handwritten` и `generating_questions`:

```python
# Паттерн interrupt для получения пользовательского ввода
user_feedback = interrupt(value="Сообщение пользователю")

# Возврат Command для управления потоком
return Command(
    goto="next_node_or_self",
    update={
        "state_field": new_value,
        # ...
    }
)
```

### Работа с ExamState

**Важно**: Агент работает напрямую с полем `synthesized_material` в ExamState, не создавая отдельное поле `document`:

```python
# Правильно - используем существующее поле
document = state.synthesized_material

# После редактирования обновляем то же поле
return Command(
    update={"synthesized_material": edited_document}
)
```

### Промпты из configs/prompts.yaml

Промпт агента должен быть добавлен в существующий файл конфигурации:

```yaml
# configs/prompts.yaml
edit_agent_system_prompt: |
  <role>
  You are a university-level cryptography professor...
  </role>
  # ... остальной промпт
```

### Сохранение артефактов

Для сохранения отредактированного материала после каждой правки нужно добавить метод в GraphManager и вызывать его из узла редактирования.

#### Новый метод в GraphManager:

```python
# learnflow/core/graph_manager.py

async def push_edited_material(self, thread_id: str, synthesized_material: str) -> Optional[Dict[str, Any]]:
    """
    Сохраняет отредактированный синтезированный материал в артефакты.
    Перезаписывает существующий файл synthesized_material.md.
    
    Args:
        thread_id: ID потока
        synthesized_material: Отредактированный материал
        
    Returns:
        Dict с результатом сохранения или None при ошибке
    """
    if not self.artifacts_manager:
        logger.warning(f"Artifacts manager not configured for thread {thread_id}")
        return None
    
    try:
        # Получаем путь к текущей сессии из сохранённых данных
        folder_path = self.artifacts_data.get(thread_id, {}).get("local_folder_path")
        
        if not folder_path:
            # Если сессия ещё не создана, создаём через push_learning_material
            # (это случай, если edit_material вызывается до других пушей)
            state_vals = await self.get_state(thread_id)
            exam_question = state_vals.get("exam_question", "")
            
            result = await self.artifacts_manager.push_learning_material(
                thread_id=thread_id,
                exam_question=exam_question,
                generated_material=state_vals.get("generated_material", "")
            )
            folder_path = result.get("folder_path")
            
            # Сохраняем путь для последующих операций
            if thread_id not in self.artifacts_data:
                self.artifacts_data[thread_id] = {}
            self.artifacts_data[thread_id]["local_folder_path"] = folder_path
        
        # Пушим отредактированный материал (ПЕРЕЗАПИСЫВАЕТ существующий файл)
        result = await self.artifacts_manager.push_synthesized_material(
            folder_path=folder_path,
            synthesized_material=synthesized_material,
            thread_id=thread_id
        )
        
        if result.get("success"):
            logger.info(f"Successfully pushed edited material for thread {thread_id}")
            
            # Обновляем метаданные сессии с информацией о редактировании
            edit_count = (await self.get_state(thread_id)).get("edit_count", 0)
            session_metadata_updates = {
                "last_edited": datetime.now().isoformat(),
                "edit_count": edit_count,
                "has_edited_material": True
            }
            # Метод обновления метаданных (если есть)
            # await self.artifacts_manager.update_session_metadata(folder_path, session_metadata_updates)
        
        return result
        
    except Exception as e:
        logger.error(f"Error pushing edited material for thread {thread_id}: {e}")
        return None
```

#### Автоматический вызов из GraphManager при обработке событий:

```python
# learnflow/core/graph_manager.py
# В методе run_exam_workflow, в цикле обработки событий:

async for event in graph.astream(
    input_state, cfg, stream_mode="updates"
):
    logger.debug(f"Event: {event}")
    
    for node_name, node_data in event.items():
        # Существующий пуш после generating_content
        if node_name == "generating_content":
            logger.info(f"Content generation completed for thread {thread_id}, pushing to GitHub...")
            # ... существующий код ...
        
        # НОВЫЙ: Пуш отредактированного материала после edit_material
        if node_name == "edit_material" and "synthesized_material" in node_data:
            logger.info(f"Edit material updated for thread {thread_id}, pushing to artifacts...")
            
            # Вызываем наш новый метод push_edited_material
            push_result = await self.push_edited_material(
                thread_id=thread_id,
                synthesized_material=node_data.get("synthesized_material")
            )
            
            if push_result and push_result.get("success"):
                logger.info(f"Successfully pushed edited material for thread {thread_id}")
                
                # Обновляем данные в artifacts_data если нужно
                if thread_id not in self.artifacts_data:
                    self.artifacts_data[thread_id] = {}
                self.artifacts_data[thread_id]["has_edited_material"] = True
```

#### Узел EditMaterialNode просто возвращает Command:

```python
# learnflow/nodes/edit_material.py

async def __call__(self, state: ExamState, config) -> Command:
    """Главная функция узла - только логика редактирования"""
    
    # ... логика редактирования ...
    
    # После успешной правки просто обновляем state
    if action.action_type == "edit" and edit_successful:
        return Command(
            goto="edit_material",  # Возвращаемся к себе для следующей итерации
            update={
                "synthesized_material": edited_document,
                "edit_count": state.edit_count + 1,
                "needs_user_input": not action.continue_editing,
                "last_action": "edit"
            }
        )
    
    # При завершении редактирования
    if action.action_type == "complete":
        return Command(
            goto="generating_questions",
            update={
                "synthesized_material": state.synthesized_material,
                "edit_count": state.edit_count,
                "last_action": "complete"
            }
        )
```

**Важно**: 
- Метод `push_edited_material` ПЕРЕЗАПИСЫВАЕТ файл `synthesized_material.md` после каждой правки
- НЕ создаёт версионированные копии (edit_001.md и т.д.)
- Использует существующий `push_synthesized_material` из LocalArtifactsManager, который делает override
- Обновляет метаданные сессии с информацией о количестве правок

## Known Limitations (MVP)

1. **Fuzzy matching**: May not find text with >15% differences
2. **No undo**: Edits are permanent (but versioned in artifacts)
3. **Single user**: No concurrent editing support
4. **Text only**: No formatting preservation (markdown is plain text)

## Future Enhancements (Post-MVP)

Once MVP is validated with users:
- Better fuzzy matching algorithms
- Undo/redo functionality  
- Batch edit operations
- Edit templates for common corrections
- Web UI with live preview

## Conclusion

This simplified implementation plan focuses on MVP delivery in 4-6 days by:
- Reusing existing HITL patterns and infrastructure
- Porting proven logic from the Jupyter notebook
- Minimal changes to existing codebase (2 new files, 3 modified files)
- No WebSocket/SSE complexity - just REST API and existing bot integration
- Feature flag for easy rollback if needed

The edit agent will allow users to iteratively refine synthesized educational materials through the Telegram bot interface, with each edit automatically saved to the artifacts storage for persistence and version tracking.