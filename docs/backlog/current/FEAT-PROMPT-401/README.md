# FEAT-PROMPT-401: Prompt Configuration Service (MVP)

## Статус
Planned

## Milestone
OSS Launch

## Цель
Создать микросервис для управления конфигурациями промптов, позволяющий пользователям персонализировать генерацию учебных материалов под различные дисциплины и уровни сложности.

## Обоснование
- Текущая система жестко завязана на криптографию
- Невозможность адаптации под другие предметы
- Отсутствие персонализации для разных целевых аудиторий
- Снижение порога входа для новых пользователей

## Архитектура решения

### Компоненты системы

1. **PostgreSQL** - Хранилище профилей пользователей
2. **Prompt Configuration Service** - Stateless микросервис для генерации промптов
3. **Telegram Bot** - Интерфейс для выбора конфигураций
4. **LearnFlow** - Потребитель сгенерированных промптов

### Архитектура данных

**Плейсхолдер-центричная система:**
Основа системы - прямое управление плейсхолдерами. Профили - вторичный удобный функционал.

**Компоненты системы:**
- **Плейсхолдеры** - определения переменных в промпт-шаблонах (role_perspective, subject_name, target_audience_inline)
- **Значения плейсхолдеров** - все возможные варианты для каждого плейсхолдера
- **Пользовательские настройки** - индивидуальные значения каждого плейсхолдера для конкретного пользователя
- **Профили** - шаблоны для быстрого применения наборов значений

**Логика работы:**
1. Пользователь может настраивать каждый плейсхолдер индивидуально
2. Либо применить профиль для быстрой настройки, а затем донастроить по необходимости
3. Генерация промпта основана только на текущих значениях плейсхолдеров пользователя

**Существующие плейсхолдеры в системе:**
Промпты уже декомпозированы на плейсхолдеры в `configs/prompts.yaml`. Анализ показывает следующую структуру:

**Общие плейсхолдеры (используются в нескольких промптах):**
- `subject_keywords` - ключевые слова предметной области для тегирования
- `subject_name` - название предмета/дисциплины
- `role_perspective` - роль эксперта (senior expert, educational mentor)
- `target_audience_inline` - краткое описание аудитории для inline использования
- `target_audience_block` - развернутое описание целевой аудитории
- `language` - язык генерации контента
- `style` - стиль изложения материала
- `input_content` - основной контент для обработки
- `include_mathematics` - флаг для включения математических блоков

**Специфичные для generating_content:**
- `role_additional_context` - дополнительный контекст роли
- `material_type_inline` - краткий тип материала
- `material_type_block` - развернутое описание типа материала
- `topic_coverage` - охват темы
- `explanation_depth` - глубина объяснения

**Специфичные для gen_question:**
- `question_purpose_inline` - краткое описание цели вопросов
- `question_purpose` - развернутая цель генерации вопросов
- `question_quantity` - количество вопросов
- `question_formats` - форматы вопросов

**Контентные данные (передаются из LearnFlow в runtime):**
- `exam_question` - вопрос экзамена
- `study_material` - учебный материал
- `lecture_notes` - конспекты лекций
- `recognized_notes` - распознанные заметки

## Разбиение на задачи

### Обоснование разбиения
Монолитная реализация (6 этапов, 11 дней) заменяется на 3 независимые задачи для лучшей управляемости и тестируемости.

### Задача 1: "Prompt Configuration Service" (Backend Core)
**Цель:** Создание микросервиса конфигурации промптов с полным API
**Время:** 4-5 дней
**Статус:** Должна быть выполнена первой (блокирует остальные)

**Включает:**
- Создание плейсхолдер-центричной схемы БД (5 таблиц)
- Предзаполнение ~25 плейсхолдеров из prompts.yaml и их значений
- Создание 8 профилей-шаблонов (3 стилевых + 5 предметных)
- Настройка маппинга плейсхолдеров для каждого профиля
- Реализация REST API (6 endpoints)
- Docker контейнер и интеграция с docker-compose
- Базовое тестирование API

**Результат:** Полностью рабочий сервис конфигурации
**Тестируемость:** Можно тестировать через Postman/curl независимо от других компонентов

### Задача 2: "LearnFlow Integration" (Core System Changes)
**Цель:** Интеграция LearnFlow с сервисом конфигурации
**Время:** 2-3 дня
**Зависимость:** Требует завершения Задачи 1

**Включает:**
- Модификация всех узлов LangGraph для запроса промптов из сервиса
- Передача user_id = thread_id в сервис конфигурации
- Замена статичных промптов из YAML на динамические
- Обработка ошибок сервиса и fallback на дефолтные промпты
- Тестирование генерации материалов с персонализированными промптами

**Результат:** LearnFlow генерирует материалы с учетом пользовательских настроек
**Тестируемость:** Можно проверить работу через существующие тесты LearnFlow

