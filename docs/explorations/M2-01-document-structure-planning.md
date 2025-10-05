# M2-01: Document Structure Planning & Decomposed Generation

**Дата**: 2025-10-05
**Статус**: Exploration & Design
**Milestone**: M2 - AI-Enhanced Generation

---

## Проблема

### Текущая архитектура workflow:
```
input_processing
→ generating_content (генерация на основе весов модели)
→ recognition_handwritten (OCR конспектов)
→ synthesis_material (переписывание + синтез)
→ edit_material
→ generating_questions
→ answer_question
```

### Выявленные проблемы:

1. **Двойная генерация материала**
   - `generating_content` генерирует материал из весов модели
   - `synthesis_material` фактически переписывает тот же материал, добавляя конспекты
   - Результат: избыточное потребление токенов и времени

2. **Монолитная генерация**
   - Весь материал генерируется за один вызов LLM
   - Нет структурирования и планирования перед генерацией
   - Сложно масштабировать для больших документов

3. **Неясная интеграция источников**
   - Непонятно где и как добавлять новые источники (web search, RAG)
   - Конспекты добавляются только на этапе синтеза, а не с самого начала

---

## Целевое решение (MVP)

### Новая архитектура workflow:

```
input_processing
→ recognition_handwritten (OCR конспектов - ПЕРЕМЕЩЕН РАНЬШЕ)
→ planning_structure (планирование структуры + HITL)
→ parallel_section_generation (единственная генерация, параллельно по секциям)
→ document_assembly (сборка финального документа)
→ edit_material
→ generating_questions
→ answer_question
```

### Ключевые изменения:

1. **Recognition перемещается перед планированием**
   - OCR выполняется ДО генерации структуры
   - Распознанные конспекты доступны при планировании
   - Находятся в `state.recognized_notes`

2. **Единая генерация вместо двух**
   - Удаляется узел `synthesis_material`
   - Узел `generating_content` трансформируется в `parallel_section_generation`
   - Генерация происходит один раз с учетом всех доступных данных

3. **Структурированный подход**
   - Сначала планируем структуру документа
   - Затем генерируем каждую секцию независимо и параллельно
   - Финально собираем документ из секций

---

## Детальный дизайн

### 1. Planning Structure Node

**Назначение**: Генерация иерархической структуры документа на основе темы и доступных конспектов

**Входные данные** (из State):
- `state.input_content` - тема/вопрос
- `state.recognized_notes` - распознанные конспекты (если есть)
- Персонализация из Prompt Config Service

**Structured Output** (Pydantic модель):
```python
class DocumentStructure(BaseModel):
    """Структура документа"""
    sections: List[Section]

class Section(BaseModel):
    """Раздел документа"""
    title: str
    subsections: List[Subsection]
    # order присваивается программно, не LLM!

class Subsection(BaseModel):
    """Подраздел документа"""
    title: str
    description: Optional[str] = None
    # order присваивается программно, не LLM!
```

**Логика работы**:
1. LLM генерирует структуру (sections с subsections)
2. **Программно** присваиваем `order` каждой секции и подсекции
3. Сохраняем в `state.document_structure`

**HITL взаимодействие** (стандартный подход):
- Показываем структуру пользователю
- Если пользователь сигнализирует "всё отлично" → переход к генерации секций
- Если есть правки → генерируем структуру заново с учётом фидбека
- Цикл через `Command` (аналогично `edit_material` и `generating_questions`)

**Промпт** (`planning_structure_system_prompt`):
- Анализ темы и конспектов
- Генерация логичной иерархической структуры
- Учет персонализации (уровень, стиль и т.д.)

---

### 2. Parallel Section Generation Node

**Назначение**: Параллельная генерация каждой секции как единственная точка генерации материала

**Входные данные** (для каждой секции):
- `state.document_structure` - утвержденная структура
- `state.input_content` - исходная тема
- `state.recognized_notes` - конспекты (если есть)
- Конкретная секция для генерации
- Контекст соседних секций (предыдущая/следующая)

**Механика параллелизации**:
```python
async def __call__(self, state: GeneralState, config) -> Command:
    sections = state.document_structure.sections

    sends = []
    for i, section in enumerate(sections):
        sends.append(Send(
            "generate_section",
            {
                "section": section,
                "previous_section": sections[i-1] if i > 0 else None,
                "next_section": sections[i+1] if i < len(sections)-1 else None,
            }
        ))

    return Command(
        goto="document_assembly",
        update={"generated_sections": []}
    )
```

**Промпт** (`generate_section_system_prompt`):
```yaml
generate_section_system_prompt: |
  KEYWORD: {{ subject_keywords }}

  <role>
  You are a {{ role_perspective }} specializing in {{ subject_name }},
  creating comprehensive educational content for {{ target_audience_inline }}.
  </role>

  <task>
  Generate content for the specified section using BOTH your knowledge
  and provided handwritten notes (if available).
  </task>

  <input_data>
    <topic>
    {{ input_content }}
    </topic>

    <document_structure>
    {{ document_structure }}
    </document_structure>

    <current_section>
    {{ current_section }}
    </current_section>

    <handwritten_notes>
    {{ recognized_notes }}
    </handwritten_notes>

    <adjacent_sections>
    Previous: {{ previous_section }}
    Next: {{ next_section }}
    </adjacent_sections>
  </input_data>

  <generation_requirements>
    <knowledge_synthesis>
      - Leverage your deep understanding of {{ subject_name }}
      - When handwritten notes provide specific methods/notations, use them
      - Use your knowledge to provide complete theoretical foundation
      - Create coherent synthesis of both sources
    </knowledge_synthesis>

    <section_context>
      - Follow the structure defined in current_section
      - Create smooth transition from previous section
      - Prepare logical lead-in to next section
      - Maintain self-contained yet connected content
    </section_context>

    <quality_standards>
      {{ topic_coverage }}
      {{ explanation_depth }}
      {{ mathematics }}
    </quality_standards>
  </generation_requirements>

  <output_format>
  Generate section content directly without meta-commentary.
  </output_format>
```

