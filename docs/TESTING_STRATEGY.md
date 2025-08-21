# Стратегия тестирования LearnFlow AI

## Обзор проекта

LearnFlow AI - это система генерации образовательного контента на базе LangGraph для подготовки к экзаменам по криптографии. Система обрабатывает экзаменационные вопросы и изображения рукописных заметок для создания комплексных учебных материалов с вопросами и ответами для анализа пробелов в знаниях.

## Текущее состояние

- **Стадия разработки**: MVP (за неделю до open-source релиза)
- **Тестовое покрытие**: 0% (нет тестов)
- **Цель**: Достичь базового тестового покрытия критически важных компонентов для обеспечения надежности MVP

## Архитектурные компоненты для тестирования

### 1. Критически важные компоненты (Приоритет 1 - Обязательно для MVP)

#### 1.1 Управление состоянием workflow (State Management)
**Файл**: `learnflow/core/state.py`

**Что тестировать**:
- Валидация модели `ExamState` через Pydantic
- Корректность накопления данных в полях с `operator.add`
- Сериализация/десериализация состояния
- Переходы состояния между узлами workflow
- Обработка пустых и некорректных данных

**Примеры тестов**:
```python
def test_exam_state_validation():
    """Тест валидации полей ExamState"""
    # Проверка обязательных полей
    # Проверка типов данных
    # Проверка значений по умолчанию

def test_state_accumulation():
    """Тест накопления данных в gap_q_n_a"""
    # Проверка operator.add для списков
    # Проверка сохранения порядка элементов

def test_state_transitions():
    """Тест переходов между состояниями"""
    # Проверка изменения состояния после каждого узла
    # Проверка сохранения данных при переходах
```

#### 1.2 Менеджер графа (Graph Manager)
**Файл**: `learnflow/core/graph_manager.py`

**Что тестировать**:
- Инициализация workflow через `_ensure_setup()`
- Обработка текстовых запросов (`process_step`)
- Обработка запросов с изображениями (`process_step_with_images`)
- Управление жизненным циклом потоков (thread lifecycle)
- Интеграция с PostgreSQL checkpointer
- Восстановление после ошибок

**Примеры тестов**:
```python
def test_graph_manager_initialization():
    """Тест инициализации GraphManager"""
    # Проверка создания экземпляра
    # Проверка подключения к БД
    # Проверка создания workflow

def test_process_step_text_only():
    """Тест обработки текстовых запросов"""
    # Мокирование LLM ответов
    # Проверка корректного выполнения workflow
    # Проверка сохранения состояния

def test_process_with_images():
    """Тест обработки изображений"""
    # Мокирование OCR
    # Проверка загрузки изображений
    # Проверка интеграции с workflow

def test_thread_cleanup():
    """Тест очистки потоков"""
    # Проверка удаления временных файлов
    # Проверка очистки состояния из БД
```

#### 1.3 HITL Manager (Human-in-the-Loop)
**Файлы**: 
- `learnflow/services/hitl_manager.py`
- `learnflow/models/hitl_config.py`

**Что тестировать**:
- Конфигурация HITL для каждого потока
- Включение/отключение узлов
- Массовые операции (bulk updates)
- Изоляция конфигураций между потоками
- Singleton паттерн HITLManager
- Значения по умолчанию

**Примеры тестов**:
```python
def test_hitl_config_validation():
    """Тест валидации HITLConfig"""
    # Проверка создания конфигурации
    # Проверка валидации имен узлов
    # Проверка методов all_enabled/all_disabled

def test_hitl_manager_singleton():
    """Тест singleton паттерна"""
    # Проверка единственности экземпляра
    # Проверка потокобезопасности

def test_thread_specific_config():
    """Тест изоляции конфигураций"""
    # Создание конфигураций для разных потоков
    # Проверка независимости настроек

def test_bulk_operations():
    """Тест массовых операций"""
    # Включение всех узлов
    # Отключение всех узлов
    # Частичные обновления
```

#### 1.4 FastAPI Endpoints
**Файл**: `learnflow/api/main.py`

**Что тестировать**:
- Все REST endpoints
- Валидация входных данных
- Обработка ошибок и коды ответов
- Загрузка файлов и лимиты
- Интеграция с GraphManager
- Health checks

**Примеры тестов**:
```python
def test_process_endpoint():
    """Тест POST /process"""
    # Валидные запросы
    # Невалидные данные
    # Проверка ответов

def test_upload_images():
    """Тест POST /upload-images/{thread_id}"""
    # Загрузка валидных изображений
    # Проверка лимитов размера
    # Проверка типов файлов
    # Множественная загрузка

def test_state_retrieval():
    """Тест GET /state/{thread_id}"""
    # Получение существующего состояния
    # Обработка несуществующих потоков

def test_hitl_endpoints():
    """Тест HITL configuration endpoints"""
    # GET /api/hitl/{thread_id}
    # PATCH /api/hitl/{thread_id}/node/{node_name}
    # POST /api/hitl/{thread_id}/bulk
```

### 2. Важные компоненты (Приоритет 2)

