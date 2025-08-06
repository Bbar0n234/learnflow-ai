# Implementation Plan: Базовая инфраструктура и Artifacts Service (Итерация 1)

## Обзор

Данный план описывает создание файлового хранилища с REST API для работы с артефактами LearnFlow AI. Artifacts Service будет служить заменой GitHub интеграции, обеспечивая локальное хранение и управление файлами, создаваемыми workflow.

## Архитектура решения

### Основные компоненты

1. **Artifacts Service** - FastAPI приложение для управления файлами
2. **File Storage System** - локальная файловая система с организованной структурой
3. **Docker Integration** - контейнеризация сервиса и интеграция с docker-compose
4. **API Layer** - REST API для CRUD операций над файлами

### Структура файловой системы

```
artifacts-service/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI приложение
│   ├── models.py         # Pydantic модели
│   ├── storage.py        # файловые операции
│   ├── settings.py       # настройки сервиса
│   └── exceptions.py     # кастомные исключения
├── pyproject.toml        # uv конфигурация (не requirements.txt)
├── Dockerfile
└── README.md

data/artifacts/           # структура хранения с thread_id + session_id
├── {thread_id_1}/        # user_id из Telegram
│   ├── metadata.json     # информация о пользователе и его сессиях
│   └── sessions/
│       ├── {session_id_1}/    # UUID для каждого экзаменационного вопроса
│       │   ├── session_metadata.json
│       │   ├── generated_material.md
│       │   ├── recognized_notes.md
│       │   ├── synthesized_material.md
│       │   ├── gap_questions.md
│       │   └── answers/
│       │       ├── question_1.md
│       │       └── question_2.md
│       └── {session_id_2}/    # следующий вопрос того же пользователя
│           ├── session_metadata.json
│           └── ...
└── {thread_id_2}/
    └── sessions/
        └── ...
```

## API и интерфейсы

### Основные endpoints

#### 1. GET /health
**Назначение:** Health check для проверки доступности сервиса
**Параметры:** Отсутствуют
**Возвращаемые значения:** 
- 200: `{"status": "ok", "service": "artifacts-service"}`
- 503: `{"status": "error", "message": "Service unavailable"}`

#### 2. GET /threads
**Назначение:** Получение списка всех thread'ов (пользователей)
**Параметры:** Отсутствуют
**Возвращаемые значения:**
- 200: `{"threads": [{"thread_id": str, "sessions_count": int, "last_activity": datetime}]}`

#### 3. GET /threads/{thread_id}
**Назначение:** Получение информации о thread'е и его сессиях
**Параметры:**
- `thread_id` (str): Идентификатор thread'а
**Возвращаемые значения:**
- 200: `{"thread_id": str, "sessions": [{"session_id": str, "exam_question": str, "created": datetime, "status": str}]}`
- 404: `{"error": "Thread not found"}`

#### 4. GET /threads/{thread_id}/sessions/{session_id}
**Назначение:** Получение списка файлов в конкретной сессии
**Параметры:**
- `thread_id` (str): Идентификатор thread'а
- `session_id` (str): Идентификатор сессии
**Возвращаемые значения:**
- 200: `{"thread_id": str, "session_id": str, "files": [{"path": str, "size": int, "modified": datetime}]}`
- 404: `{"error": "Thread or session not found"}`

#### 5. GET /threads/{thread_id}/sessions/{session_id}/{path:path}
**Назначение:** Получение содержимого конкретного файла в сессии
**Параметры:**
- `thread_id` (str): Идентификатор thread'а
- `session_id` (str): Идентификатор сессии
- `path` (str): Путь к файлу относительно директории сессии
**Возвращаемые значения:**
- 200: Содержимое файла (text/plain или application/json)
- 404: `{"error": "File not found"}`

#### 6. POST /threads/{thread_id}/sessions/{session_id}/{path:path}
**Назначение:** Создание или обновление файла в сессии
**Параметры:**
- `thread_id` (str): Идентификатор thread'а
- `session_id` (str): Идентификатор сессии
- `path` (str): Путь к файлу
- Body: `{"content": str, "content_type": str?, "metadata": dict?}`
**Возвращаемые значения:**
- 201: `{"message": "File created", "path": str}`
- 200: `{"message": "File updated", "path": str}`
- 400: `{"error": "Invalid path or content"}`

