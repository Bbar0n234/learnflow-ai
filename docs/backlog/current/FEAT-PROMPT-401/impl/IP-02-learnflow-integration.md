# IP-02: LearnFlow Integration с Prompt Configuration Service

## Смысл и цель задачи

Интегрировать существующую систему LearnFlow с новым сервисом конфигурации промптов для обеспечения персонализированной генерации учебных материалов. Сервис динамически определяет необходимые плейсхолдеры из шаблонов промптов, используя значения из контекста workflow в приоритете над настройками пользователя из БД. Основное ожидание - качество генерации важнее доступности, поэтому при недоступности сервиса workflow останавливается с ошибкой.

## Архитектура решения

**Модули для модификации:**
- `learnflow/services/prompt_client.py` - новый HTTP клиент для Prompt Configuration Service
- `learnflow/nodes/base.py` - модификация базового класса для интеграции с сервисом
- `learnflow/nodes/` - все 6 узлов LangGraph будут использовать обновленный базовый класс
- `learnflow/config/settings.py` - добавление настроек для интеграции

**Компоненты:**
- **PromptConfigClient** - HTTP клиент для взаимодействия с сервисом конфигурации с retry механизмом
- **BaseWorkflowNode** - расширение базового класса методами получения промптов
- **Обработка ошибок** - явное прерывание workflow при недоступности сервиса

**Размещение файлов:**
```
learnflow/
├── services/
│   └── prompt_client.py      # HTTP клиент для Prompt Config Service
└── nodes/
    ├── base.py               # Модифицировать базовый класс для работы с сервисом
    ├── content.py            # Использует обновленный базовый класс
    ├── recognition.py        # Использует обновленный базовый класс
    ├── synthesis.py          # Использует обновленный базовый класс
    ├── questions.py          # Использует обновленный базовый класс
    ├── answers.py            # Использует обновленный базовый класс
    └── input_processing.py   # Использует обновленный базовый класс
```

## Полный flow работы функционала

1. **Инициализация узла LangGraph:**
   - Узел создается с thread_id из конфигурации
   - Инициализируется PromptManager с настройками подключения к сервису

2. **Запрос промпта при обработке:**
   - Узел вызывает метод get_system_prompt() из базового класса
   - BaseWorkflowNode извлекает user_id из thread_id (они равны по соглашению)
   - PromptConfigClient формирует HTTP запрос к Prompt Configuration Service

3. **Получение персонализированного промпта:**
   - Сервис динамически извлекает плейсхолдеры из шаблона
   - Использует значения из context (приоритет) и БД пользователя
   - При ошибке сервиса после retry попыток - WorkflowExecutionError
   - Workflow останавливается с явной ошибкой для пользователя

4. **Генерация контента с промптом:**
   - Узел использует полученный промпт для вызова LLM
   - Результат обрабатывается стандартным образом
   - Логирование включает информацию об источнике промпта

## API и интерфейсы

**PromptConfigClient:**
- `async generate_prompt(user_id, node_name, context)` - получить промпт от сервиса
  - Параметры: user_id (int), node_name (str), context (dict)
  - Возвращает: str с текстом промпта
  - Ошибки: WorkflowExecutionError при недоступности после retry попыток
  - Включает retry механизм: 3 попытки с экспоненциальной задержкой

**BaseWorkflowNode (расширение):**
- `async get_system_prompt(state, config)` - метод получения промпта из сервиса
  - Параметры: state (ExamState), config (RunnableConfig)
  - Возвращает: str с системным промптом
  - Извлекает user_id из thread_id
  - Формирует context из состояния workflow
  - Вызывает PromptConfigClient для получения промпта

## Взаимодействие компонентов

```
LangGraph Node (BaseWorkflowNode) -> PromptConfigClient -> Prompt Config Service
                |                            |                       |
                v                            v                       v
        Extract user_id              HTTP POST Request       Generate Prompt
        from thread_id               with retry logic        from user settings
                |                            |                       |
                v                            v                       v
         Form context               Handle response or         Return prompt
         from state                 throw WorkflowError              |
                |                            |                       |
                +----------------------------+-----------------------+
                                            |
                                            v
                                   Final Prompt to LLM
```

**Flow данных:**
1. Node вызывает get_system_prompt() из базового класса
2. BaseWorkflowNode извлекает user_id из thread_id
3. PromptConfigClient делает POST запрос к сервису с retry
4. При успехе - возвращается персонализированный промпт
5. При неудаче после retry - выбрасывается WorkflowExecutionError
6. Промпт передается в LLM для генерации

## Код PromptConfigClient

```python
# learnflow/services/prompt_config_client.py
import asyncio
import httpx
from typing import Optional
from learnflow.exceptions import WorkflowExecutionError

class PromptConfigClient:
    """MVP версия клиента без кэширования - только retry механизм"""
    
    def __init__(self, base_url: str, timeout: int = 5, retry_count: int = 3):
        self.base_url = base_url
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = 0.5  # секунды
    
    async def generate_prompt(self, user_id: int, node_name: str, context: dict) -> str:
        """
        Получает промпт из сервиса конфигурации с retry механизмом.
        При недоступности сервиса - выбрасывает ошибку (без fallback).
        """
        last_error: Optional[Exception] = None
        
        for attempt in range(self.retry_count):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    response = await client.post(
                        f"{self.base_url}/api/v1/generate-prompt",
                        json={
                            "user_id": user_id,
                            "node_name": node_name,
                            "context": context
                        }
                    )
                    response.raise_for_status()
                    return response.json()["prompt"]
                    
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
                last_error = e
                if attempt < self.retry_count - 1:
                    # Экспоненциальная задержка между попытками
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue
        
        # Все попытки исчерпаны - выбрасываем ошибку
        raise WorkflowExecutionError(
            f"Prompt configuration service is unavailable after {self.retry_count} attempts. "
            f"Please try again in a few minutes. Last error: {last_error}"
        )
```

## Порядок реализации

1. **Создание PromptConfigClient:**
   - Использовать код выше для создания клиента
   - Retry механизм: 3 попытки с экспоненциальной задержкой
   - При неудаче - WorkflowExecutionError

2. **Модификация BaseWorkflowNode в base.py:**
   - Добавить метод get_system_prompt
   - Извлечение user_id из thread_id
   - Формирование context из state
   - Вызов PromptConfigClient

3. **Модификация остальных узлов:**
   - content.py - использование get_system_prompt из базового класса
   - recognition.py - аналогичные изменения
   - synthesis.py - с учетом множественных промптов
   - questions.py - адаптация под структуру
   - answers.py - простая замена
   - input_processing.py - минимальные изменения

4. **Добавление конфигурации:**
   - prompt_service_url в settings.py
   - prompt_service_timeout (default: 5)
   - prompt_service_retry_count (default: 3)

## Критичные граничные случаи

**Недоступность сервиса:**
- Workflow останавливается с WorkflowExecutionError
- Пользователь получает явное сообщение об ошибке
- Логирование всех попыток подключения

**Изменение настроек пользователя во время обработки:**
- Изменения применятся в новом thread
- Для текущего thread используются настройки на момент старта

**Некорректный thread_id формат:**
- thread_id должен быть строковым представлением числа (user_id)
- При невалидном формате - возвращать ошибку валидации

**Некорректный ответ от сервиса:**
- Если промпт пустой или null - выбрасывается ошибка валидации
- Валидация минимальной длины промпта (>50 символов)