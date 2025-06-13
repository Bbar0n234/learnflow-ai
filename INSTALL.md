# Инструкции по установке LearnFlow AI

## Обзор системы

LearnFlow AI - система подготовки экзаменационных материалов на базе LangGraph с архитектурой:

- **FastAPI сервис** (`learnflow/`) - REST API для обработки запросов
- **Telegram бот** (`bot/`) - основной пользовательский интерфейс  
- **LangGraph workflow** (`core/`) - граф обработки с HITL логикой
- **PostgreSQL** - persistence для состояний workflow
- **LangFuse** - трассировка и мониторинг LLM вызовов

## Требования

- Python 3.13+
- Poetry для управления зависимостями
- PostgreSQL 12+ для checkpointer
- OpenAI API ключ
- LangFuse аккаунт
- Telegram Bot Token

## Установка

### 1. Клонирование и настройка окружения

```bash
# Установка зависимостей через Poetry
poetry install

# Установка групп зависимостей для разных компонентов
poetry install --group learnflow    # FastAPI сервис
poetry install --group bot          # Telegram бот  
poetry install --group core         # PostgreSQL драйвер
poetry install --group dev          # Development tools (опционально)
```

### 2. Настройка переменных окружения

```bash
# Копируем пример конфигурации
cp env.example .env

# Редактируем .env файл с вашими значениями
nano .env
```

**Обязательные переменные:**

```env
# PostgreSQL для checkpointer
LLM_DATABASE_CONN_STRING=postgresql+asyncpg://user:password@localhost:5432/learnflow

# OpenAI API
LLM_OPENAI_API_KEY=your_openai_api_key_here

# Telegram Bot
TELEGRAM_TOKEN=your_telegram_bot_token_here

# LangFuse трассировка
LANGFUSE_PUBLIC_KEY=your_langfuse_public_key
LANGFUSE_SECRET_KEY=your_langfuse_secret_key
```

### 3. Настройка PostgreSQL

```bash
# Создание БД для checkpointer
createdb learnflow

# Альтернативно через psql:
psql -c "CREATE DATABASE learnflow;"
```

### 4. Проверка конфигурации

Убедитесь что существуют конфигурационные файлы:
- `config/prompts.yaml` - шаблоны промптов
- `config/graph.yaml` - настройки модели

## Запуск системы

### Вариант 1: Раздельный запуск компонентов

**Терминал 1 - FastAPI сервис:**
```bash
poetry run python learnflow/main.py
```

**Терминал 2 - Telegram бот:**
```bash
poetry run python bot/main.py
```

### Вариант 2: Docker Compose (если настроен)

```bash
docker-compose up -d
```

## Проверка работы

### 1. Проверка FastAPI сервиса

```bash
curl http://localhost:8000/health
# Ожидаемый ответ: {"status": "healthy", "service": "learnflow-ai"}
```

### 2. Проверка Telegram бота

- Найдите вашего бота в Telegram по имени
- Отправьте команду `/start`
- Должно появиться приветственное сообщение

### 3. Тестовый workflow

1. Отправьте боту экзаменационный вопрос, например:
   ```
   Классификация криптографических алгоритмов. Основные определения.
   ```

2. Система должна:
   - Сгенерировать обучающий материал
   - Предложить дополнительные вопросы
   - Запросить обратную связь (HITL)
   - Сгенерировать ответы после одобрения

## API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| GET  | `/`          | Проверка работы |
| GET  | `/health`    | Health-probe |
| POST | `/process`   | Запуск/продолжение workflow |
| GET  | `/state/{thread_id}` | Текущее состояние |
| DELETE | `/thread/{thread_id}` | Очистка checkpoints |

### Пример использования API

```bash
# Запуск нового workflow
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Классификация криптографических алгоритмов"
  }'

# Продолжение workflow с feedback
curl -X POST http://localhost:8000/process \
  -H "Content-Type: application/json" \
  -d '{
    "thread_id": "your-thread-id",
    "message": "Одобряю предложенные вопросы"
  }'
```

## Архитектурные особенности

### HITL (Human-in-the-Loop)
- Используется `interrupt()` для остановки workflow
- Возобновление через `Command(resume=...)`
- Состояние сохраняется в PostgreSQL между прерываниями

### PostgreSQL Checkpointer
- Каждая операция открывает новую async сессию
- Thread ID разделяет состояния разных пользователей
- Автоматическая инициализация схемы БД

### LangFuse интеграция
- Все LLM вызовы трассируются автоматически
- CallbackHandler передается в каждую модель
- Мониторинг доступен в LangFuse dashboard

## Troubleshooting

### Частые проблемы

**1. Ошибка подключения к PostgreSQL**
```
Проверьте строку подключения в LLM_DATABASE_CONN_STRING
Убедитесь что PostgreSQL запущен и доступен
```

**2. Telegram бот не отвечает**
```
Проверьте TELEGRAM_TOKEN
Убедитесь что FastAPI сервис запущен на правильном порту
```

**3. LangFuse authentication failed**
```
Проверьте LANGFUSE_PUBLIC_KEY и LANGFUSE_SECRET_KEY
Убедитесь что хост указан правильно (по умолчанию cloud.langfuse.com)
```

**4. Ошибки импорта модулей**
```bash
# Убедитесь что все зависимости установлены
poetry install --group core --group learnflow --group bot

# Проверьте что вы в правильной директории
pwd
```

### Логи

Логи доступны в stdout при запуске сервисов:
- FastAPI: подробные логи запросов и workflow
- Telegram бот: логи сообщений и API вызовов
- LangGraph: трассировка выполнения узлов

## Развертывание в Production

Для production развертывания рекомендуется:

1. **Использовать внешний PostgreSQL** (не локальный)
2. **Настроить reverse proxy** (nginx) для FastAPI
3. **Использовать webhook** вместо polling для Telegram бота
4. **Настроить мониторинг** через LangFuse и системные метрики
5. **Включить HTTPS** для всех внешних соединений

### Docker развертывание

```bash
# Сборка образов
docker-compose build

# Запуск в production режиме
docker-compose -f docker-compose.prod.yml up -d
```

## Расширение функциональности

Система спроектирована для расширения:

- **Новые узлы**: добавьте в `core/nodes/`
- **Новые форматы вывода**: расширьте `AnswerGenerationNode`  
- **Интеграция с GitHub**: активируйте в `settings.py`
- **Webhook интеграции**: добавьте в FastAPI сервис

Следуйте паттернам из existing кода и документации в `project_documentation.md`. 