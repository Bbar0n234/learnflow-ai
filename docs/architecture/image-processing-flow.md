# Предлагаемая архитектура обработки изображений в LearnFlow AI

## Обзор

Документ описывает предлагаемый унифицированный подход к обработке изображений в системе LearnFlow AI, включая загрузку, хранение, обработку и интеграцию с LangGraph workflow.

## Основные принципы

### 1. Единый метод обработки
- Использование единого метода `process_step()` для всех сценариев (с изображениями и без)
- Отказ от отдельного метода `process_step_with_images()`
- Передача изображений через параметр `image_paths: List[str] = None`

### 2. Состояние как источник истины
- Не используем дополнительные флаги для отслеживания состояния изображений
- Полагаемся на семантику полей состояния:
  - `image_paths=None` или `[]` → изображения отсутствуют
  - `image_paths=[...]` → изображения загружены
  - `recognized_notes=None` → распознавание не выполнено
  - `recognized_notes=""` → распознавание выполнено/пропущено, текст пустой
  - `recognized_notes="текст"` → успешное распознавание
  - `recognition_attempts` → счетчик попыток запроса изображений у пользователя

### 3. Использование Command API
- При продолжении workflow с изображениями используем `Command(resume=..., update={...})`
- Поле `update` позволяет добавить изображения в существующее состояние
- Узел может вернуться сам в себя через `Command(goto="recognition_handwritten")` для повторной обработки

### 4. Обработка ошибок и HITL
- При ошибках распознавания пользователь может:
  - Повторить попытку распознавания
  - Загрузить новые изображения
  - Пропустить распознавание и продолжить
- Узел корректно обрабатывает повторные вызовы после interrupt

## Архитектура компонентов

