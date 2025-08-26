# FEAT-PROMPT-401: Prompt Configuration Service (MVP)

## Статус
In Progress - динамические промпты уже реализованы в configs/prompts.yaml

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
Промпты УЖЕ РЕАЛИЗОВАНЫ с использованием плейсхолдеров в `configs/prompts.yaml`. Система динамической генерации промптов на основе шаблонов Jinja2 уже работает. Анализ показывает следующую структуру:

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

### Схема БД (использование SQLAlchemy ORM)

**ВАЖНО:** Вместо прямого SQL будет использоваться SQLAlchemy ORM для более качественной разработки и поддержки.

```python
# models.py - SQLAlchemy модели
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Placeholder(Base):
    __tablename__ = 'placeholders'
    
    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    name = Column(String(100), nullable=False, unique=True)  # "role_perspective"
    display_name = Column(String(200))  # "Роль эксперта"
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    
    values = relationship("PlaceholderValue", back_populates="placeholder")

class PlaceholderValue(Base):
    __tablename__ = 'placeholder_values'
    
    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    placeholder_id = Column(UUID, ForeignKey('placeholders.id'))
    value = Column(Text, nullable=False)  # "senior technical expert"
    display_name = Column(String(200))  # "Старший технический эксперт"
    created_at = Column(DateTime, server_default=func.now())
    
    placeholder = relationship("Placeholder", back_populates="values")

class UserPlaceholderSetting(Base):
    __tablename__ = 'user_placeholder_settings'
    
    user_id = Column(BigInteger, primary_key=True)
    placeholder_id = Column(UUID, ForeignKey('placeholders.id'), primary_key=True)
    placeholder_value_id = Column(UUID, ForeignKey('placeholder_values.id'))
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    placeholder = relationship("Placeholder")
    placeholder_value = relationship("PlaceholderValue")

class Profile(Base):
    __tablename__ = 'profiles'
    
    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    name = Column(String(100), nullable=False)  # "technical_expert"
    display_name = Column(String(200))  # "Технический эксперт"
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.now())
    
    settings = relationship("ProfilePlaceholderSetting", back_populates="profile")

class ProfilePlaceholderSetting(Base):
    __tablename__ = 'profile_placeholder_settings'
    
    profile_id = Column(UUID, ForeignKey('profiles.id'), primary_key=True)
    placeholder_id = Column(UUID, ForeignKey('placeholders.id'), primary_key=True)
    placeholder_value_id = Column(UUID, ForeignKey('placeholder_values.id'))
    
    profile = relationship("Profile", back_populates="settings")
    placeholder = relationship("Placeholder")
    placeholder_value = relationship("PlaceholderValue")
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

**1. Основной флоу - генерация промпта (с SQLAlchemy ORM):**
```python
from sqlalchemy.orm import Session
from jinja2 import Template

async def generate_prompt(db: Session, user_id: int, node_name: str, context: dict):
    # Получаем все настройки плейсхолдеров пользователя через ORM
    user_settings = db.query(UserPlaceholderSetting).filter(
        UserPlaceholderSetting.user_id == user_id
    ).options(
        joinedload(UserPlaceholderSetting.placeholder),
        joinedload(UserPlaceholderSetting.placeholder_value)
    ).all()
    
    placeholders = {
        setting.placeholder.name: setting.placeholder_value.value 
        for setting in user_settings
    }
    placeholders.update(context)  # context переопределяет пользовательские
    
    # Загружаем шаблон из configs/prompts.yaml (уже реализовано)
    template_string = load_prompt_template(node_name)
    template = Template(template_string)
    return template.render(**placeholders)
```

**2. Применение профиля (с SQLAlchemy ORM):**
```python
async def apply_profile(db: Session, user_id: int, profile_id: str):
    # Получаем профиль со всеми настройками
    profile = db.query(Profile).filter(
        Profile.id == profile_id
    ).options(
        joinedload(Profile.settings)
    ).first()
    
    if not profile:
        raise ValueError(f"Profile {profile_id} not found")
    
    # Применяем настройки профиля к пользователю
    for profile_setting in profile.settings:
        # Upsert через ORM
        user_setting = db.query(UserPlaceholderSetting).filter(
            UserPlaceholderSetting.user_id == user_id,
            UserPlaceholderSetting.placeholder_id == profile_setting.placeholder_id
        ).first()
        
        if user_setting:
            user_setting.placeholder_value_id = profile_setting.placeholder_value_id
        else:
            new_setting = UserPlaceholderSetting(
                user_id=user_id,
                placeholder_id=profile_setting.placeholder_id,
                placeholder_value_id=profile_setting.placeholder_value_id
            )
            db.add(new_setting)
    
    db.commit()
```

**3. Индивидуальная настройка (с SQLAlchemy ORM):**
```python
async def set_user_placeholder(db: Session, user_id: int, placeholder_id: str, value_id: str):
    # Проверяем существование плейсхолдера и значения
    placeholder_value = db.query(PlaceholderValue).filter(
        PlaceholderValue.id == value_id,
        PlaceholderValue.placeholder_id == placeholder_id
    ).first()
    
    if not placeholder_value:
        raise ValueError(f"Invalid placeholder value {value_id} for placeholder {placeholder_id}")
    
    # Upsert настройки пользователя
    user_setting = db.query(UserPlaceholderSetting).filter(
        UserPlaceholderSetting.user_id == user_id,
        UserPlaceholderSetting.placeholder_id == placeholder_id
    ).first()
    
    if user_setting:
        user_setting.placeholder_value_id = value_id
    else:
        new_setting = UserPlaceholderSetting(
            user_id=user_id,
            placeholder_id=placeholder_id,
            placeholder_value_id=value_id
        )
        db.add(new_setting)
    
    db.commit()
```

**4. Интеграция в LangGraph (ТЕКУЩАЯ РЕАЛИЗАЦИЯ):**
```python
# ТЕКУЩАЯ реализация в LearnFlow (уже работает с динамическими промптами)
from learnflow.prompt_service import PromptService

prompt_service = PromptService()

# В узлах графа уже используется динамическая генерация
system_prompt = prompt_service.get_prompt(
    node_name="generating_content",
    placeholders={
        "subject_keywords": user_config.subject_keywords,
        "role_perspective": user_config.role_perspective,
        "subject_name": user_config.subject_name,
        "input_content": state.exam_question,
        # ... другие плейсхолдеры
    }
)

# БУДУЩАЯ интеграция (с сервисом конфигурации)
prompt_response = await prompt_config_service.post(
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