#### 2.1 Security Guard
**Файл**: `learnflow/security/guard.py`

**Что тестировать**:
- Обнаружение инъекций
- Fuzzy matching алгоритмы
- Очистка входных данных
- Graceful degradation
- Производительность

**Примеры тестов**:
```python
def test_injection_detection():
    """Тест обнаружения инъекций"""
    # SQL инъекции
    # Command инъекции
    # XSS попытки

def test_fuzzy_matching():
    """Тест нечеткого сопоставления"""
    # Различные вариации вредоносных паттернов
    # False positives
    # False negatives

def test_graceful_degradation():
    """Тест деградации при ошибках"""
    # Поведение при недоступности сервиса
    # Fallback механизмы
```

#### 2.2 File Utils
**Файл**: `learnflow/services/file_utils.py`

**Что тестировать**:
- Валидация изображений
- Управление временными файлами
- Очистка файлов
- Concurrent operations
- Обработка ошибок файловой системы

**Примеры тестов**:
```python
def test_image_validation():
    """Тест валидации изображений"""
    # Проверка размеров
    # Проверка форматов
    # Проверка MIME типов

def test_temp_file_lifecycle():
    """Тест жизненного цикла временных файлов"""
    # Создание
    # Хранение
    # Автоматическая очистка

def test_concurrent_file_operations():
    """Тест параллельных операций"""
    # Одновременная загрузка файлов
    # Race conditions
    # Блокировки файлов
```

#### 2.3 Базовые классы узлов
**Файл**: `learnflow/nodes/base.py`

**Что тестировать**:
- Абстрактный класс `BaseWorkflowNode`
- Паттерн `FeedbackNode` для HITL
- Интеграция с Security Guard
- Конфигурация моделей

**Примеры тестов**:
```python
def test_base_node_initialization():
    """Тест инициализации базового узла"""
    # Проверка обязательных методов
    # Проверка конфигурации

def test_feedback_node_pattern():
    """Тест HITL паттерна"""
    # Обработка команд
    # Прерывание выполнения
    # Возобновление после feedback
```

### 3. Компоненты полноты функционала (Приоритет 3)

#### 3.1 Workflow Nodes
**Директория**: `learnflow/nodes/`

**Узлы для тестирования**:
- `input_processing.py` - анализ входных данных
- `content.py` - генерация контента
- `recognition.py` - OCR обработка
- `synthesis.py` - синтез материалов
- `questions.py` - генерация вопросов
- `answers.py` - генерация ответов

**Что тестировать**:
- Логика каждого узла
- Трансформация состояния
- Обработка ошибок
- Интеграция с LLM

#### 3.2 Telegram Bot
**Файл**: `bot/main.py`

**Что тестировать**:
- Обработка команд
- Загрузка изображений
- Интеграция с API
- Управление сессиями пользователей

#### 3.3 Configuration Management
**Файлы**:
- `learnflow/config/config_manager.py`
- `learnflow/config/settings.py`

**Что тестировать**:
- Загрузка конфигурации
- Валидация настроек
- Environment variables
- Значения по умолчанию

## Структура тестов

### Предлагаемая структура директорий
```
tests/
├── __init__.py
├── conftest.py                    # Общие фикстуры pytest
├── unit/                          # Unit тесты
│   ├── __init__.py
│   ├── test_state.py             # Тесты ExamState
│   ├── test_hitl_manager.py     # Тесты HITL
│   ├── test_security_guard.py   # Тесты Security
│   ├── test_models.py           # Тесты Pydantic моделей
│   └── test_file_utils.py       # Тесты работы с файлами
├── integration/                   # Интеграционные тесты
│   ├── __init__.py
│   ├── test_graph_manager.py    # Тесты GraphManager
│   ├── test_api_endpoints.py    # Тесты FastAPI
│   ├── test_workflow_nodes.py   # Тесты узлов workflow
│   └── test_bot_integration.py  # Тесты Telegram бота
├── e2e/                          # End-to-end тесты
│   ├── __init__.py
│   └── test_full_workflow.py    # Полный цикл обработки
├── fixtures/                      # Тестовые данные
│   ├── __init__.py
│   ├── images/                  # Тестовые изображения
│   ├── prompts/                 # Тестовые промпты
│   └── responses/               # Мок ответы LLM
└── mocks/                        # Моки внешних сервисов
    ├── __init__.py
    ├── llm_mock.py              # Мок OpenAI
    ├── db_mock.py               # Мок PostgreSQL
    └── telegram_mock.py         # Мок Telegram API
```

## Конфигурация тестирования

### pytest.ini
```ini
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
asyncio_mode = "auto"
markers = [
    "unit: Unit tests",
    "integration: Integration tests",
    "e2e: End-to-end tests",
    "slow: Slow tests",
    "requires_api: Tests requiring external APIs"
]
```

### Базовые фикстуры (conftest.py)
```python
# Примеры необходимых фикстур:

@pytest.fixture
def mock_llm():
    """Мок для OpenAI API"""
    
@pytest.fixture
def mock_db():
    """Мок для PostgreSQL"""
    
@pytest.fixture
def test_client():
    """TestClient для FastAPI"""
    
@pytest.fixture
def sample_exam_state():
    """Пример ExamState для тестов"""
    
@pytest.fixture
def temp_test_dir():
    """Временная директория для тестов файлов"""
    
@pytest.fixture
def mock_telegram_bot():
    """Мок Telegram бота"""
```