### Задача 3: "Telegram Bot UI" (User Interface)
**Цель:** Пользовательский интерфейс для управления конфигурациями
**Время:** 2-3 дня
**Зависимость:** Требует завершения Задачи 1 (может выполняться параллельно с Задачей 2)

**Включает:**
- Команда `/configure` для настройки промптов
- Интерактивные меню для выбора и применения профилей
- UI для индивидуальной настройки плейсхолдеров
- Отображение текущих настроек пользователя
- Команда `/reset_prompts` для сброса к дефолтам

**Результат:** Пользователи могут настраивать персонализацию через Telegram
**Тестируемость:** Можно тестировать через Telegram независимо от LearnFlow

### Преимущества разбиения
- **Независимость:** Каждая задача дает законченный результат
- **Тестируемость:** Можно тестировать каждый компонент отдельно
- **Приоритизация:** Задача 1 критически важна, 2 и 3 можно делать параллельно
- **Управляемость:** Меньше риск "большого банга", проще отслеживать прогресс

## План реализации (детальный)

### Этап 1: Микросервис и БД (2 дня)
- [ ] Создать структуру микросервиса Prompt Configuration Service
- [ ] Реализовать схему БД (2 таблицы: user_prompt_configs, prompt_profiles)
- [ ] Настроить Docker контейнер для сервиса
- [ ] Интегрировать с docker-compose проекта

### Этап 2: Система плейсхолдеров и профилей (2 дня)
- [ ] Создать плейсхолдер-центричную схему БД (5 таблиц)
- [ ] Предзаполнить ~25 существующих плейсхолдеров из prompts.yaml с их значениями
- [ ] Создать 8 профилей-шаблонов:
  - **3 стилевых:** Technical Expert, Learning Path, Quick Reference  
  - **5 предметных:** Информационная безопасность, Машинное обучение, Архитектура ПО, Базы данных, Веб-разработка
- [ ] Настроить маппинг плейсхолдеров для каждого профиля

### Этап 3: REST API (2 дня)
- [ ] GET /profiles - получение доступных профилей-шаблонов
- [ ] GET /users/{user_id}/placeholders - текущие настройки плейсхолдеров пользователя
- [ ] PUT /users/{user_id}/placeholders/{placeholder_id} - изменение конкретного плейсхолдера
- [ ] POST /users/{user_id}/apply-profile/{profile_id} - применение профиля-шаблона
- [ ] GET /placeholders/{placeholder_id}/values - доступные значения для плейсхолдера
- [ ] POST /generate-prompt - генерация промпта на основе настроек пользователя

### Этап 4: Интеграция с Telegram Bot (1 день)
- [ ] Добавить команду /configure для настройки профиля
- [ ] Реализовать интерактивный выбор параметров через inline кнопки
- [ ] Сохранение и переключение профилей
- [ ] Отображение текущей конфигурации

### Этап 5: Интеграция с LearnFlow (2 дня)
- [ ] Модифицировать узлы графа для запроса промптов
- [ ] Передавать user_id = thread_id в сервис
- [ ] Заменить статичные промпты из YAML на динамические
- [ ] Протестировать для всех узлов (generating_content, recognition, synthesize и т.д.)

### Этап 6: Шаблоны промптов (2 дня)
- [ ] Создать базовые шаблоны с плейсхолдерами для каждого узла
- [ ] Реализовать подстановку значений через Jinja2
- [ ] Валидация сгенерированных промптов
- [ ] Кэширование часто используемых конфигураций

## Технические детали

### Схема БД (плейсхолдер-центричная)
```sql
-- 1. Плейсхолдеры (определения переменных)
CREATE TABLE placeholders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL UNIQUE,     -- "role_perspective"
    display_name VARCHAR(200),             -- "Роль эксперта"  
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 2. Значения для плейсхолдеров (все возможные варианты)
CREATE TABLE placeholder_values (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    placeholder_id UUID REFERENCES placeholders(id),
    value TEXT NOT NULL,                   -- "senior technical expert"
    display_name VARCHAR(200),             -- "Старший технический эксперт"
    created_at TIMESTAMP DEFAULT NOW()
);

-- 3. Настройки пользователей (ОСНОВНАЯ таблица)
CREATE TABLE user_placeholder_settings (
    user_id BIGINT NOT NULL,
    placeholder_id UUID REFERENCES placeholders(id),
    placeholder_value_id UUID REFERENCES placeholder_values(id),
    updated_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, placeholder_id)
);

-- 4. Профили (шаблоны для быстрого применения)
CREATE TABLE profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,            -- "technical_expert"
    display_name VARCHAR(200),             -- "Технический эксперт"
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 5. Настройки профилей (какие значения входят в профиль)
CREATE TABLE profile_placeholder_settings (
    profile_id UUID REFERENCES profiles(id),
    placeholder_id UUID REFERENCES placeholders(id),
    placeholder_value_id UUID REFERENCES placeholder_values(id),
    PRIMARY KEY (profile_id, placeholder_id)
);
```

