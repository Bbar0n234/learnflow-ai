# LearnFlow AI - Обзор системы

<general-description>
## Общее описание

**LearnFlow AI** — это интеллектуальная система подготовки экзаменационных материалов по криптографии, построенная на основе **LangGraph** и использующая современные технологии обработки естественного языка и компьютерного зрения. Система автоматически генерирует всесторонние учебные материалы, анализирует пробелы в знаниях студентов и создает дополнительные вопросы с подробными ответами.

### Ключевые возможности

- 📚 **Генерация обучающих материалов**: Создание исчерпывающих учебных материалов по криптографии на основе экзаменационных вопросов
- 🖼️ **Распознавание рукописных конспектов**: OCR обработка изображений студенческих конспектов с последующей интеграцией в материалы
- 🤔 **Анализ пробелов знаний**: Автоматическое выявление недостающих знаний и генерация дополнительных вопросов
- 💡 **Подробные ответы**: Генерация развернутых ответов с математическими выводами и практическими примерами
- 🔄 **HITL (Human-in-the-Loop)**: Интерактивное взаимодействие с пользователем для уточнения и улучшения результатов
- 🌐 **Telegram-бот**: Удобный пользовательский интерфейс для взаимодействия с системой
- 📊 **Мониторинг и трассировка**: Интеграция с LangFuse для отслеживания выполнения workflow
- 🚀 **GitHub интеграция**: Автоматическое сохранение результатов в GitHub репозиторий
</general-description>

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
  - `POST /process` - обработка текстовых запросов
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

### 3. **LangGraph Workflow** (`learnflow/graph.py`, `learnflow/nodes/`)
Многоэтапный граф обработки с узлами:

#### Поток выполнения:
1. **`input_processing`** - анализ пользовательского ввода
2. **`generating_content`** - генерация основного обучающего материала
3. **`recognition_handwritten`** - распознавание рукописных конспектов (с HITL)
4. **`synthesis_material`** - синтез финального материала
5. **`generating_questions`** - генерация gap questions (с HITL)
6. **`answer_question`** - параллельная генерация ответов

#### Узлы workflow:
- **BaseWorkflowNode** (`nodes/base.py`) - базовый класс с логированием и трассировкой
- **InputProcessingNode** (`nodes/input_processing.py`) - анализ входных данных
- **ContentGenerationNode** (`nodes/content.py`) - генерация обучающего материала
- **RecognitionNode** (`nodes/recognition.py`) - OCR обработка изображений
- **SynthesisNode** (`nodes/synthesis.py`) - объединение материалов
- **QuestionGenerationNode** (`nodes/questions.py`) - создание дополнительных вопросов
- **AnswerGenerationNode** (`nodes/answers.py`) - генерация ответов

### 4. **Управление состоянием** (`learnflow/state.py`)
Типизированная модель состояния **ExamState** включает:

```python
class ExamState(BaseModel):
    exam_question: str              # Исходный экзаменационный вопрос
    image_paths: List[str]          # Пути к загруженным изображениям
    recognized_notes: str           # Распознанный текст из конспектов
    generated_material: str         # Сгенерированный материал
    synthesized_material: str       # Финальный синтезированный материал
    gap_questions: List[str]        # Дополнительные вопросы
    gap_q_n_a: List[str]           # Вопросы и ответы (аккумулирующее поле)
    feedback_messages: List[Any]    # HITL сообщения
    # GitHub интеграция
    github_folder_path: Optional[str]
    github_learning_material_url: Optional[str]
    # ... другие поля
```
</system-architecture>

<system-configuration>
## Конфигурация системы

### 1. **Настройки моделей** (`configs/graph.yaml`)
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
    # ... конфигурации для других узлов
```

### 2. **Системные промпты** (`configs/prompts.yaml`)
Детальные промпты для каждого этапа обработки:

- `generating_content_system_prompt` - генерация обучающего материала
- `recognition_system_prompt` - распознавание рукописных конспектов
- `synthesize_system_prompt` - синтез материалов
- `gen_question_system_prompt` - создание дополнительных вопросов
- `gen_answer_system_prompt` - генерация ответов

### 3. **Переменные окружения** (`.env`)
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
```
</system-configuration>

<deployment>
## Развертывание

### Локальная разработка

1. **Установка зависимостей:**
```bash
poetry install --group core --group learnflow --group bot
```

2. **Настройка окружения:**
```bash
cp env.example .env
# Редактировать .env с API ключами
```

3. **Запуск сервисов:**
```bash
# Только FastAPI
poetry run python -m learnflow.main

# Только бот
poetry run python -m bot.main

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
- **LangFuse** с веб-интерфейсом (порт 3000)
- **PostgreSQL** (порт 5433)
- **Redis** (порт 6379)
- **ClickHouse** (порт 8123)
- **MinIO** (порт 9090)
</deployment>

<workflow>
## Рабочий процесс

### 1. Пользовательский сценарий

1. **Отправка вопроса**: Пользователь отправляет экзаменационный вопрос через Telegram
2. **Добавление конспектов**: Опционально загружает фотографии рукописных конспектов
3. **Генерация материала**: Система создает обучающий материал
4. **Распознавание конспектов**: OCR обработка изображений с HITL уточнениями
5. **Синтез**: Объединение сгенерированного материла и распознанных конспектов
6. **Gap анализ**: Генерация дополнительных вопросов с HITL обратной связью
7. **Финальные ответы**: Создание подробных ответов на все вопросы
8. **Сохранение**: Автоматическое сохранение в GitHub (опционально)

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
- **Poetry** для управления зависимостями
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

### Интеграция новых LLM провайдеров
- Расширить `model_factory.py`
- Добавить конфигурацию в `graph.yaml`
- Обновить настройки окружения

Эта архитектура обеспечивает высокую масштабируемость, наблюдаемость и гибкость для различных сценариев использования в образовательной сфере.
</system-extension>