# LearnFlow AI - Обзор системы

<general_description>
## Общее описание

**LearnFlow AI** — это универсальная интеллектуальная система создания образовательных материалов, построенная на основе **LangGraph** и использующая современные технологии обработки естественного языка и компьютерного зрения. Система автоматически генерирует всесторонние учебные материалы для любых предметных областей и уровней образования, анализирует пробелы в знаниях учащихся и создает дополнительные вопросы с подробными ответами.

### Поддерживаемые области знаний
- **STEM**: Математика, Физика, Химия, Биология, Информатика
- **Гуманитарные науки**: Литература, История, Философия, Языки
- **Социальные науки**: Психология, Экономика, Политология
- **Профессиональные области**: Право, Медицина, Инженерия, Бизнес

### Ключевые возможности

- 📚 **Генерация обучающих материалов**: Создание исчерпывающих учебных материалов по любым дисциплинам на основе образовательных вопросов и заданий
- 🖼️ **Распознавание рукописных конспектов**: OCR обработка изображений конспектов учащихся с последующей интеграцией в материалы
- 🤔 **Анализ пробелов знаний**: Автоматическое выявление недостающих знаний и генерация дополнительных вопросов
- 💡 **Подробные ответы**: Генерация развернутых ответов с математическими выводами и практическими примерами
- 🔄 **HITL (Human-in-the-Loop)**: Интерактивное взаимодействие с пользователем для уточнения и улучшения результатов
- ✏️ **Интерактивное редактирование**: Edit agent с fuzzy matching для точечных правок синтезированного материала
- 🌐 **Telegram-бот**: Удобный пользовательский интерфейс для взаимодействия с системой
- 🛡️ **Система безопасности**: Универсальная защита от prompt injection атак с graceful degradation
- 📊 **Мониторинг и трассировка**: Интеграция с LangFuse для отслеживания выполнения workflow
- 🚀 **GitHub интеграция**: Автоматическое сохранение результатов в GitHub репозиторий
</general_description>

<system-architecture>
## Архитектура системы

### Основные компоненты

```mermaid
graph TB
    A[Telegram Bot] --> B[FastAPI Service]
    B --> C[LangGraph Workflow]
    C --> D[OpenAI API]
    C --> E[Image Recognition]
    B --> F[PostgreSQL Database]
    B --> G[LangFuse Tracing]
    H[GitHub Integration] --> I[Artifacts Storage]
    
    subgraph "LangGraph Nodes"
    J[Input Processing]
    K[Content Generation]
    L[Recognition]
    M[Material Synthesis]
    N[Question Generation]
    O[Answer Generation]
    end
```

### 1. **FastAPI сервис** (`learnflow/`)
REST API для обработки запросов и управления workflow:

- **Основные эндпойнты:**
  - `POST /process` - обработка образовательных вопросов и заданий
  - `POST /upload-images/{thread_id}` - загрузка изображений конспектов
  - `POST /process-with-images` - обработка с изображениями
  - `GET /state/{thread_id}` - получение состояния потока
  - `DELETE /thread/{thread_id}` - удаление потока

- **Возможности:**
  - Валидация загружаемых изображений (тип, размер)
  - Управление временными файлами
  - Интеграция с LangFuse для трассировки
  - Обработка ошибок и логирование

### 2. **Telegram бот** (`bot/`)
Основной пользовательский интерфейс с поддержкой:

- **Команды:**
  - `/start` - запуск бота
  - `/help` - справка по использованию
  - `/reset` - сброс текущей сессии
  - `/status` - статус текущей обработки

- **Возможности:**
  - Обработка текстовых сообщений и изображений
  - Группировка медиа-файлов от пользователя
  - Отображение результатов в Markdown формате
  - Управление сессиями пользователей

### 3. **Prompt Configuration Service** (`prompt-config-service/`)
Сервис динамической генерации персонализированных промптов:

- **Возможности:**
  - Создание профилей пользователей с индивидуальными предпочтениями
  - Динамические плейсхолдеры для адаптации промптов под контекст
  - REST API для интеграции с основным workflow
  - Поддержка различных стилей обучения и предметных областей

- **Интеграция:**
  - HTTP клиент в основном сервисе с retry механизмом
  - Автоматическое обогащение промптов контекстом из workflow состояния
  - Graceful degradation при недоступности сервиса

### 4. **LangGraph Workflow** (`learnflow/graph.py`, `learnflow/nodes/`)
Многоэтапный граф обработки с узлами:

#### Поток выполнения:
1. **`input_processing`** - анализ пользовательского ввода
2. **`generating_content`** - генерация основного обучающего материала
3. **`recognition_handwritten`** - распознавание рукописных конспектов (с HITL)
4. **`synthesis_material`** - синтез финального материала
5. **`edit_material`** - интерактивное редактирование синтезированного материала (с HITL)
6. **`generating_questions`** - генерация gap questions (с HITL)
7. **`answer_question`** - параллельная генерация ответов
8. **`export_materials`** - экспорт результатов в PDF/Markdown

