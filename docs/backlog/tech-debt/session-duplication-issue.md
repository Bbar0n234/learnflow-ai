# TECH-DEBT: Дублирование директорий сессий в системе артефактов

**Приоритет:** 🔴 Высокий  
**Категория:** Bug/Architecture  
**Статус:** Открыт  
**Дата обнаружения:** 2025-08-12  
**Модули:** `GraphManager`, `LocalArtifactsManager`

## Описание проблемы

При работе с системой LearnFlow AI наблюдается создание **множественных директорий сессий** для одного и того же экзаменационного вопроса. Первый сгенерированный материал сохраняется в отдельной директории от остального материала сессии.

### Примеры проблемного поведения

```
data/artifacts/979557959/sessions/
├── session-20250812_193607-bb111996/    # Только generated_material.md
├── session-20250812_194552-bb111996/    # Только generated_material.md  
└── session-20250812_194751-bb111996/    # Полный набор файлов
    ├── generated_material.md
    ├── recognized_notes.md
    ├── synthesized_material.md
    ├── gap_questions.md
    └── answers/
```

## Корень проблемы

### 1. Дублирующие события в GraphManager

В файле `learnflow/core/graph_manager.py` есть **два идентичных блока кода**, которые вызывают `_push_learning_material_to_artifacts()` при завершении узла `generating_content`:

- **Строки 387-392** в методе `stream_with_images()`
- **Строки 501-506** в методе `stream()`

```python
# Дублирующий код в обоих методах:
if node_name == "generating_content":
    logger.info(f"Content generation completed for thread {thread_id}, pushing to GitHub...")
    current_state = await self._get_state(thread_id)
    artifacts_data = await self._push_learning_material_to_artifacts(thread_id, {
        "exam_question": current_state.values.get("exam_question"),
        "generated_material": node_data.get("generated_material"),
    })
    if artifacts_data:
        await self._update_state(thread_id, artifacts_data)
```

### 2. Timestamp-based генерация session_id

В `LocalArtifactsManager._generate_session_id()` (строка 84-92):

```python
def _generate_session_id(self, thread_id: str, exam_question: str) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  # ← Каждый раз новый!
    hash_input = f"{thread_id}_{exam_question}".encode('utf-8')
    short_hash = hashlib.md5(hash_input).hexdigest()[:8]
    return f"session-{timestamp}-{short_hash}"
```

**Каждый вызов** генерирует новый timestamp, что приводит к созданию нового `session_id`.

### 3. Конфликт двух систем session management

**Проблема архитектуры:** В системе есть два независимых механизма управления сессиями:

1. **GraphManager.user_sessions** (UUID-based) - для LangFuse трассировки
2. **LocalArtifactsManager._generate_session_id()** (timestamp-based) - для файловой системы

Они не синхронизированы между собой.

## Последствия

1. **Фрагментация данных** - материалы одной сессии разбросаны по разным директориям
2. **Неэффективное использование места** - дублирование `generated_material.md`
3. **Сложность навигации** - пользователь не может найти все материалы в одном месте
4. **Проблемы с artifacts service** - API может не найти связанные файлы

## Предлагаемое решение

### 1. Устранить дублирование в GraphManager

**Создать единый метод** для обработки event-ов вместо дублирования логики:

```python
def _handle_workflow_event(self, node_name: str, node_data: dict, thread_id: str):
    """Единый обработчик событий workflow"""
    if node_name == "generating_content":
        # Логика push learning material
        pass
```

### 2. Синхронизировать session management

**Передавать session_id из GraphManager в LocalArtifactsManager:**

```python
async def push_learning_material(
    self,
    thread_id: str,
    session_id: str,  # ← Добавить параметр
    exam_question: str,
    generated_material: str,
):
```

### 3. Добавить проверку существующих сессий

**Перед созданием новой сессии** проверять, есть ли уже активная сессия для данного thread_id + exam_question.

### 4. Рефакторинг архитектуры

- Сделать **GraphManager.session_id единственным источником истины**
- Удалить timestamp-based генерацию в LocalArtifactsManager
- Использовать UUID для всех session_id

## Приоритет исправления

**🔴 Высокий** - проблема влияет на UX и может привести к потере данных при навигации по артефактам.

## Затрагиваемые файлы

- `learnflow/core/graph_manager.py` - устранить дублирование кода
- `learnflow/services/artifacts_manager.py` - рефакторинг session management
- `learnflow/core/state.py` - возможно потребуется обновление ExamState

## Связанные задачи

- [ ] Создание миграции для существующих артефактов
- [ ] Обновление API endpoints в artifacts-service
- [ ] Добавление тестов для session management
- [ ] Документация по новой архитектуре сессий

## Примечания

Эта проблема была обнаружена при анализе структуры файлов в `data/artifacts/`. Рекомендуется решить до выхода следующей версии системы.