#### 7. DELETE /threads/{thread_id}/sessions/{session_id}/{path:path}
**Назначение:** Удаление файла из сессии
**Параметры:**
- `thread_id` (str): Идентификатор thread'а
- `session_id` (str): Идентификатор сессии
- `path` (str): Путь к файлу
**Возвращаемые значения:**
- 200: `{"message": "File deleted"}`
- 404: `{"error": "File not found"}`

#### 8. DELETE /threads/{thread_id}/sessions/{session_id}
**Назначение:** Удаление целой сессии со всеми файлами
**Параметры:**
- `thread_id` (str): Идентификатор thread'а
- `session_id` (str): Идентификатор сессии
**Возвращаемые значения:**
- 200: `{"message": "Session deleted"}`
- 404: `{"error": "Session not found"}`

### Pydantic модели

#### FileInfo
```python
class FileInfo(BaseModel):
    path: str
    size: int
    modified: datetime
    content_type: str
```

#### FileContent
```python
class FileContent(BaseModel):
    content: str
    content_type: str = "text/markdown"
    metadata: Optional[Dict[str, Any]] = None
```

#### SessionInfo
```python
class SessionInfo(BaseModel):
    session_id: str
    exam_question: str
    created: datetime
    modified: datetime
    status: str  # "active", "completed", "failed"
    files_count: int
```

#### SessionMetadata
```python
class SessionMetadata(BaseModel):
    session_id: str
    thread_id: str
    exam_question: str
    created: datetime
    modified: datetime
    status: str
    workflow_data: Optional[Dict[str, Any]] = None  # данные из ExamState
```

#### ThreadInfo
```python
class ThreadInfo(BaseModel):
    thread_id: str
    sessions: List[SessionInfo]
    created: datetime
    last_activity: datetime
    sessions_count: int
```

#### ThreadMetadata
```python
class ThreadMetadata(BaseModel):
    thread_id: str
    created: datetime
    last_activity: datetime
    sessions_count: int
    user_info: Optional[Dict[str, Any]] = None  # информация о пользователе Telegram
```

### Storage класс

#### ArtifactsStorage
**Основные методы:**

**Thread management:**
- `create_thread_directory(thread_id: str) -> Path`: Создание директории для thread'а
- `get_threads() -> List[ThreadInfo]`: Получение списка всех thread'ов
- `get_thread_info(thread_id: str) -> ThreadInfo`: Информация о thread'е и его сессиях
- `delete_thread(thread_id: str) -> bool`: Удаление thread'а со всеми сессиями

**Session management:**
- `create_session_directory(thread_id: str, session_id: str) -> Path`: Создание сессии
- `get_session_files(thread_id: str, session_id: str) -> List[FileInfo]`: Файлы сессии
- `get_session_metadata(thread_id: str, session_id: str) -> SessionMetadata`: Метаданные сессии
- `update_session_metadata(thread_id: str, session_id: str, metadata: SessionMetadata) -> bool`: Обновление метаданных
- `delete_session(thread_id: str, session_id: str) -> bool`: Удаление сессии

**File operations:**
- `read_file(thread_id: str, session_id: str, path: str) -> str`: Чтение содержимого файла
- `write_file(thread_id: str, session_id: str, path: str, content: str, metadata: dict = None) -> bool`: Запись файла
- `delete_file(thread_id: str, session_id: str, path: str) -> bool`: Удаление файла

**Validation:**
- `validate_thread_id(thread_id: str) -> bool`: Валидация thread_id
- `validate_session_id(session_id: str) -> bool`: Валидация session_id
- `validate_path(path: str) -> bool`: Валидация пути файла

## Взаимодействие компонентов

### Архитектурный flow

1. **Request Processing**: FastAPI получает HTTP запрос
2. **Path Validation**: Проверка безопасности пути файла и валидация thread_id/session_id
3. **Thread/Session Management**: Проверка/создание структуры thread'а и сессии
4. **Metadata Operations**: Обновление метаданных thread'а и сессии
5. **Storage Operations**: Выполнение файловых операций через ArtifactsStorage
6. **Response Formation**: Формирование JSON ответа с использованием Pydantic моделей

### Пример типичного workflow:

1. **LearnFlow workflow начинается**:
   - `POST /threads/{thread_id}/sessions/{session_id}/session_metadata.json`
   - Создается структура сессии, сохраняются метаданные

2. **Генерация контента**:
   - `POST /threads/{thread_id}/sessions/{session_id}/generated_material.md`
   - Обновляются метаданные сессии

