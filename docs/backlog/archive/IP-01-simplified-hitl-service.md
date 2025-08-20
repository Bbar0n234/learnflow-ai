# Implementation Plan: Simplified HITL Service Architecture

## Архитектура решения

### Компоненты системы

1. **HITLManager Service** (`learnflow/services/hitl_manager.py`)
   - Независимый сервис для управления конфигурацией HITL
   - Хранение настроек per-user (по thread_id) в памяти
   - Простой интерфейс для проверки состояния
   - Персистентное хранение конфигураций между выполнениями графов

2. **HITLConfig Model** (`learnflow/models/hitl_config.py`)
   - Простая Pydantic модель с булевыми флагами
   - Флаги точно соответствуют именам узлов
   - Без сложных настроек и таймаутов

3. **Node Adaptations**
   - Минимальные изменения в существующих узлах
   - Обращение к HITLManager перед вызовом interrupt()

4. **API Extensions** (`learnflow/api/main.py`)
   - REST endpoints для управления конфигурацией
   - Get/Set операции для thread-specific настроек
   - Bulk update для всех флагов

5. **Telegram Bot Integration** (`bot/handlers/hitl_settings.py`)
   - Команды для управления HITL настройками
   - Интуитивный интерфейс с кнопками и меню
   - Интеграция с FastAPI через HTTP-клиент

## API и интерфейсы

### 1. HITLConfig Model

```python
class HITLConfig(BaseModel):
    """Простая конфигурация HITL с флагами для каждого узла"""
    
    # Флаги для узлов (точное соответствие именам в graph.py)
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
        """Инициализация с хранилищем конфигураций"""
        self._configs: Dict[str, HITLConfig] = {}  # thread_id -> config
        self._default_config: HITLConfig = HITLConfig()
    
    def is_enabled(self, node_name: str, thread_id: str) -> bool:
        """
        Проверяет, включен ли HITL для узла и потока.
        
        Args:
            node_name: Имя узла
            thread_id: Идентификатор пользователя (из Telegram)
            
        Returns:
            True если HITL включен, False иначе
        """
        
    def get_config(self, thread_id: str) -> HITLConfig:
        """Получает конфигурацию для пользователя"""
        
    def set_config(self, thread_id: str, config: HITLConfig) -> None:
        """Устанавливает конфигурацию для пользователя"""
        
    def update_node_setting(self, thread_id: str, node_name: str, enabled: bool) -> HITLConfig:
        """Обновляет настройку для конкретного узла"""
        
    def reset_config(self, thread_id: str) -> None:
        """Сбрасывает конфигурацию к значениям по умолчанию"""
        
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

### 6. Telegram Bot Integration

#### Команды и интерфейс

```python
# bot/handlers/hitl_settings.py

@router.message(Command("hitl"))
async def show_hitl_menu(message: Message, state: FSMContext):
    """
    Главное меню настроек HITL
    
    /hitl - показать текущие настройки и меню управления
    """

@router.callback_query(F.data == "hitl_toggle_all")
async def toggle_all_hitl(callback: CallbackQuery):
    """Быстрое включение/выключение всех HITL"""

@router.callback_query(F.data.startswith("hitl_toggle_"))
async def toggle_node_hitl(callback: CallbackQuery):
    """Переключение HITL для конкретного узла"""

@router.callback_query(F.data == "hitl_preset_autonomous")
async def set_autonomous_preset(callback: CallbackQuery):
    """Preset: Автономный режим (все HITL выключены)"""

@router.callback_query(F.data == "hitl_preset_guided")
async def set_guided_preset(callback: CallbackQuery):
    """Preset: Управляемый режим (все HITL включены)"""
```

#### API Client для бота

```python
# bot/services/api_client.py

class LearnFlowAPIClient:
    """HTTP-клиент для взаимодействия с FastAPI сервисом"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.session = aiohttp.ClientSession()
    
    async def get_hitl_config(self, user_id: int) -> HITLConfig:
        """Получить текущую конфигурацию HITL пользователя"""
        
    async def update_hitl_config(self, user_id: int, config: HITLConfig) -> HITLConfig:
        """Обновить полную конфигурацию HITL"""
        
    async def toggle_node_hitl(self, user_id: int, node_name: str) -> HITLConfig:
        """Переключить HITL для конкретного узла"""
        
    async def bulk_update_hitl(self, user_id: int, enable_all: bool) -> HITLConfig:
        """Включить/выключить HITL для всех узлов"""
```

#### Keyboard и UI Components

```python
# bot/keyboards/hitl_keyboards.py

def build_hitl_settings_keyboard(config: HITLConfig) -> InlineKeyboardMarkup:
    """
    Строит клавиатуру настроек HITL с текущим состоянием
    
    Layout:
    [🎯 Редактирование материала: ✅] [🎯 Генерация вопросов: ✅]
    [🚀 Автономный режим] [🎛️ Управляемый режим]
    [🔄 Переключить все] [↩️ Назад]
    """

def build_confirmation_keyboard(action: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения для критических действий"""