**Выход**:
- `state.generated_sections` - аккумулируется список сгенерированных секций

---

### 3. Document Assembly Node

**Назначение**: Сборка финального документа из сгенерированных секций

**Входные данные**:
- `state.generated_sections` - список сгенерированных секций
- `state.document_structure` - оригинальная структура с `order`

**Логика**:
1. Упорядочить секции согласно `order`
2. Объединить в единый документ
3. Опционально: создать переходы между секциями (легкий пост-процессинг)
4. Записать результат в `state.synthesized_material`

**Выход**:
- `state.synthesized_material` - финальный документ

---

## Обновление State

### Новые модели:

```python
class DocumentStructure(BaseModel):
    """Структура документа"""
    sections: List[Section]

class Section(BaseModel):
    """Раздел документа"""
    title: str
    subsections: List[Subsection]
    order: int  # присваивается программно

class Subsection(BaseModel):
    """Подраздел"""
    title: str
    description: Optional[str] = None
    order: int  # присваивается программно

class GeneratedSection(BaseModel):
    """Сгенерированная секция"""
    section_order: int
    content: str
```

### Изменения в GeneralState:

```python
class GeneralState(BaseModel):
    # ... существующие поля ...

    # DEPRECATED (удалить после миграции):
    # generated_material: str

    # НОВЫЕ поля:
    document_structure: Optional[DocumentStructure] = Field(
        default=None,
        description="Утвержденная структура документа"
    )
    generated_sections: Annotated[List[GeneratedSection], operator.add] = Field(
        default_factory=list,
        description="Список сгенерированных секций (аккумулируется)"
    )
    structure_approved: bool = Field(
        default=False,
        description="Флаг подтверждения структуры пользователем"
    )

    # ОСТАВИТЬ без изменений:
    recognized_notes: str  # используется теперь в planning и generation
    synthesized_material: str  # финальный результат от document_assembly
```

---

## Новые промпты

### 1. `planning_structure_system_prompt`
- Генерация структуры на основе темы и конспектов
- Structured output: `DocumentStructure`

### 2. `planning_structure_further_system_prompt`
- Уточнение структуры на основе фидбека пользователя
- Structured output: стандартный HITL pattern (next_step: "clarify" | "finalize")

### 3. `generate_section_system_prompt`
- Генерация контента одной секции
- Контекст: тема + конспекты + структура + соседние секции

### 4. `document_assembly_system_prompt` (опционально)
- Если нужна LLM-обработка переходов между секциями
- Может быть чисто программная логика (конкатенация)

---

## План миграции

### Фаза 1: Модели и State
- [ ] Создать `DocumentStructure`, `Section`, `Subsection` модели
- [ ] Создать `GeneratedSection` модель
- [ ] Обновить `GeneralState` с новыми полями

### Фаза 2: Planning Structure Node
- [ ] Реализовать `PlanningStructureNode`
- [ ] Написать `planning_structure_system_prompt`
- [ ] Написать `planning_structure_further_system_prompt`
- [ ] Программная логика присвоения `order`
- [ ] HITL цикл для редактирования структуры

### Фаза 3: Реорганизация workflow
- [ ] Переместить `recognition_handwritten` ПЕРЕД planning
- [ ] Убедиться что `recognized_notes` доступны при планировании

### Фаза 4: Section Generation
- [ ] Создать `SectionGenerationNode`
- [ ] Написать `generate_section_system_prompt`
- [ ] Реализовать параллельную генерацию через `Send`
- [ ] Аккумулирование в `generated_sections`

### Фаза 5: Document Assembly
- [ ] Создать `DocumentAssemblyNode`
- [ ] Логика упорядочивания и сборки
- [ ] Запись в `synthesized_material`

### Фаза 6: Cleanup
- [ ] Удалить `ContentGenerationNode` (deprecated)
- [ ] Удалить `SynthesisNode` (deprecated)
- [ ] Удалить поле `generated_material` из State
- [ ] Обновить граф в `create_workflow()`
- [ ] Обновить интеграцию с Telegram bot

---

## Ключевые решения

### ✅ Что ДЕЛАЕМ:
- Recognition перемещается ПЕРЕД планирование
- Единая генерация вместо двух (content + synthesis)
- Структурное планирование с HITL
- Параллельная генерация секций через LangGraph `Send`
- Программное присвоение `order` (не LLM)
- Стандартный HITL pattern (как в других узлах)

### ❌ Что НЕ делаем (избегаем переусложнения):
- Source Collection Node (избыточно для MVP)
- Маппинг источников на секции (будущая оптимизация)
- Интеграция web search / RAG (отдельная инициатива М2)
- Сложная логика переходов между секциями (опционально)

---

## Будущие расширения (вне MVP)

### Инициатива 2: External Sources Integration
- Source Collection Node для агрегации источников (web search, RAG, etc.)
- `ExternalSources` модель для унификации
- Маппинг источников на секции при планировании:
  ```python
  class Section(BaseModel):
      # ...
      relevant_source_ids: List[str] = []  # ID источников для секции
  ```

### Инициатива 3: Content Quality Enhancements
- Пост-процессинг в Document Assembly
- Дедупликация контента между секциями
- Система references и citation
- Улучшение плавности переходов

### Оптимизации:
- Умный маппинг источников (не все источники на каждую секцию)
- Adaptive структура (разная глубина вложенности по контексту)
- Кэширование структур для типовых тем