## Стратегия внедрения

### Фаза 1: Базовые Unit-тесты (1-2 дня)
1. Настройка pytest и структуры тестов
2. Тесты для `ExamState` и моделей данных
3. Тесты для `HITLManager` и `HITLConfig`
4. Тесты для `SecurityGuard`
5. Базовые фикстуры и моки

**Ожидаемое покрытие**: 30-40% критических компонентов

### Фаза 2: Интеграционные тесты (2-3 дня)
1. Тесты для `GraphManager`
2. Тесты для FastAPI endpoints
3. Тесты для workflow nodes
4. Тесты для file operations

**Ожидаемое покрытие**: 50-60% основного функционала

### Фаза 3: E2E тесты (1 день)
1. Полный workflow от входа до выхода
2. Тестирование HITL взаимодействий
3. Тестирование error recovery

**Ожидаемое покрытие**: 70% критических путей

## Инструменты и библиотеки

### Уже установленные
- `pytest>=8.4.1` - основной фреймворк тестирования
- `pytest-asyncio>=1.1.0` - поддержка async тестов

### Рекомендуемые к добавлению
```toml
[tool.uv.dependency-groups.test]
dependencies = [
    "pytest>=8.4.1",
    "pytest-asyncio>=1.1.0",
    "pytest-cov>=5.0.0",        # Покрытие кода
    "pytest-mock>=3.12.0",       # Улучшенные моки
    "httpx>=0.27.0",            # Тестирование FastAPI
    "faker>=24.0.0",            # Генерация тестовых данных
    "factory-boy>=3.3.0",       # Фабрики для моделей
    "freezegun>=1.4.0",         # Мокирование времени
]
```

## Команды для запуска тестов

```bash
# Запуск всех тестов
uv run pytest

# Запуск с покрытием
uv run pytest --cov=learnflow --cov=bot --cov-report=html

# Запуск только unit тестов
uv run pytest -m unit

# Запуск только integration тестов  
uv run pytest -m integration

# Запуск конкретного файла
uv run pytest tests/unit/test_state.py

# Запуск с verbose output
uv run pytest -v

# Запуск параллельно (требует pytest-xdist)
uv run pytest -n auto

# Запуск с остановкой на первой ошибке
uv run pytest -x

# Запуск только failed тестов из прошлого запуска
uv run pytest --lf
```

## Метрики качества

### Минимальные требования для MVP
- **Code Coverage**: минимум 60% для критических компонентов
- **Test Execution Time**: < 5 минут для всех unit и integration тестов
- **Test Stability**: 0 flaky тестов

### Целевые метрики после MVP
- **Code Coverage**: 80% overall, 90% для критических путей
- **Test Types**: 60% unit, 30% integration, 10% e2e
- **Performance**: p95 < 1s для unit тестов

## Continuous Integration

### GitHub Actions Workflow (для будущего)
```yaml
name: Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install uv
        uses: astral-sh/setup-uv@v3
      - name: Install dependencies
        run: uv sync --group test
      - name: Run tests
        run: uv run pytest --cov
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Лучшие практики

### Написание тестов
1. **Именование**: Используйте описательные имена `test_should_do_something_when_condition`
2. **Arrange-Act-Assert**: Структурируйте тесты по паттерну AAA
3. **Изоляция**: Каждый тест должен быть независимым
4. **Мокирование**: Мокируйте внешние зависимости (LLM, БД, API)
5. **Fixtures**: Переиспользуйте setup через pytest fixtures

### Тестовые данные
1. Используйте фабрики для создания тестовых объектов
2. Храните большие тестовые данные в отдельных файлах
3. Используйте Faker для генерации случайных данных
4. Версионируйте тестовые изображения

### Performance
1. Используйте `pytest.mark.slow` для медленных тестов
2. Запускайте тесты параллельно где возможно
3. Кешируйте дорогие операции в fixtures с scope="session"

## Риски и митигация

### Риски
1. **Сложность мокирования LangGraph**: Требует глубокого понимания workflow
2. **Async тестирование**: Сложность тестирования асинхронного кода
3. **Внешние зависимости**: OpenAI API, PostgreSQL, Telegram
4. **Временные ограничения**: Неделя до релиза

### Митигация
1. Начать с простых синхронных компонентов
2. Использовать готовые моки где возможно
3. Фокус на критических путях, не на 100% покрытии
4. Приоритизация тестов по важности для пользователя

## Заключение

Данная стратегия обеспечивает прагматичный подход к тестированию MVP с фокусом на:
- Критически важные компоненты системы
- Быструю реализацию базового покрытия
- Масштабируемость для будущего развития
- Баланс между качеством и временем разработки

Следуя этому плану, можно достичь надежного тестового покрытия основного функционала за 4-5 дней, что обеспечит уверенность в качестве open-source релиза.