#### Узлы workflow:
- **BaseWorkflowNode** (`nodes/base.py`) - базовый класс с логированием, трассировкой и интегрированной системой безопасности
- **InputProcessingNode** (`nodes/input_processing.py`) - анализ входных данных с валидацией образовательных вопросов и заданий
- **ContentGenerationNode** (`nodes/content.py`) - генерация обучающего материала
- **RecognitionNode** (`nodes/recognition.py`) - OCR обработка изображений с валидацией распознанного контента
- **SynthesisNode** (`nodes/synthesis.py`) - объединение материалов
- **EditMaterialNode** (`nodes/edit_material.py`) - интерактивное редактирование с fuzzy matching и HITL валидацией
- **QuestionGenerationNode** (`nodes/questions.py`) - создание дополнительных вопросов с HITL валидацией
- **AnswerGenerationNode** (`nodes/answers.py`) - генерация ответов

### 5. **Система безопасности** (`learnflow/security/`)
**SecurityGuard** - универсальная система защиты от prompt injection:

- **Компоненты:**
  - `guard.py` - основной класс SecurityGuard с методом `validate_and_clean()`
  - `exceptions.py` - кастомные исключения для безопасности
  - Интеграция во все BaseWorkflowNode через `validate_input()`

- **Ключевые особенности:**
  - **Non-blocking design** - никогда не останавливает workflow (graceful degradation)
  - **LLM-based detection** - использует gpt-4o-mini с structured output для детекции
  - **Fuzzy cleaning** - умное удаление injection контента через fuzzy string matching
  - **Educational context aware** - адаптивная система, учитывающая особенности различных предметных областей
  - **Configuration-driven** - все промпты и настройки управляются через конфиги

- **Защищенные входы:**
  - Образовательные вопросы и задания (InputProcessingNode)
  - Распознанный текст из конспектов (RecognitionNode)
  - HITL обратная связь (автоматически через FeedbackNode)
  - Запросы на редактирование (EditMaterialNode)

### 6. **Управление состоянием** (`learnflow/state.py`)
Типизированная модель состояния **ExamState** включает:

```python
class ExamState(BaseModel):
    exam_question: str              # Исходный образовательный вопрос или задание
    image_paths: List[str]          # Пути к загруженным изображениям
    recognized_notes: str           # Распознанный текст из конспектов
    generated_material: str         # Сгенерированный материал
    synthesized_material: str       # Финальный синтезированный материал
    gap_questions: List[str]        # Дополнительные вопросы
    gap_q_n_a: List[str]           # Вопросы и ответы (аккумулирующее поле)
    feedback_messages: List[Any]    # HITL сообщения
    # GitHub интеграция и экспорт
    github_folder_path: Optional[str]
    github_learning_material_url: Optional[str]
    export_settings: Optional[dict] # Настройки экспорта в PDF/Markdown
    # ... другие поля
```
</system-architecture>

<system-configuration>
## Конфигурация системы

### 1. **Prompt Configuration Service** (`prompt-config-service/`)
Микросервис для динамической генерации промптов:

```yaml
# Конфигурация профилей пользователей
profiles:
  beginner:
    learning_style: "step-by-step"
    complexity: "simple"
    examples: true
  advanced:
    learning_style: "concise"
    complexity: "detailed"
    examples: false

# Плейсхолдеры для динамической подстановки
placeholders:
  subject_context: "Контекст предметной области"
  user_level: "Уровень пользователя"
  learning_objectives: "Цели обучения"
```

### 2. **Настройки моделей** (`configs/graph.yaml`)
Конфигурация OpenAI моделей для каждого узла:

```yaml
models:
  default:
    model_name: "gpt-4.1-mini"
    temperature: 0.1
    max_tokens: 4000
  
  nodes:
    generating_content:
      model_name: "gpt-4.1-mini"
      temperature: 0.2
      max_tokens: 8000
    security_guard:
      model_name: "gpt-4o-mini"
      temperature: 0.0
      max_tokens: 1000
    # ... конфигурации для других узлов
```

### 3. **Системные промпты** (`configs/prompts.yaml`)
Детальные промпты для каждого этапа обработки:

- `generating_content_system_prompt` - генерация обучающего материала
- `recognition_system_prompt` - распознавание рукописных конспектов
- `synthesize_system_prompt` - синтез материалов
- `gen_question_system_prompt` - создание дополнительных вопросов
- `gen_answer_system_prompt` - генерация ответов
- `security_guard_detection_system_prompt` - детекция prompt injection атак

### 4. **Переменные окружения** (`.env`)
Конфигурация API ключей и сервисов:

```bash
# API Keys
OPENAI_API_KEY=your_openai_api_key
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key

# Telegram Bot
TELEGRAM_TOKEN=your_telegram_bot_token

# GitHub Integration
GITHUB_TOKEN=your_github_token
GITHUB_REPOSITORY=your_username/your_repository

# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/learnflow

# Prompt Configuration Service
PROMPT_SERVICE_URL=http://localhost:8002
PROMPT_SERVICE_TIMEOUT=5
PROMPT_SERVICE_RETRY_COUNT=3

# Security Settings
SECURITY_ENABLED=true
SECURITY_FUZZY_THRESHOLD=0.85
SECURITY_MIN_CONTENT_LENGTH=10
```
</system-configuration>

