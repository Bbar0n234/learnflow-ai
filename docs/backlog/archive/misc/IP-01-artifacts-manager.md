# Implementation Plan: Local Artifacts Manager (IP-01)

## Архитектура решения

### Основные компоненты

1. **LocalArtifactsManager** (`learnflow/artifacts_manager.py`)
   - Основной класс для управления локальными артефактами
   - Прямая замена `GitHubArtifactPusher` с идентичным интерфейсом
   - Атомарные файловые операции с proper error handling

2. **ArtifactsConfig** 
   - Конфигурация для локального хранения (базовый путь, права доступа)
   - Замена `GitHubConfig`

3. **Файловая структура артефактов**
   ```
   data/artifacts/
   ├── {thread_id}/
   │   ├── metadata.json              # Thread-level metadata
   │   └── sessions/
   │       └── {session_id}/
   │           ├── session_metadata.json    # Session-level metadata  
   │           ├── generated_material.md    # push_learning_material()
   │           ├── recognized_notes.md      # push_recognized_notes()
   │           ├── synthesized_material.md  # push_synthesized_material()
   │           ├── questions.md         # push_questions_and_answers()
   │           └── answers/                 # Individual answer files
   │               ├── answer_001.md
   │               └── answer_002.md
   ```

### Модули взаимодействия

1. **Settings** (`learnflow/settings.py`)
   - Добавить настройки локального artifacts storage
   - Заменить GitHub-специфичные настройки

2. **GraphManager** (`learnflow/graph_manager.py`)
   - Заменить `GitHubArtifactPusher` на `LocalArtifactsManager`
   - Обновить методы пуша артефактов

3. **State** (`learnflow/state.py`)
   - Заменить GitHub-специфичные поля на локальные file paths
   - Добавить поля для session_id tracking

## API и интерфейсы

### LocalArtifactsManager

#### Конфигурация
```python
class ArtifactsConfig(BaseModel):
    base_path: str = "data/artifacts"
    ensure_permissions: bool = True
    atomic_writes: bool = True
```

#### Основные методы (сохраняют совместимость с GitHub API)

**push_learning_material(thread_id, input_content, generated_material) -> Dict[str, Any]**
- Назначение: Создает session и сохраняет generated_material.md
- Параметры:
  - thread_id: str - идентификатор потока
  - input_content: str - исходный экзаменационный вопрос  
  - generated_material: str - сгенерированный материал
- Возвращает: 
  ```python
  {
      "success": bool,
      "file_path": str,        # Относительный путь к файлу
      "folder_path": str,      # Путь к session папке
      "session_id": str,       # Автосгенерированный session ID
      "thread_path": str,      # Путь к thread папке
      "absolute_path": str,    # Абсолютный путь к файлу
      "error": str             # При success=False
  }
  ```

**push_recognized_notes(folder_path, recognized_notes, thread_id) -> Dict[str, Any]**
- Назначение: Сохраняет recognized_notes.md в существующую session
- Параметры:
  - folder_path: str - путь к session (из предыдущего вызова)
  - recognized_notes: str - распознанный текст
  - thread_id: str - для логирования
- Возвращает: success/error status + file paths

**push_synthesized_material(folder_path, synthesized_material, thread_id) -> Dict[str, Any]**
- Назначение: Сохраняет synthesized_material.md
- Параметры: аналогично recognized_notes
- Возвращает: success/error status + file paths

**push_questions_and_answers(folder_path, questions, questions_and_answers, thread_id) -> Dict[str, Any]**
- Назначение: Сохраняет questions.md и отдельные answer файлы
- Параметры:
  - folder_path: str - путь к session
  - questions: List[str] - список gap questions
  - questions_and_answers: List[str] - список Q&A пар
  - thread_id: str - для логирования
- Возвращает: success/error status + файлы paths

**push_complete_materials(thread_id, input_content, all_materials) -> Dict[str, Any]**
- Назначение: Комплексное сохранение всех материалов
- Параметры:
  - thread_id: str
  - input_content: str
  - all_materials: Dict с ключами generated_material, recognized_notes, etc.
- Возвращает: сводную информацию обо всех сохраненных файлах

#### Вспомогательные методы

**_create_thread_metadata(thread_id, input_content) -> Dict[str, Any]**
- Создание thread-level metadata.json

**_create_session_metadata(session_id, thread_id, input_content) -> Dict[str, Any]**  
- Создание session-level metadata.json

**_ensure_directory_exists(path) -> None**
- Создание директорий с proper permissions

**_atomic_write_file(file_path, content) -> None**
- Атомарная запись файла (temp file + rename)

**_generate_session_id(thread_id, input_content) -> str**
- Генерация уникального session ID

#### Content Creation Methods (из GitHub integration)

**_create_learning_material_content(input_content, generated_material, thread_id, session_id) -> str**
**_create_recognized_notes_content(recognized_notes, thread_id) -> str**  
**_create_synthesized_material_content(synthesized_material, thread_id) -> str**
**_create_questions_content(questions, questions_and_answers, thread_id) -> str**

### Metadata Структуры

