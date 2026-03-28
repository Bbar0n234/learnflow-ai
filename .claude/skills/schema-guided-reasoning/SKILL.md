---
name: schema-guided-reasoning
description: >
  Паттерн Schema-Guided Reasoning (SGR) для решения задач на базе LLM
  с использованием structured output, constrained decoding, Pydantic моделей.
  Используй когда нужно: структурированный вывод, JSON schema,
  воспроизводимость рассуждений, тестируемость промежуточных шагов,
  направленное рассуждение модели, response_format, parse().
---

# Schema-Guided Reasoning (SGR)

## Суть подхода

SGR направляет рассуждения LLM через предопределённые схемы с использованием Constrained Decoding (Structured Output). Вместо свободного текста модель **обязана** следовать структуре: какие шаги выполнить, в каком порядке, на чём сфокусироваться.

**Ключевой механизм:** Порядок полей в схеме = порядок рассуждения модели. Модель заполняет поля последовательно, и ранние поля "разогревают" мышление для поздних.

## Когда применять

**Используй SGR когда важны:**
- Воспроизводимость — одинаковая структура ответов
- Тестируемость — можно проверять промежуточные шаги
- Аудируемость — каждый шаг рассуждения виден
- Предсказуемость — известная структура для downstream обработки

**Не используй когда:**
- Нужен максимально качественный свободный текст
- Задача плохо формализуется в структуру
- Ограничения схемы мешают модели рассуждать

## Честный trade-off

```
✅ SGR даёт:                    ⚠️ SGR НЕ гарантирует:
─────────────────────────────   ─────────────────────────────
• Воспроизводимость             • Прирост качества/accuracy
• Тестируемость                 • Лучшие рассуждения
• Аудируемость                  • Более умные ответы
• Надёжность структуры
• Прозрачность шагов
```

**Почему качество может падать:** Constraint decoding и следование структуре "отнимают силы" у модели. Она тратит capacity на соблюдение схемы вместо качества рассуждений.

**Вывод:** Используй SGR когда предсказуемость важнее максимального качества.

---

## Pydantic модели — центральный компонент

### Провайдеры автоматически добавляют схему в контекст

Когда передаёшь схему в `response_format` или `parse()`, провайдер (OpenAI и др.) **автоматически** добавляет её в контекст модели.

```python
# ❌ НЕ ДЕЛАЙ ТАК — двойная трата токенов
system_prompt = """
Ты анализируешь кандидатов.

Формат ответа:
- brief_summary: краткое резюме
- skill_rating: оценка 1-10
- recommendation: hire/reject/hold
"""

# ✅ ДЕЛАЙ ТАК — схема добавится автоматически
system_prompt = "Ты анализируешь кандидатов."

class CandidateEvaluation(BaseModel):
    brief_summary: str
    skill_rating: Annotated[int, Ge(1), Le(10)]
    recommendation: Literal["hire", "reject", "hold"]
```

### Всё в схеме — это prompt для модели

Каждый элемент Pydantic модели идёт в контекст и влияет на генерацию:

| Элемент | Роль в контексте |
|---------|------------------|
| Имя класса | Семантика задачи |
| Docstring класса | Контекст и инструкции |
| Имена полей | Семантика каждого шага |
| Field description | Детальные указания по заполнению |
| Порядок полей | Последовательность рассуждения |
| Типы и constraints | Ограничения на значения |

### Имя класса

Отражает семантику задачи. Модель "видит" это имя.

```python
# ❌ Плохо — бессмысленно для модели
class Response(BaseModel): ...
class Output(BaseModel): ...
class Result(BaseModel): ...

# ✅ Хорошо — передаёт контекст
class CandidateEvaluation(BaseModel): ...
class RiskAssessment(BaseModel): ...
class ComplianceVerification(BaseModel): ...
```

### Docstring класса

Пишется **ДЛЯ МОДЕЛИ**, не для разработчиков. Объясняет контекст, цель, может содержать инструкции.