### API Примеры

#### Генерация промпта
```json
POST /generate-prompt
{
  "user_id": 123456,
  "node_name": "generating_content",
  "context": {
    "exam_question": "Объясните процесс фотосинтеза"
  }
}

Response:
{
  "prompt": "KEYWORD: biology, education...\n<role>You are a biology educator...</role>..."
}
```

#### Применение профиля и индивидуальная настройка
```json
// Применить профиль (копирует все его настройки пользователю)
POST /users/123456/apply-profile/technical-expert-uuid

// Получить текущие настройки пользователя
GET /users/123456/placeholders
{
  "role_perspective": {
    "value": "senior technical expert",
    "display_name": "Старший технический эксперт"
  },
  "subject_name": {
    "value": "machine learning",
    "display_name": "Машинное обучение"
  }
}

// Изменить конкретный плейсхолдер
PUT /users/123456/placeholders/role_perspective
{
  "value_id": "uuid-ml-researcher-value"
}

// Получить доступные профили
GET /profiles
[
  {"id": "uuid", "name": "technical_expert", "display_name": "Технический эксперт"},
  {"id": "uuid", "name": "information_security", "display_name": "Информационная безопасность"}
]
```

### Логика работы системы

**1. Основной флоу - генерация промпта:**
```python
async def generate_prompt(user_id: int, node_name: str, context: dict):
    # Получаем все настройки плейсхолдеров пользователя
    user_placeholders = await db.query("""
        SELECT p.name, pv.value 
        FROM user_placeholder_settings ups
        JOIN placeholders p ON ups.placeholder_id = p.id
        JOIN placeholder_values pv ON ups.placeholder_value_id = pv.id
        WHERE ups.user_id = $1
    """, user_id)
    
    placeholders = {row['name']: row['value'] for row in user_placeholders}
    placeholders.update(context)  # context переопределяет пользовательские
    
    template = get_node_template(node_name)
    return template.render(**placeholders)
```

**2. Применение профиля (вспомогательный функционал):**
```python
async def apply_profile(user_id: int, profile_id: str):
    # Получаем все настройки профиля
    profile_settings = await db.query("""
        SELECT placeholder_id, placeholder_value_id
        FROM profile_placeholder_settings
        WHERE profile_id = $1
    """, profile_id)
    
    # Применяем к пользователю (batch upsert)
    for setting in profile_settings:
        await db.query("""
            INSERT INTO user_placeholder_settings (user_id, placeholder_id, placeholder_value_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, placeholder_id) 
            DO UPDATE SET placeholder_value_id = $3, updated_at = NOW()
        """, user_id, setting['placeholder_id'], setting['placeholder_value_id'])
```

**3. Индивидуальная настройка:**
```python
async def set_user_placeholder(user_id: int, placeholder_id: str, value_id: str):
    await db.query("""
        INSERT INTO user_placeholder_settings (user_id, placeholder_id, placeholder_value_id)
        VALUES ($1, $2, $3)
        ON CONFLICT (user_id, placeholder_id) 
        DO UPDATE SET placeholder_value_id = $3, updated_at = NOW()
    """, user_id, placeholder_id, value_id)
```

**4. Интеграция в LangGraph:**
```python
# Было (статичный промпт)
system_prompt = load_from_yaml("generating_content_system_prompt")

# Стало (персонализированный)
prompt_response = await prompt_service.post(
    "/generate-prompt",
    json={
        "user_id": state.thread_id,  # thread_id = user_id
        "node_name": "generating_content",
        "context": {"exam_question": state.exam_question}
    }
)
system_prompt = prompt_response["prompt"]
```

## Definition of Done

- [ ] Микросервис развернут и доступен по HTTP
- [ ] БД создана с необходимыми таблицами
- [ ] Все 5 API endpoints работают корректно
- [ ] Интеграция с Telegram ботом протестирована
- [ ] LearnFlow узлы используют динамические промпты
- [ ] Реализация всех 3 задач: Backend сервис + LearnFlow интеграция + Telegram UI
- [ ] Документация по использованию написана

## Метрики успеха
- Время переключения между дисциплинами < 1 сек
- Полная гибкость настройки плейсхолдеров + удобные профили-шаблоны + интуитивный UI
- 100% покрытие узлов графа динамическими промптами
- Успешная генерация материалов для всех комбинаций параметров

## Риски
- Увеличение сложности архитектуры
- Дополнительная точка отказа (новый сервис)
- Необходимость миграции существующих пользователей

## Зависимости
- PostgreSQL должен быть доступен
- Docker и docker-compose настроены
- Telegram bot должен поддерживать inline кнопки