# IP-01: Унифицированная обработка изображений в LearnFlow AI

## Смысл и цель задачи

Объединить два существующих метода обработки (`process_step()` и `process_step_with_images()`) в единый унифицированный подход, поддерживающий все сценарии работы с изображениями и текстовыми конспектами. Это упростит архитектуру, уберет дублирование кода и улучшит UX за счет возможности добавления изображений и текстовых заметок в любой момент workflow.

## Архитектура решения

Основные компоненты для модификации:
- **GraphManager** (`learnflow/core/graph_manager.py`) - унификация методов обработки
- **RecognitionNode** (`learnflow/nodes/recognition.py`) - поддержка текстовых конспектов
- **API endpoints** (`learnflow/api/main.py`) - обновление моделей запросов
- **Telegram Bot** (`bot/main.py`, `bot/services/api_client.py`) - поддержка нового API

Размещение файлов остается прежним в существующей структуре проекта.

## Полный flow работы функционала

### Сценарий 1: Старт с изображениями
1. Пользователь отправляет фото + текст вопроса в Telegram
2. Bot накапливает медиа в `pending_media` 
3. Bot загружает изображения через `/upload-images/{thread_id}`
4. Bot вызывает унифицированный `process_step()` с параметром `image_paths`
5. GraphManager создает новое состояние с `input_content` и `image_paths`
6. RecognitionNode обнаруживает изображения и обрабатывает их
7. При успехе идет синтез материалов, при ошибке - пропуск к вопросам

### Сценарий 2: Добавление текстовых конспектов
1. Пользователь начинает без изображений
2. RecognitionNode делает interrupt с запросом конспектов
3. Пользователь вводит текст конспектов (>50 символов)
4. RecognitionNode проверяет длину и использует текст как `recognized_notes`
5. Переход к синтезу материалов с текстовыми конспектами

### Сценарий 3: Добавление изображений в процессе
1. После interrupt RecognitionNode запрашивает конспекты
2. Пользователь отправляет изображения
3. Bot загружает изображения и вызывает `process_step()` с `image_paths`
4. GraphManager создает `Command(resume=..., update={"image_paths": ...})`
5. RecognitionNode перезапускается и обрабатывает новые изображения

### Сценарий 4: Пропуск конспектов
1. RecognitionNode запрашивает конспекты через interrupt
2. Пользователь отвечает "пропустить"
3. RecognitionNode переходит к `generating_questions` без синтеза
4. `synthesized_material` копирует `generated_material`

## API и интерфейсы

### GraphManager.process_step()
- **Название**: `process_step`
- **Назначение**: Универсальный метод обработки всех сценариев workflow
- **Параметры**: 
  - `thread_id` - идентификатор потока
  - `query` - текстовый запрос или команда
  - `image_paths` (опционально) - список путей к изображениям
- **Возвращает**: словарь с `thread_id` и `result` (сообщения)
- **Критичные ошибки**: отсутствие GraphManager, ошибки БД

### RecognitionNode.__call__()
- **Название**: `__call__`
- **Назначение**: Обработка конспектов (изображения, текст, пропуск)
- **Параметры**:
  - `state` - состояние workflow с возможными `image_paths`
  - `config` - конфигурация LangGraph
- **Возвращает**: `Command` с переходом и обновлением состояния
- **Критичные ошибки**: ошибки распознавания изображений (обрабатываются gracefully)

### RecognitionNode валидация
- **MIN_TEXT_LENGTH = 50** - минимальная длина текста для валидных конспектов
- Текст короче трактуется как пропуск
- Поддержка ключевых слов: "пропустить", "skip", "нет"

## Взаимодействие компонентов

```
Telegram Bot -> API /process -> GraphManager.process_step()
                                       |
                                       v
                              [Новый workflow?]
                                 /          \
                               Да           Нет  
                               /              \
                        GeneralState         Command(resume)
                     (input_content,       (+update если
                      image_paths)         есть image_paths)
                            |                    |
                            v                    v
                      RecognitionNode <----------
                            |
                     [Есть image_paths?]
                        /           \
                      Да            Нет
                      /               \
              Обработка          interrupt
              изображений        (запрос)
                   |                  |
                   v                  v
            synthesis_material   Ответ пользователя
                                      |
                              [Тип ответа?]
                           /      |         \
                    Изображения  Текст   "пропустить"
                         |        |           |
                    Рестарт   Валидация    Пропуск
                     узла      длины      синтеза
```

## Порядок реализации

### Шаг 1: Унификация GraphManager (РЕАЛИЗАЦИЯ)