3. **Распознавание изображений** (если есть):
   - `POST /threads/{thread_id}/sessions/{session_id}/recognized_notes.md`

4. **Синтез материала**:
   - `POST /threads/{thread_id}/sessions/{session_id}/synthesized_material.md`

5. **Генерация вопросов**:
   - `POST /threads/{thread_id}/sessions/{session_id}/gap_questions.md`

6. **Генерация ответов**:
   - `POST /threads/{thread_id}/sessions/{session_id}/answers/question_1.md`
   - `POST /threads/{thread_id}/sessions/{session_id}/answers/question_2.md`

7. **Завершение workflow**:
   - Обновление статуса сессии в метаданных на "completed"

### Интеграция с существующим проектом

1. **uv workspace**: Добавление `artifacts-service` в `pyproject.toml` как workspace member
2. **docker-compose**: Добавление нового сервиса с портом 8001
3. **Volume mounts**: Общие `./data` volume для доступа к артефактам
4. **Environment variables**: Настройка через `.env` файл

## Edge Cases и особенности

### Безопасность файловой системы

1. **Path Traversal Protection**: 
   - Валидация путей на предмет `../` и абсолютных путей
   - Whitelist разрешенных символов в именах файлов
   - Проверка глубины вложенности (максимум 3 уровня)

2. **File Size Limits**:
   - Максимальный размер файла: 10MB
   - Максимальное количество файлов в thread'е: 100

3. **Content Type Validation**:
   - Поддержка только text/markdown, application/json, text/plain
   - Проверка содержимого на соответствие заявленному типу

### Обработка ошибок

1. **Storage Errors**:
   - Недоступность файловой системы
   - Нехватка места на диске
   - Права доступа к директориям

2. **Concurrency**:
   - Блокировка файлов при записи
   - Обработка одновременных запросов к одному файлу
   - Atomic операции записи через временные файлы

3. **Thread Management**:
   - Создание thread директории при первом обращении
   - Очистка пустых thread директорий
   - Ограничение количества thread'ов

### Производительность

1. **File System Caching**: 
   - Кэширование метаданных файлов в памяти
   - Lazy loading содержимого файлов
   - Debounced file system watches для изменений

2. **Response Optimization**:
   - Streaming для больших файлов
   - Gzip сжатие для JSON ответов
   - ETags для кэширования на клиенте

## Детальный план реализации

### Шаг 1: Создание базовой структуры

1. **Создать директорию `artifacts-service/`**
2. **Настроить uv workspace**:
   - Добавить `artifacts-service` в root `pyproject.toml`
   - Создать `artifacts-service/pyproject.toml` с зависимостями
3. **Создать базовую структуру приложения**:
   - `app/__init__.py`
   - `app/main.py` с базовым FastAPI app
   - `app/settings.py` с Pydantic settings

### Шаг 2: Реализация Storage системы

1. **Создать `app/storage.py`**:
   - Класс `ArtifactsStorage` с базовыми методами
   - Path validation логика
   - File system operations с error handling
2. **Создать `app/exceptions.py`**:
   - Кастомные исключения для различных ошибок
   - HTTP exception mappers
3. **Создать `data/artifacts/` директорию**

### Шаг 3: Реализация API endpoints

1. **Создать `app/models.py`**:
   - Pydantic модели для request/response
   - Validation rules для file paths и content
2. **Реализовать endpoints в `app/main.py`**:
   - Health check endpoint
   - CRUD операции для файлов
   - Error handling middleware

### Шаг 4: Контейнеризация

1. **Создать `Dockerfile`**:
   - Multi-stage build с uv
   - Оптимизированный Python image
   - Health check команда
2. **Обновить `docker-compose.yaml`**:
   - Добавить artifacts-service сервис
   - Настроить volume mounts
   - Environment variables

### Шаг 5: Конфигурация окружения

1. **Обновить `.env.example`**:
   - Добавить переменные для artifacts service
   - Настройки портов и путей
2. **Создать `artifacts-service/README.md`**:
   - Документация по API
   - Примеры использования
   - Инструкции по развертыванию

## Критерии готовности и тестирование

### Automated Tests

1. **Unit Tests** для Storage класса:
   - Path validation
   - File operations
   - Error handling

2. **Integration Tests** для API endpoints:
   - CRUD операции
   - Error responses
   - File system integration

3. **Docker Tests**:
   - Container startup
   - Health check endpoint
   - Volume mounting

### Manual Testing Checklist

