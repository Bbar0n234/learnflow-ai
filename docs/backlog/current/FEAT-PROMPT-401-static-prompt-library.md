# FEAT-PROMPT-401: Статическая библиотека промптов

## Статус
Planned

## Milestone
OSS Launch

## Цель
Создать библиотеку готовых промптов для различных учебных дисциплин, позволяющую пользователям быстро адаптировать LearnFlow AI под свои нужды.

## Обоснование
- Снижение порога входа для новых пользователей
- Демонстрация возможностей системы
- База для community contributions
- Ускорение внедрения в разных областях знаний

## План реализации

### Этап 1: Архитектура библиотеки (1 день)
- [ ] Спроектировать структуру YAML конфигураций
- [ ] Создать схему валидации промптов
- [ ] Реализовать загрузчик промптов с кэшированием
- [ ] Добавить систему наследования и композиции

### Этап 2: Базовые дисциплины (3 дня)
- [ ] Криптография (существующая, доработать)
- [ ] Математика (линейная алгебра, анализ)
- [ ] Физика (механика, электродинамика)
- [ ] Программирование (алгоритмы, структуры данных)
- [ ] История (мировая, отечественная)

### Этап 3: Технические дисциплины (2 дня)
- [ ] Machine Learning / AI
- [ ] Компьютерные сети
- [ ] Базы данных
- [ ] Операционные системы
- [ ] Web-разработка

### Этап 4: Система переключения (1 день)
- [ ] CLI параметр для выбора дисциплины
- [ ] ENV переменная для дефолтной дисциплины
- [ ] API endpoint для динамического переключения
- [ ] UI селектор в веб-интерфейсе

### Этап 5: Документация и примеры (2 дня)
- [ ] Гайд по добавлению новых дисциплин
- [ ] Примеры кастомизации промптов
- [ ] Best practices для prompt engineering
- [ ] Шаблоны для contribution

## Технические требования

### Структура файлов
```
configs/prompts/
├── base.yaml              # Базовые промпты
├── disciplines/
│   ├── cryptography.yaml
│   ├── mathematics.yaml
│   ├── physics.yaml
│   ├── programming.yaml
│   ├── history.yaml
│   ├── ml_ai.yaml
│   ├── networking.yaml
│   ├── databases.yaml
│   └── custom/           # Пользовательские
└── schema.json           # JSON Schema для валидации
```

### Формат промпта
```yaml
# disciplines/mathematics.yaml
discipline:
  name: "Mathematics"
  description: "Промпты для математических дисциплин"
  tags: ["stem", "exact-sciences"]
  version: "1.0.0"
  
base_context: |
  Ты — опытный преподаватель математики.
  Используй строгие математические определения.
  Включай доказательства и выводы формул.

prompts:
  generating_content:
    system: |
      {base_context}
      Создай подробный учебный материал по теме.
      Структура:
      1. Определения и обозначения
      2. Основные теоремы с доказательствами
      3. Примеры решения задач
      4. Связь с другими разделами
    
    examples:
      - input: "Собственные значения матриц"
        output: "## Собственные значения и векторы..."
  
  generating_questions:
    system: |
      {base_context}
      Сгенерируй вопросы для проверки понимания.
      Уровни сложности:
      - Базовый: определения и простые вычисления
      - Средний: применение теорем
      - Продвинутый: доказательства и обобщения
  
  synthesis:
    system: |
      {base_context}
      Объедини материалы, выделяя:
      - Ключевые концепции
      - Методы решения
      - Типичные ошибки

variables:
  difficulty_levels:
    - beginner
    - intermediate
    - advanced
  
  notation_style:
    - latex
    - unicode
    - plain

overrides:
  # Переопределения для специфических тем
  linear_algebra:
    generating_content:
      append: |
        Обязательно включи геометрическую интерпретацию.
```

### API использования
```python
from learnflow.prompts import PromptLibrary

# Загрузка дисциплины
library = PromptLibrary()
discipline = library.load_discipline("mathematics")

# Получение промпта
prompt = discipline.get_prompt(
    "generating_content",
    variables={"difficulty_level": "advanced"}
)

# Переключение дисциплины
library.set_active_discipline("physics")

# Кастомный промпт
custom_prompt = library.create_custom(
    base="mathematics",
    overrides={
        "generating_content": {
            "append": "Фокус на практических применениях"
        }
    }
)
```

### Конфигурация через ENV
```bash
# Выбор дисциплины
LEARNFLOW_DISCIPLINE=mathematics
LEARNFLOW_DISCIPLINE_PATH=configs/prompts/disciplines/

# Кастомная директория
LEARNFLOW_CUSTOM_PROMPTS=/path/to/custom/prompts

# Язык промптов
LEARNFLOW_PROMPT_LANGUAGE=ru
```

## Definition of Done

- [ ] Минимум 5 дисциплин с полными промптами
- [ ] Валидация всех промптов через JSON Schema
- [ ] Документация по структуре промптов
- [ ] Примеры для каждой дисциплины
- [ ] Тесты на корректность загрузки
- [ ] UI/CLI для выбора дисциплины
- [ ] Contributing guide для новых дисциплин

## Метрики успеха
- Количество доступных дисциплин
- Количество community contributions
- Использование разных дисциплин
- Качество генерации по дисциплинам

## Риски
- Сложность поддержки качества для всех дисциплин
- Необходимость экспертной проверки промптов
- Различия в терминологии между языками

## Примеры использования

### CLI
```bash
# Запуск с выбором дисциплины
learnflow --discipline mathematics process exam.txt

# Список доступных дисциплин
learnflow disciplines list

# Валидация кастомных промптов
learnflow prompts validate ./my-prompts/
```

### Web UI
```javascript
// Выбор дисциплины в UI
const disciplines = await api.getDisciplines();
const selected = await showDisciplineSelector(disciplines);
await api.setDiscipline(selected);
```

### Telegram Bot
```
/discipline mathematics
Дисциплина изменена на: Математика

/disciplines
Доступные дисциплины:
1. Криптография
2. Математика
3. Физика
...
```

## Ссылки
- [Prompt Engineering Guide](https://www.promptingguide.ai/)
- [YAML Schema](https://yaml.org/spec/1.2/spec.html)
- [JSON Schema](https://json-schema.org/)