```python
class GraphManager:
    async def process_step(
        self, 
        thread_id: str, 
        query: str, 
        image_paths: List[str] = None
    ) -> Dict[str, Any]:
        """
        Универсальный метод для обработки шагов workflow.
        
        Args:
            thread_id: Идентификатор потока
            query: Текстовый запрос или команда
            image_paths: Опциональный список путей к изображениям
            
        Returns:
            Результат обработки с thread_id и сообщениями
        """
        state = await self._get_state(thread_id)
        
        if not state.values:
            # Новый workflow - создаем начальное состояние
            input_state = GeneralState(
                input_content=query,
                image_paths=image_paths or []
            )
            session_id = self.create_new_session(thread_id)
        else:
            # Продолжение существующего workflow
            if image_paths:
                # Добавляем изображения через Command.update
                input_state = Command(
                    resume=query,
                    update={"image_paths": image_paths}
                )
            else:
                # Обычное продолжение без изображений
                input_state = Command(resume=query)
            
            session_id = self.get_session_id(thread_id) or self.create_new_session(thread_id)
        
        # Конфигурация и запуск workflow
        cfg = {
            "configurable": {"thread_id": thread_id},
            "callbacks": [self.langfuse_handler],
            "metadata": {
                "langfuse_session_id": session_id,
                "langfuse_user_id": thread_id
            },
        }
        
        # ... продолжение обработки
```

### Шаг 2: Обновление RecognitionNode (РЕАЛИЗАЦИЯ)

```python
class RecognitionNode(BaseWorkflowNode):
    """
    Узел обработки конспектов с поддержкой:
    - Распознавания изображений рукописных конспектов
    - Прямого ввода текстовых конспектов (печатный вид)
    - Валидации минимальной длины текста
    - Пропуска обработки по желанию пользователя
    """
    
    MIN_TEXT_LENGTH = 50  # Минимальная длина для валидного текста конспекта
    
    async def __call__(self, state: GeneralState, config) -> Command:
        thread_id = config["configurable"]["thread_id"]
        logger.info(f"RecognitionNode started for thread {thread_id}")
        
        # Если есть изображения - пытаемся распознать
        if state.image_paths:
            logger.info(f"Found {len(state.image_paths)} images, starting recognition")
            
            recognized_text = await self._process_images(state.image_paths)
            
            if recognized_text:
                logger.info(f"Recognition successful, proceeding to synthesis")
                return Command(
                    goto="synthesis_material",
                    update={"recognized_notes": recognized_text}
                )
            else:
                logger.warning(f"Recognition failed, skipping synthesis")
                return Command(
                    goto="generating_questions",
                    update={"synthesized_material": state.generated_material}
                )
        
        # Нет изображений - запрашиваем у пользователя
        logger.info(f"No images found, requesting notes from user")
        
        interrupt_json = {
            "message": "📸 Для улучшения качества материала рекомендуется добавить ваши конспекты.\n\n"
                      "Варианты действий:\n"
                      "• Отправьте фотографии рукописных конспектов\n"
                      "• Вставьте текст уже распознанных/печатных конспектов\n"
                      "• Напишите 'пропустить' для продолжения без конспектов"
        }
        
        user_response = interrupt(interrupt_json)
        
        # Обработка ответа пользователя
        if 'пропустить' in user_response.lower():
            logger.info("User chose to skip notes")
            return Command(
                goto="generating_questions",
                update={"synthesized_material": state.generated_material}
            )
        
        # Проверяем длину текста для валидации
        cleaned_text = user_response.strip()
        if len(cleaned_text) < self.MIN_TEXT_LENGTH:
            logger.warning(f"Text too short ({len(cleaned_text)} chars), treating as skip")
            return Command(
                goto="generating_questions",
                update={"synthesized_material": state.generated_material}
            )
        
        # Текст достаточной длины - используем как распознанные конспекты
        logger.info(f"Received text notes ({len(cleaned_text)} chars), proceeding to synthesis")
        return Command(
            goto="synthesis_material",
            update={"recognized_notes": cleaned_text}
        )
```

### Шаг 3: Модификация API endpoints

Обновить модель `ProcessRequest` для поддержки `image_paths`:
- Добавить поле `image_paths: Optional[List[str]]`
- Использовать единый эндпоинт `/process` для всех сценариев
- Удалить или deprecated `/process-with-images`

### Шаг 4: Обновление Telegram Bot

Модифицировать `_process_message()` для передачи изображений:
- Добавить параметр `image_paths` в метод
- Передавать `image_paths` в JSON запросе к API
- Унифицировать обработку с изображениями и без

### Шаг 5: Тестирование

Протестировать все сценарии из документа:
1. Старт с изображениями
2. Добавление текстовых конспектов
3. Добавление изображений в процессе
4. Пропуск конспектов
5. Короткий текст (автопропуск)
6. Ошибки распознавания

## Критичные граничные случаи

### Валидация текста конспектов
- Текст менее 50 символов автоматически трактуется как пропуск
- Это предотвращает использование коротких ответов типа "ок" как конспектов
- Пользователь не блокируется - workflow продолжается

### Обработка ошибок распознавания
- При ошибке OCR узел не падает, а пропускает синтез
- `synthesized_material` копирует `generated_material`
- Workflow продолжается к генерации вопросов

### Повторная загрузка изображений
- Через `Command.update` можно добавить изображения в процессе
- Узел может вернуться в себя через `goto="recognition_handwritten"`
- Состояние корректно обновляется без потери данных