<deployment>
## Развертывание

### Локальная разработка

1. **Установка зависимостей:**
```bash
uv sync
```

2. **Настройка окружения:**
```bash
cp env.example .env
# Редактировать .env с API ключами
```

3. **Запуск сервисов:**
```bash
# Только FastAPI
uv run --package learnflow python -m learnflow.main

# Только бот
uv run --package bot python -m bot.main

# Оба сервиса (рекомендуется)
./run.sh
```

### Docker Compose (продакшн)

```bash
docker-compose up
```

Включает полный стек:
- **FastAPI сервис** (порт 8000)
- **Telegram бот**
- **Prompt Configuration Service** (порт 8002)
- **Artifacts Service** (порт 8001)
- **LangFuse** с веб-интерфейсом (порт 3000)
- **PostgreSQL** (порт 5433)
- **Redis** (порт 6379)
- **ClickHouse** (порт 8123)
- **MinIO** (порт 9090)
</deployment>

<workflow>
## Рабочий процесс

### 1. Пользовательский сценарий

1. **Отправка вопроса**: Пользователь отправляет образовательный вопрос или задание через Telegram
2. **Добавление конспектов**: Опционально загружает фотографии рукописных конспектов
3. **Генерация материала**: Система создает обучающий материал
4. **Распознавание конспектов**: OCR обработка изображений с HITL уточнениями
5. **Синтез**: Объединение сгенерированного материла и распознанных конспектов
6. **Интерактивное редактирование**: Точечные правки синтезированного материала через edit agent (опционально)
7. **Gap анализ**: Генерация дополнительных вопросов с HITL обратной связью
8. **Финальные ответы**: Создание подробных ответов на все вопросы
9. **Экспорт материалов**: Конвертация в PDF или Markdown с настраиваемыми параметрами
10. **Сохранение**: Автоматическое сохранение в GitHub и локальное хранение (опционально)

### 2. Техническая реализация

- **Thread-based обработка**: Каждый пользователь имеет уникальный thread_id
- **Checkpoint система**: Сохранение состояния в PostgreSQL
- **HITL интеграция**: Пауза workflow для пользовательского ввода
- **Параллельная обработка**: Concurrent генерация ответов на вопросы
- **Обработка изображений**: Временное хранение и валидация файлов
</workflow>

<monitoring-debugging>
## Мониторинг и отладка

### LangFuse интеграция
- Трассировка всех вызовов LLM
- Метрики производительности
- Стоимость токенов
- Детальные логи workflow

### Логирование
- Структурированные логи с trace ID
- Файловое логирование (`learnflow.log`)
- Уровни логирования через переменную `LOG_LEVEL`

### Health checks
- `GET /health` - проверка работоспособности API
- Docker health checks для всех сервисов
</monitoring-debugging>

<technical-details>
## Технические детали

### Основные зависимости
- **LangGraph** 0.4.8 - workflow orchestration
- **FastAPI** 0.115.12 - REST API
- **aiogram** 3.20.0 - Telegram bot framework
- **langchain-openai** 0.3.22 - OpenAI интеграция
- **langfuse** 2.60.0 - observability
- **Pillow** 11.3.0 - обработка изображений

### Требования к системе
- **Python** 3.13+
- **UV** для управления зависимостями
- **PostgreSQL** для checkpoint хранения
- **Redis** для LangFuse
- **OpenAI API** доступ

### Ограничения
- Максимум 10 изображений на запрос
- Максимальный размер изображения: 10 МБ
- Поддерживаемые форматы: JPG, PNG
- Timeout обработки: настраивается через Docker
</technical-details>

<system-extension>
## Расширение системы

### Добавление новых узлов
1. Создать класс, наследующий от `BaseWorkflowNode`
2. Реализовать метод `process()`
3. Добавить узел в `create_workflow()`
4. Обновить конфигурацию в `graph.yaml`

### Кастомизация промптов
- Редактировать `configs/prompts.yaml`
- Поддержка Jinja2 шаблонов
- Горячая перезагрузка конфигурации
- Адаптация под различные предметные области с поддержкой специализированных промптов для разных дисциплин

### Интеграция новых LLM провайдеров
- Расширить `model_factory.py`
- Добавить конфигурацию в `graph.yaml`
- Обновить настройки окружения

Эта архитектура обеспечивает высокую масштабируемость, наблюдаемость и гибкость для различных сценариев использования в образовательной сфере — от точных наук до гуманитарных дисциплин, от начального образования до университетского уровня.

### Технический долг и рефакторинг
В процессе AI-driven разработки, как и в любой другой разработке, накапливается технический долг. Для систематизации и планирования рефакторинга используется директория `docs/backlog/tech-debt/`, где документируются:

- Архитектурные проблемы и их анализ
- Вопросы производительности и безопасности  
- Предложения по улучшению качества кода
- Стратегии декомпозиции сложных компонентов

Эти документы служат основой для технических инициатив и помогают поддерживать долгосрочную поддерживаемость системы.
</system-extension>