#### Thread Metadata (metadata.json)
```python
{
    "thread_id": str,
    "created": str,           # ISO datetime
    "last_activity": str,     # ISO datetime  
    "sessions_count": int,
    "user_info": Optional[Dict]
}
```

#### Session Metadata (session_metadata.json)
```python  
{
    "session_id": str,
    "thread_id": str,
    "input_content": str,
    "created": str,
    "modified": str,
    "status": str,            # "active", "completed"
    "workflow_data": Optional[Dict],
    "files": List[str]        # Список созданных файлов
}
```

## Взаимодействие компонентов

### Инициализация в GraphManager
1. Settings загружает конфигурацию artifacts storage
2. GraphManager создает `LocalArtifactsManager` вместо `GitHubArtifactPusher`
3. Все вызовы `github_pusher.*` заменяются на `artifacts_manager.*`

### Workflow процесс
1. **generating_content** node завершается → `push_learning_material()` создает session
2. **recognition_handwritten** node → `push_recognized_notes()` добавляет в session  
3. **synthesis_material** node → `push_synthesized_material()` добавляет в session
4. **generating_questions** + **answer_question** nodes → `push_questions_and_answers()`
5. Thread completion → `push_complete_materials()` финализирует все данные

### File System Organization
- Thread создается при первом `push_learning_material()`
- Session создается автоматически с timestamp-based ID
- Metadata обновляется при каждой файловой операции
- Files немедленно доступны artifacts-service через file system

## Edge Cases и особенности

### Конкуренция и атомарность
- Атомарная запись через temporary files + rename операции
- File locking для предотвращения concurrent writes
- Proper cleanup при failed operations

### Session ID Generation
- Format: `session-{timestamp}-{short_hash}` 
- Уникальность в рамках thread
- Sortable chronologically

### Error Handling
- Graceful fallback если директории не существуют
- Detailed error messages с context information  
- Rollback capability для failed operations
- Logging всех file system операций

### Path Management  
- Использование `pathlib.Path` для cross-platform compatibility
- Validation входящих path параметров
- Sanitization для безопасности file system

### Metadata Consistency
- Thread metadata updates при каждой session operation
- Session metadata tracks все созданные files
- Timestamps в UTC with proper timezone handling

### Web UI Compatibility
- File paths compatible с artifacts-service expectations
- Immediate availability без additional processing
- Metadata structure matches existing artifacts-service models

### Migration Considerations
- Direct migration strategy (MVP stage, no backward compatibility required)
- Clean removal of GitHub-specific functionality
- Simplified migration path with direct replacement

### Performance Optimizations  
- Minimal metadata I/O operations
- Efficient directory structure для faster file access
- Optional compression для large content files
- Configurable cleanup policies для old sessions

### Security
- Path traversal protection
- File permission management
- Content sanitization для markdown files
- Size limits для uploaded content

## Integration Points

### Settings Migration
```python
# Заменить GitHub settings
artifacts_base_path: str = "data/artifacts"
artifacts_ensure_permissions: bool = True  
artifacts_max_file_size: int = 10 * 1024 * 1024  # 10MB

# Удалить GitHub-specific settings
# github_token, github_repository, etc.
```

### State Model Changes
```python
# Заменить в GeneralState
local_session_path: Optional[str] = None
local_thread_path: Optional[str] = None  
session_id: Optional[str] = None

# Удалить GitHub fields
# github_folder_path, github_learning_material_url, etc.
```

### GraphManager Updates
- Заменить `GitHubArtifactPusher` initialization
- Update все `_push_*_to_github` methods
- Remove GitHub-specific data storage logic
- Update state field mappings

## Testing и Validation

### Unit Tests
- File operations (create, read, update)
- Metadata generation and consistency
- Error handling scenarios
- Path management and security

### Integration Tests  
- Full workflow execution с файловыми outputs
- artifacts-service compatibility  
- Concurrent operations handling
- Migration от GitHub storage

### Validation Criteria
1. Все artifacts немедленно visible в Web UI
2. File structure matches artifacts-service expectations
3. Performance не worse than GitHub integration
4. Error recovery и cleanup functionality
5. Clean removal of GitHub dependencies

## Migration Strategy (Direct Migration)

### Phase 1: Implementation
1. Создать `LocalArtifactsManager` с совместимым API
2. Add artifacts settings к `Settings`
3. Create unit tests для core functionality

### Phase 2: Direct Migration  
1. **Полная замена** `GitHubArtifactPusher` на `LocalArtifactsManager` в `GraphManager`
2. **Прямое удаление** GitHub-specific fields из `GeneralState` model
3. **Немедленное обновление** всех вызовов к новому API
4. Add integration tests

### Phase 3: Cleanup
1. **Удалить весь GitHub integration код** (`github.py`, GitHub settings)
2. **Очистить dependencies** от GitHub-specific packages
3. Update configuration templates и documentation  

### Phase 4: Validation
1. End-to-end testing с Web UI
2. Performance benchmarking
3. Production deployment validation

### No Rollback Plan Required
- MVP stage не требует backward compatibility
- Clean architecture с прямой заменой
- Simplified codebase без legacy support