def build_preset_selection_keyboard() -> InlineKeyboardMarkup:
    """Меню выбора предустановленных режимов"""
```

#### User Experience Flow

1. **Вход в настройки:**
   ```
   /hitl → Показ текущих настроек + меню управления
   ```

2. **Быстрые действия:**
   ```
   "🚀 Автономный режим" → Подтверждение → Все HITL OFF
   "🎛️ Управляемый режим" → Подтверждение → Все HITL ON
   "🔄 Переключить все" → Инверсия текущего состояния
   ```

3. **Точечная настройка:**
   ```
   Кнопка узла → Переключение → Обновление интерфейса
   ```

4. **Обратная связь:**
   ```
   Каждое действие → Toast уведомление о результате
   Ошибки API → Понятное сообщение пользователю
   ```

#### Интеграция с основным потоком

```python
# bot/handlers/main_flow.py

async def process_exam_request(message: Message):
    """
    Основной обработчик запросов на обработку экзамена
    
    Изменения:
    - Показывает текущие настройки HITL перед обработкой
    - Предлагает быстрые настройки при первом использовании
    """
    
    user_id = message.from_user.id
    
    # Получаем текущую конфигурацию HITL
    config = await api_client.get_hitl_config(user_id)
    
    # Показываем пользователю режим обработки
    await message.answer(
        f"📋 **Режим обработки:**\n"
        f"• Редактирование: {'✅ Включено' if config.edit_material else '❌ Отключено'}\n"
        f"• Генерация вопросов: {'✅ Включена' if config.generating_questions else '❌ Отключена'}\n\n"
        f"Изменить настройки: /hitl",
        reply_markup=build_quick_settings_keyboard()
    )
```

## Взаимодействие компонентов

### Поток инициализации

1. **При первом обращении пользователя:**
   - HITLManager создает конфигурацию по умолчанию для thread_id
   - Конфигурация сохраняется в памяти и не удаляется

2. **При выполнении узла:**
   - Узел получает thread_id из контекста (Telegram user ID)
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

3. **Пользователь меняет настройки через бота:**
   ```
   Telegram User → /hitl command → Bot Handler → HTTP Request → FastAPI → HITLManager
   ```

### Поток интеграции Telegram Bot ↔ FastAPI

1. **Получение настроек:**
   ```
   Bot Handler → GET /api/hitl/{user_id} → HITLManager.get_config() → HITLConfig
   ```

2. **Обновление настроек:**
   ```
   User Action → Bot Callback → PATCH /api/hitl/{user_id}/node/{node_name} → Updated Config
   ```

3. **Отображение в интерфейсе:**
   ```
   Updated Config → build_hitl_settings_keyboard() → Telegram InlineKeyboard → User
   ```


### Интеграция с существующими узлами

1. **EditMaterialNode:**
   - Проверяет `hitl_manager.is_enabled("edit_material", thread_id)`
   - При HITL off: один проход с улучшенным промптом
   - Сохраняет версию для потенциального rollback

2. **QuestionGenerationNode:**
   - Проверяет `hitl_manager.is_enabled("generating_questions", thread_id)`
   - При HITL off: генерирует с дополнительными критериями качества
   - Использует structured output для валидации

## Edge Cases и особенности

### 1. Thread ID Management
- **Проблема:** Отсутствие thread_id в некоторых сценариях
- **Решение:** Fallback на "default" thread_id
- **Валидация:** Проверка наличия user_id в ExamState

### 2. Память и масштабирование
- **Особенность:** Конфигурации хранятся постоянно для каждого пользователя
- **Решение:** 
  - Простое хранение в памяти без очистки
  - Опциональная интеграция с Redis для персистентности
  - При необходимости - ограничение количества пользователей

### 3. Миграция существующего кода
- **Проблема:** Узлы ожидают HITL всегда включенным
- **Решение:**
  - По умолчанию все флаги = True
  - Постепенное внедрение через feature flag
  - Логирование для отслеживания использования

### 4. Персистентность настроек
- **Особенность:** Настройки должны сохраняться между сессиями
- **Решение:**
  - В памяти - настройки сохраняются до перезапуска сервиса
  - Для prod - интеграция с Redis или БД
  - API для экспорта/импорта конфигураций

### 5. Обратная совместимость
- **Проблема:** Существующий код не знает о HITLManager
- **Решение:**
  - HITLManager по умолчанию возвращает True
  - Feature flag для активации новой функциональности
  - Постепенная миграция узлов

### 6. Отладка и мониторинг
- **Проблема:** Сложность отслеживания решений HITL
- **Решение:**
  - Детальное логирование всех проверок
  - Метрики использования HITL/non-HITL режимов
  - Debug endpoint для просмотра всех конфигураций