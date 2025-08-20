# Implementation Plan: Simplified HITL Service Architecture

## Архитектура решения

### Компоненты системы

1. **HITLManager Service** (`learnflow/services/hitl_manager.py`)
   - Независимый сервис для управления конфигурацией HITL
   - Хранение настроек per-thread/per-user в памяти
   - Простой интерфейс для проверки состояния
   - Thread-safe для параллельного доступа

2. **HITLConfig Model** (`learnflow/models/hitl_config.py`)
   - Простая Pydantic модель с булевыми флагами
   - Флаги точно соответствуют именам узлов
   - Без сложных настроек и таймаутов

3. **Node Adaptations**
   - Минимальные изменения в существующих узлах
   - Обращение к HITLManager перед вызовом interrupt()
   - Enhanced generation при отключенном HITL

4. **API Extensions** (`learnflow/api/main.py`)
   - REST endpoints для управления конфигурацией
   - Get/Set операции для thread-specific настроек
   - Bulk update для всех флагов

## API и интерфейсы

### 1. HITLConfig Model

```python
class HITLConfig(BaseModel):
    """Простая конфигурация HITL с флагами для каждого узла"""
    
    # Флаги для узлов (точное соответствие именам в graph.py)
    recognition_handwritten: bool = Field(
        default=True,
        description="Enable HITL for handwritten recognition node"
    )
    
    edit_material: bool = Field(
        default=True,
        description="Enable HITL for material editing node"
    )
    
    generating_questions: bool = Field(
        default=True,
        description="Enable HITL for question generation node"
    )
    
    # Helper методы
    def is_enabled_for_node(self, node_name: str) -> bool:
        """Проверяет, включен ли HITL для конкретного узла"""
        
    @classmethod
    def all_enabled(cls) -> "HITLConfig":
        """Возвращает конфигурацию со всеми включенными флагами"""
        
    @classmethod
    def all_disabled(cls) -> "HITLConfig":
        """Возвращает конфигурацию со всеми выключенными флагами"""
```

### 2. HITLManager Service

```python
class HITLManager:
    """Сервис управления HITL конфигурацией"""
    
    def __init__(self):
        """Инициализация с thread-safe хранилищем"""
        self._configs: Dict[str, HITLConfig] = {}  # thread_id -> config
        self._lock: threading.Lock = threading.Lock()
        self._default_config: HITLConfig = HITLConfig()
    
    def is_enabled(self, node_name: str, thread_id: str) -> bool:
        """
        Проверяет, включен ли HITL для узла и потока.
        
        Args:
            node_name: Имя узла (например, 'recognition_handwritten')
            thread_id: Идентификатор потока/сессии
            
        Returns:
            True если HITL включен, False иначе
        """
        
    def get_config(self, thread_id: str) -> HITLConfig:
        """Получает конфигурацию для потока"""
        
    def set_config(self, thread_id: str, config: HITLConfig) -> None:
        """Устанавливает конфигурацию для потока"""
        
    def update_node_setting(self, thread_id: str, node_name: str, enabled: bool) -> HITLConfig:
        """Обновляет настройку для конкретного узла"""
        
    def reset_config(self, thread_id: str) -> None:
        """Сбрасывает конфигурацию к значениям по умолчанию"""
        
    def cleanup_old_configs(self, max_age_hours: int = 24) -> int:
        """Очищает устаревшие конфигурации"""
```

### 3. Singleton Instance

```python
# В learnflow/services/hitl_manager.py
_hitl_manager_instance = None

def get_hitl_manager() -> HITLManager:
    """Возвращает singleton instance HITLManager"""
    global _hitl_manager_instance
    if _hitl_manager_instance is None:
        _hitl_manager_instance = HITLManager()
    return _hitl_manager_instance
```

### 4. Модификация узлов

```python
# Пример для RecognitionNode
class RecognitionNode(FeedbackNode):
    
    async def process(self, state: ExamState) -> ExamState:
        """Обработка с опциональным HITL"""
        
        # Получаем thread_id из состояния или контекста
        thread_id = state.session_id or "default"
        
        # Проверяем конфигурацию HITL
        hitl_manager = get_hitl_manager()
        hitl_enabled = hitl_manager.is_enabled("recognition_handwritten", thread_id)
        
        if hitl_enabled:
            # Существующая логика с interrupt()
            recognized_text = await self.request_user_feedback(state, message)
        else:
            # Enhanced generation без HITL
            recognized_text = await self.auto_recognize(state)
            
        return state
    
    async def auto_recognize(self, state: ExamState) -> str:
        """Автоматическое распознавание без HITL"""
        # Enhanced prompt с инструкциями для повышения качества
        # Дополнительные проверки и валидация
```