```python
class CandidateEvaluation(BaseModel):
    """
    Оценка кандидата на позицию.

    Сначала кратко резюмируй ключевые факты о кандидате,
    затем оцени соответствие навыков требованиям позиции,
    и только после этого дай рекомендацию.
    """
    brief_summary: str
    skill_rating: Annotated[int, Ge(1), Le(10)]
    recommendation: Literal["hire", "reject", "hold"]
```

### Имена полей

Семантически значимые, понятные модели.

```python
# ❌ Плохо
class Analysis(BaseModel):
    field1: str
    field2: int
    result: str

# ✅ Хорошо
class Analysis(BaseModel):
    brief_situation_summary: str
    confidence_score: int
    recommended_action: str
```

### Field descriptions

**Главный инструмент направления модели.** Пишутся для модели, не для IDE.

```python
from pydantic import BaseModel, Field

class RiskAssessment(BaseModel):
    """Оценка рисков проекта."""

    risk_factors: list[str] = Field(
        description="Перечисли 2-4 ключевых риска. "
                    "Для каждого укажи конкретную причину, не общие фразы."
    )

    overall_severity: Literal["low", "medium", "high"] = Field(
        description="Общая критичность на основе выявленных факторов. "
                    "high — если есть хотя бы один блокирующий риск."
    )

    mitigation_possible: bool = Field(
        description="Можно ли смягчить риски в рамках текущих ресурсов и сроков."
    )
```

**Принципы описаний:**
- Каждое слово должно помогать модели
- Не засорять очевидным ("это поле содержит...")
- Включать критерии, примеры, граничные случаи
- Если описание не добавляет ценности — не писать его

### Порядок полей (Cascade)

Модель заполняет поля **последовательно**. Используй это:

```python
class DocumentAnalysis(BaseModel):
    # 1. Сначала понять что перед нами
    document_type: Literal["contract", "invoice", "report", "other"]

    # 2. Затем извлечь ключевое
    key_entities: list[str]
    main_topic: str

    # 3. На основе понимания — анализ
    potential_issues: list[str]

    # 4. Финальное решение на базе всего выше
    requires_review: bool
    priority: Literal["low", "medium", "high"]
```

**Принцип:** От общего к конкретному. Ранние поля создают контекст для поздних.

---

## Паттерны (применяй по необходимости)

### Cascade (базовый)

Последовательные шаги через порядок полей. **Используется почти всегда.**

```python
class Evaluation(BaseModel):
    # Шаг 1: Собрать факты
    observed_facts: list[str]

    # Шаг 2: Проанализировать
    analysis: str

    # Шаг 3: Сделать вывод
    conclusion: str
```

### Routing (когда нужен выбор пути)

Union типы для выбора одного варианта из нескольких.

```python
from typing import Union

class HardwareIssue(BaseModel):
    kind: Literal["hardware"]
    component: Literal["battery", "display", "keyboard"]

class SoftwareIssue(BaseModel):
    kind: Literal["software"]
    application: str
    error_message: str

class SupportTriage(BaseModel):
    """Модель выберет ОДИН тип проблемы."""
    issue: Union[HardwareIssue, SoftwareIssue]
    suggested_action: str
```

**Применяй когда:** Реально нужна ветвящаяся логика с разной структурой веток.

### Cycle (когда нужно N однотипных элементов)

List с ограничениями на количество.

```python
from typing import Annotated
from annotated_types import MinLen, MaxLen

class RiskFactor(BaseModel):
    description: str
    severity: Literal["low", "medium", "high"]

class RiskReport(BaseModel):
    """Требуется от 2 до 4 факторов риска."""
    factors: Annotated[list[RiskFactor], MinLen(2), MaxLen(4)]
```

**Применяй когда:** Нужен контроль над количеством элементов.

### Adaptive Planning (для агентов)

Перепланирование на каждом шаге. **Только для агентных сценариев.**