### GraphManager

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
            input_state = ExamState(
                exam_question=query,
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

### RecognitionNode

```python
class RecognitionNode(BaseWorkflowNode):
    """
    Узел распознавания рукописных конспектов с поддержкой:
    - Загрузки изображений в процессе workflow
    - Повторных попыток при ошибках распознавания
    - Пропуска распознавания по желанию пользователя
    """
    
    async def __call__(self, state: ExamState, config) -> Command:
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
        logger.info(f"No images found, requesting from user (attempt {state.recognition_attempts + 1})")
        
        interrupt_json = {
            "message": "📸 Для улучшения качества материала рекомендуется загрузить фото конспектов.\n\n"
                      "Варианты действий:\n"
                      "• Отправьте фотографии ваших конспектов\n"
                      "• Напишите 'пропустить' для продолжения без изображений"
        }
        
        user_response = interrupt(interrupt_json)
        
        # Обработка ответа пользователя
        if 'пропустить' in user_response.lower() or state.recognition_attempts >= 3:
            if state.recognition_attempts >= 3:
                logger.info("Max attempts reached, skipping recognition")
            else:
                logger.info("User chose to skip recognition")
                
            return Command(
                goto="generating_questions",
                update={"synthesized_material": state.generated_material}
            )
        else:
            logger.info("User response received, retrying recognition node")
            return Command(
                goto="recognition_handwritten",
                update={"recognition_attempts": state.recognition_attempts + 1}
            )
```

## Сценарии использования

### Сценарий 1: Старт с изображениями

**Последовательность действий:**

1. **Telegram Bot**: Пользователь отправляет фото + текст вопроса
2. **Bot обработка**:
   ```python
   # Накапливаем фото в pending_media
   pending_media[user_id] = {
       "photos": [photo_data1, photo_data2],
       "text": "Объясните RSA шифрование"
   }
   ```

3. **API вызов**:
   ```python
   # Загрузка изображений
   image_paths = await upload_images(thread_id, photos)
   # Запуск workflow
   result = await graph_manager.process_step(
       thread_id, 
       "Объясните RSA шифрование",
       image_paths
   )
   ```

4. **GraphManager**:
   - Создает новое состояние с `image_paths`
   - Запускает workflow

5. **RecognitionNode**:
   - Обнаруживает `state.image_paths` 
   - Обрабатывает изображения
   - При успехе переходит к `synthesis_material`
   - При ошибке переходит к `generating_questions` (пропуская синтез)

**Результат**: Полный проход workflow с учетом конспектов ✅

### Сценарий 2: Добавление изображений в процессе

**Последовательность действий:**

1. **Начало без изображений**:
   ```python
   # Пользователь: "Объясните RSA шифрование"
   result = await graph_manager.process_step(thread_id, query, None)
   ```

2. **RecognitionNode - первый вызов**:
   - `state.image_paths = None`
   - `state.recognition_attempts = 0`
   - Делает `interrupt` с запросом изображений
   - Workflow полностью останавливается и ждет ответа пользователя

3. **Пользователь отправляет изображения**:
   ```python
   # Bot загружает изображения
   image_paths = await upload_images(thread_id, photos)
   # Продолжает workflow
   result = await graph_manager.process_step(
       thread_id,
       "продолжить", 
       image_paths
   )
   ```

4. **GraphManager - продолжение**:
   ```python
   # Обнаруживает существующее состояние
   # Создает Command с update для добавления изображений
   input_state = Command(
       resume="продолжить",
       update={"image_paths": image_paths}
   )
   ```

5. **RecognitionNode - запускается заново с начала**:
   - `state.image_paths = [path1, path2]` (обновлено через Command.update)
   - Сразу попадает в первое условие `if state.image_paths:`
   - Обрабатывает изображения
   - При успехе переходит к `synthesis_material` с обновлением `recognized_notes`
   - При ошибке переходит к `generating_questions`, устанавливая `synthesized_material = generated_material`

**Результат**: Успешное добавление изображений в процессе ✅

### Сценарий 3: Пропуск изображений

**Последовательность действий:**

1. **После interrupt в RecognitionNode**:
   - Bot: "Загрузите фото или напишите 'пропустить'"
   - Пользователь: "пропустить"

2. **Продолжение без изображений**:
   ```python
   result = await graph_manager.process_step(
       thread_id,
       "пропустить",
       None
   )
   ```

3. **RecognitionNode - запускается заново после interrupt**:
   - Проверяет `state.image_paths` - все еще пусто
   - Снова делает `interrupt` и получает ответ "пропустить"
   - Обрабатывает пропуск:
   ```python
   if "пропустить" in user_response.lower():
       return Command(
           goto="generating_questions",
           update={"synthesized_material": state.generated_material}
       )
   ```

**Результат**: Workflow продолжается без конспектов ✅

### Сценарий 4: Обработка ошибок распознавания

**Последовательность действий:**

1. **RecognitionNode обрабатывает изображения**:
   - Метод `_process_images()` возвращает `None` (ошибка распознавания)

2. **Автоматический переход без синтеза**:
   ```python
   if recognized_text:
       # Успех - идем к синтезу
   else:
       # Ошибка - пропускаем синтез
       return Command(
           goto="generating_questions",
           update={"synthesized_material": state.generated_material}
       )
   ```

3. **Workflow продолжается**:
   - Синтез материалов пропущен
   - `synthesized_material` просто копирует `generated_material`
   - Переход к генерации вопросов

**Результат**: Устойчивость к ошибкам с возможностью повтора ✅

### Сценарий 5: Защита от зацикливания

**Ситуация**: Пользователь многократно не отвечает на запрос изображений

**Обработка**:
```python
if 'пропустить' in user_response.lower() or state.recognition_attempts >= 3:
    if state.recognition_attempts >= 3:
        logger.info("Max attempts reached, skipping recognition")
    # Автоматический пропуск после 3 попыток
    return Command(
        goto="generating_questions",
        update={"synthesized_material": state.generated_material}
    )
```

**Результат**: Защита от бесконечных запросов ✅

## Хранение изображений

### Временное хранилище

**Структура каталогов**:
```
/tmp/learnflow/
└── {thread_id}/
    └── images/
        ├── image_00_{hash}.png
        ├── image_01_{hash}.png
        └── image_02_{hash}.png
```

**Жизненный цикл**:
1. Создание при загрузке через `/upload-images/{thread_id}`
2. Использование в `RecognitionNode`
3. Очистка при вызове `delete_thread(thread_id)`

### API эндпоинты

| Эндпоинт | Метод | Описание |
|----------|-------|----------|
| `/upload-images/{thread_id}` | POST | Загрузка до 10 изображений |
| `/process` | POST | Универсальный метод обработки |
| `/state/{thread_id}` | GET | Получение состояния |
| `/thread/{thread_id}` | DELETE | Удаление thread и файлов |

## Изменения для реализации

### 1. State (ExamState)

**Добавить новое поле**:
```python
class ExamState(TypedDict):
    # ... существующие поля ...
    recognition_attempts: int  # Счетчик попыток распознавания
```

### 2. GraphManager

**Модифицировать**:
```python
async def process_step(self, thread_id: str, query: str, image_paths: List[str] = None):
    state = await self._get_state(thread_id)
    
    if not state.values:
        # Новый workflow
        input_state = ExamState(
            exam_question=query,
            image_paths=image_paths or []
        )
    else:
        # Продолжение workflow
        if image_paths:
            # Добавляем изображения в состояние
            input_state = Command(
                resume=query,
                update={"image_paths": image_paths}
            )
        else:
            # Обычное продолжение
            input_state = Command(resume=query)
```

### 3. API (main.py)

**Модифицировать**:
```python
class ProcessRequest(BaseModel):
    thread_id: Optional[str] = None
    message: str
    image_paths: Optional[List[str]] = None  # Добавить
```

### 4. Telegram Bot

**Модифицировать**:
```python
async def _process_message(
    self, 
    thread_id: str, 
    message_text: str,
    image_paths: List[str] = None  # Добавить
) -> Dict[str, Any]:
    async with session.post(
        f"{self.api_base_url}/process",
        json={
            "message": message_text,
            "thread_id": thread_id,
            "image_paths": image_paths  # Добавить
        }
    )
```

### 5. RecognitionNode

**Реализовать упрощенную логику**:
- Метод `_process_images()` с встроенной логикой retry (3 попытки)
- Использовать `recognition_attempts` для подсчета запросов изображений
- При ошибке распознавания автоматически пропускать синтез
- Поддержка возврата в себя через `Command(goto="recognition_handwritten")` для повторного запроса

## Преимущества подхода

1. **Унификация API** - один метод для всех сценариев
2. **Простота** - нет дублирования кода и логики
3. **Гибкость** - изображения можно добавить в любой момент до обработки
4. **Надежность** - идемпотентность и защита от повторов
5. **Чистота кода** - состояние само документирует себя
6. **Устойчивость к ошибкам** - возможность повторных попыток при сбоях
7. **Улучшенный UX** - пользователь имеет полный контроль над процессом

## Риски и ограничения

1. **Размер изображений** - ограничение 10MB на файл
2. **Количество** - максимум 10 изображений за раз
3. **Временное хранилище** - файлы удаляются при удалении thread
4. **Повторная загрузка** - нельзя заменить уже загруженные изображения

## Тестирование

### Необходимые тест-кейсы

1. **Старт с изображениями** - проверка полного флоу
2. **Добавление в процессе** - проверка Command.update
3. **Пропуск изображений** - проверка обработки "пропустить"
4. **Повторные вызовы** - проверка идемпотентности
5. **Ошибки распознавания** - проверка fallback логики
6. **Большие изображения** - проверка лимитов
7. **Некорректные форматы** - проверка валидации

## Метрики успеха

- Уменьшение кода на ~30% за счет удаления дублирования
- Единая точка входа для всех сценариев
- Улучшение UX - пользователь может добавить изображения когда удобно
- Снижение количества багов за счет упрощения логики

## Следующие шаги

1. Реализовать изменения в GraphManager
2. Обновить API эндпоинты
3. Исправить Telegram Bot
4. Провести тестирование всех сценариев
5. Обновить документацию пользователя