### 5. API Endpoints

```python
# GET /api/hitl/{thread_id}
async def get_hitl_config(thread_id: str) -> HITLConfig:
    """Получить текущую конфигурацию HITL для потока"""
    
# PUT /api/hitl/{thread_id}
async def set_hitl_config(thread_id: str, config: HITLConfig) -> HITLConfig:
    """Установить полную конфигурацию HITL для потока"""
    
# PATCH /api/hitl/{thread_id}/node/{node_name}
async def update_node_hitl(thread_id: str, node_name: str, enabled: bool) -> HITLConfig:
    """Обновить настройку HITL для конкретного узла"""
    
# POST /api/hitl/{thread_id}/reset
async def reset_hitl_config(thread_id: str) -> HITLConfig:
    """Сбросить конфигурацию к значениям по умолчанию"""
    
# POST /api/hitl/{thread_id}/bulk
async def bulk_update_hitl(thread_id: str, enable_all: bool) -> HITLConfig:
    """Включить или выключить HITL для всех узлов"""
```

## Взаимодействие компонентов

### Поток инициализации

1. **При старте сессии:**
   - API создает thread_id для новой сессии
   - HITLManager инициализирует конфигурацию по умолчанию
   - Конфигурация сохраняется в памяти сервиса

2. **При выполнении узла:**
   - Узел получает thread_id из ExamState.session_id
   - Узел запрашивает HITLManager.is_enabled(node_name, thread_id)
   - На основе ответа выбирается режим работы

### Поток управления конфигурацией

1. **Пользователь меняет настройки:**
   ```
   Client → API Endpoint → HITLManager → Update in-memory config
   ```

2. **Узел проверяет настройки:**
   ```
   Node → get_hitl_manager() → is_enabled(node_name, thread_id) → bool
   ```

3. **Очистка устаревших конфигураций:**
   ```
   Background task → HITLManager.cleanup_old_configs() → Remove old entries
   ```

### Интеграция с существующими узлами

1. **RecognitionNode:**
   - Проверяет `hitl_manager.is_enabled("recognition_handwritten", thread_id)`
   - При HITL off: использует enhanced OCR prompt
   - Логирует режим работы для аудита

2. **EditMaterialNode:**
   - Проверяет `hitl_manager.is_enabled("edit_material", thread_id)`
   - При HITL off: один проход с улучшенным промптом
   - Сохраняет версию для потенциального rollback

3. **QuestionGenerationNode:**
   - Проверяет `hitl_manager.is_enabled("generating_questions", thread_id)`
   - При HITL off: генерирует с дополнительными критериями качества
   - Использует structured output для валидации

## Edge Cases и особенности

### 1. Thread ID Management
- **Проблема:** Отсутствие thread_id в некоторых сценариях
- **Решение:** Fallback на "default" thread_id
- **Валидация:** Проверка наличия session_id в ExamState

### 2. Конкурентный доступ
- **Проблема:** Множественные потоки обращаются к HITLManager
- **Решение:** Thread-safe операции с threading.Lock
- **Оптимизация:** Read-write lock для улучшения производительности

### 3. Память и масштабирование
- **Проблема:** Накопление конфигураций в памяти
- **Решение:** 
  - Периодическая очистка старых конфигураций
  - Опциональная интеграция с Redis для персистентности
  - LRU cache с ограничением размера

### 4. Миграция существующего кода
- **Проблема:** Узлы ожидают HITL всегда включенным
- **Решение:**
  - По умолчанию все флаги = True
  - Постепенное внедрение через feature flag
  - Логирование для отслеживания использования

### 5. Качество при отключенном HITL
- **Проблема:** Потенциальное снижение качества
- **Решение:**
  - Enhanced prompts с self-verification
  - Дополнительная валидация результатов
  - Confidence scoring в логах

### 6. Отсутствие персистентности
- **Проблема:** Потеря конфигураций при перезапуске
- **Решение:**
  - Опциональная интеграция с Redis
  - Экспорт/импорт конфигураций через API
  - Graceful shutdown с сохранением состояния

### 7. Обратная совместимость
- **Проблема:** Существующий код не знает о HITLManager
- **Решение:**
  - HITLManager по умолчанию возвращает True
  - Feature flag для активации новой функциональности
  - Постепенная миграция узлов

### 8. Отладка и мониторинг
- **Проблема:** Сложность отслеживания решений HITL
- **Решение:**
  - Детальное логирование всех проверок
  - Метрики использования HITL/non-HITL режимов
  - Debug endpoint для просмотра всех конфигураций