```python
class NextStep(BaseModel):
    """
    Планировщик следующего действия.
    После выполнения план отбрасывается и создаётся новый.
    """
    current_situation: str = Field(
        description="Кратко: где мы сейчас, что уже сделано"
    )
    remaining_steps: Annotated[list[str], MinLen(1), MaxLen(5)] = Field(
        description="Что осталось сделать (высокоуровнево)"
    )
    task_completed: bool = Field(
        description="True если задача полностью выполнена"
    )
    next_action: Union[SendEmail, SearchDB, CreateReport, Finish] = Field(
        description="Следующее конкретное действие"
    )
```

**Применяй когда:** Строишь агента с tool calling и нужна адаптивность.

---

## Типы и constraints

### Базовые типы

```python
from typing import Literal, Annotated, Union
from annotated_types import Ge, Le, MinLen, MaxLen
from pydantic import BaseModel, Field

class Example(BaseModel):
    # Enum-подобный выбор
    status: Literal["pending", "approved", "rejected"]

    # Число в диапазоне
    score: Annotated[int, Ge(1), Le(10)]

    # Список с ограничением длины
    items: Annotated[list[str], MinLen(1), MaxLen(5)]

    # Опциональное поле
    comment: str | None = None
```

### Вложенные структуры

```python
class Address(BaseModel):
    city: str
    street: str

class Person(BaseModel):
    name: str
    address: Address  # Вложенная модель
```

---

## Пример: полная реализация

```python
from typing import Literal, Annotated
from annotated_types import Ge, Le
from pydantic import BaseModel, Field
from openai import OpenAI

# 1. Определяем схему
class CandidateEvaluation(BaseModel):
    """
    Оценка кандидата для принятия решения о найме.
    Последовательно: резюмируй → оцени → рекомендуй.
    """

    brief_summary: str = Field(
        description="2-3 предложения о ключевом опыте и навыках кандидата"
    )

    skill_match_rating: Annotated[int, Ge(1), Le(10)] = Field(
        description="Соответствие навыков требованиям позиции. "
                    "1-3: не подходит, 4-6: частично, 7-10: хорошо подходит"
    )

    recommendation: Literal["hire", "reject", "hold"] = Field(
        description="hire: рейтинг 7+, reject: рейтинг ≤3, hold: требует доп. интервью"
    )

# 2. Вызываем с parse()
client = OpenAI()

completion = client.beta.chat.completions.parse(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "Ты HR-специалист, оцениваешь кандидатов."},
        {"role": "user", "content": f"Оцени кандидата на позицию {position}:\n\n{resume}"}
    ],
    response_format=CandidateEvaluation
)

result = completion.choices[0].message.parsed

# 3. Используем структурированный результат
print(f"Резюме: {result.brief_summary}")
print(f"Оценка: {result.skill_match_rating}/10")
print(f"Решение: {result.recommendation}")

# 4. Можно тестировать отдельные поля
assert 1 <= result.skill_match_rating <= 10
assert result.recommendation in ["hire", "reject", "hold"]
```

---

## Чеклист при проектировании схемы

- [ ] Имя класса отражает семантику задачи
- [ ] Docstring написан для модели, объясняет контекст
- [ ] Имена полей семантически значимы
- [ ] Порядок полей: от общего к конкретному
- [ ] Field descriptions помогают модели, не засоряют
- [ ] Схема не дублируется в system prompt
- [ ] Constraints (Ge, Le, MinLen, MaxLen) только где реально нужны
- [ ] Паттерны (Routing, Cycle) только по необходимости

## Отладка

**Модель не следует схеме:** Проблема редкая с современными провайдерами. Если случается — упростить схему или сменить модель.

**Качество ответов упало:** Схема слишком сложная или ограничивающая. Убрать лишние поля, ослабить constraints.

**Модель "отмалчивается" в полях:** Descriptions недостаточно конкретные. Добавить примеры, критерии.

---

## Источники

- [Schema-Guided Reasoning (Rinat Abdullin)](https://abdullin.com/schema-guided-reasoning/)
- [SGR Patterns](https://abdullin.com/schema-guided-reasoning/patterns)
- [SGR Examples](https://abdullin.com/schema-guided-reasoning/examples)
- [OpenAI Structured Outputs](https://platform.openai.com/docs/guides/structured-outputs)