1. **Service Startup**:
   - [ ] `docker-compose up artifacts-service` успешно запускается
   - [ ] Health check endpoint доступен на `localhost:8001/health`
   - [ ] Логи показывают успешную инициализацию

2. **API Functionality**:
   - [ ] POST создает новые файлы в правильной структуре thread_id/sessions/session_id
   - [ ] GET возвращает содержимое файлов из сессий
   - [ ] GET списка thread'ов и сессий работает корректно
   - [ ] DELETE удаляет файлы и сессии
   - [ ] Валидация путей блокирует опасные запросы
   - [ ] Метаданные thread'ов и сессий корректно обновляются

3. **File System Integration**:
   - [ ] Файлы сохраняются в `data/artifacts/{thread_id}/sessions/{session_id}/`
   - [ ] Метаданные сохраняются в правильных местах
   - [ ] Структура директорий создается автоматически
   - [ ] Permissions настроены корректно

4. **Session Management**:
   - [ ] Создание новых сессий работает
   - [ ] Метаданные сессий корректно отслеживают статус
   - [ ] Удаление сессий очищает все связанные файлы
   - [ ] Thread'ы корректно отслеживают количество сессий

5. **Error Handling**:
   - [ ] 404 для несуществующих файлов/thread'ов/сессий
   - [ ] 400 для некорректных путей и session_id/thread_id
   - [ ] Graceful handling file system errors

### Команды для тестирования

```bash
# Health check
curl http://localhost:8001/health

# Получение списка thread'ов
curl http://localhost:8001/threads

# Получение информации о thread'е
curl http://localhost:8001/threads/12345678

# Создание файла в сессии
curl -X POST http://localhost:8001/threads/12345678/sessions/uuid-session-1/generated_material.md \
  -H "Content-Type: application/json" \
  -d '{"content": "# Сгенерированный материал\n\nТекст материала...", "content_type": "text/markdown"}'

# Чтение файла из сессии
curl http://localhost:8001/threads/12345678/sessions/uuid-session-1/generated_material.md

# Список файлов в сессии
curl http://localhost:8001/threads/12345678/sessions/uuid-session-1

# Создание файла ответа
curl -X POST http://localhost:8001/threads/12345678/sessions/uuid-session-1/answers/question_1.md \
  -H "Content-Type: application/json" \
  -d '{"content": "# Ответ на вопрос 1\n\nОтвет...", "content_type": "text/markdown"}'

# Удаление файла из сессии
curl -X DELETE http://localhost:8001/threads/12345678/sessions/uuid-session-1/answers/question_1.md

# Удаление целой сессии
curl -X DELETE http://localhost:8001/threads/12345678/sessions/uuid-session-1
```

## Технические детали

### Dependencies (pyproject.toml)

```toml
[project]
dependencies = [
    "fastapi>=0.104.0",
    "uvicorn[standard]>=0.24.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
]

[tool.uv.sources]
# Наследование от root workspace
```

### Environment Variables

```bash
# Artifacts Service Settings
ARTIFACTS_SERVICE_HOST=0.0.0.0
ARTIFACTS_SERVICE_PORT=8001
ARTIFACTS_DATA_PATH=./data/artifacts
ARTIFACTS_MAX_FILE_SIZE=10485760  # 10MB
ARTIFACTS_MAX_FILES_PER_THREAD=100
```

## Интеграция с LearnFlow AI

### Получение session_id из GraphManager

Для корректной работы с session_id необходимо модифицировать `GraphManager`:

```python
# В learnflow/graph_manager.py
def get_current_session_id(self, thread_id: str) -> Optional[str]:
    """Получение текущего session_id для thread'а"""
    return self.user_sessions.get(thread_id)

async def save_artifact_to_service(self, thread_id: str, filename: str, content: str):
    """Сохранение артефакта в Artifacts Service"""
    session_id = self.get_current_session_id(thread_id)
    if not session_id:
        logger.error(f"No session_id found for thread {thread_id}")
        return
    
    # HTTP запрос к Artifacts Service
    async with aiohttp.ClientSession() as session:
        url = f"http://localhost:8001/threads/{thread_id}/sessions/{session_id}/{filename}"
        data = {"content": content, "content_type": "text/markdown"}
        await session.post(url, json=data)
```

Этот план обеспечивает создание полнофункционального Artifacts Service, который интегрируется с существующей архитектурой LearnFlow AI, сохраняет всю историю вопросов пользователя, и готов для дальнейшего развития в последующих итерациях.