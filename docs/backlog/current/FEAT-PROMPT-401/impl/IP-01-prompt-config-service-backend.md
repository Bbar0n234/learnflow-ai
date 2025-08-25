# Implementation Plan: Prompt Configuration Service (Backend Core)

## Обзор
Создание stateless микросервиса для управления конфигурациями промптов с плейсхолдер-центричной архитектурой. Сервис предоставляет REST API для персонализации промптов пользователями и интегрируется с существующей инфраструктурой LearnFlow.

## Управление зависимостями через UV

### Важно: Использование UV в монорепозитории

Проект LearnFlow использует UV для управления зависимостями в рамках монорепозитория. Новый сервис `prompt-config-service` будет интегрирован в существующую UV workspace структуру.

#### Ключевые принципы:
1. **Добавить сервис как workspace member** в корневой pyproject.toml
2. **Использовать UV команды** для инициализации и управления зависимостями
3. **Dependency groups** для разделения dev, test и production зависимостей
4. **Интеграция с Makefile** для единообразных команд

## Архитектура решения

### 1. Структура проекта
```
prompt-config-service/              # Новая директория на уровне с learnflow/ и bot/
├── alembic/                        # Миграции БД
│   ├── versions/
│   ├── alembic.ini
│   └── env.py
├── src/
│   ├── __init__.py
│   ├── main.py                    # FastAPI приложение
│   ├── config.py                  # Настройки из переменных окружения
│   ├── database.py                # Подключение к БД и сессии
│   ├── models/                    # SQLAlchemy модели
│   │   ├── __init__.py
│   │   ├── placeholder.py
│   │   ├── profile.py
│   │   └── user_settings.py
│   ├── schemas/                   # Pydantic схемы для API
│   │   ├── __init__.py
│   │   ├── placeholder.py
│   │   ├── profile.py
│   │   └── prompt.py
│   ├── api/                       # API endpoints
│   │   ├── __init__.py
│   │   ├── profiles.py
│   │   ├── placeholders.py
│   │   ├── users.py
│   │   └── prompts.py
│   ├── services/                  # Бизнес-логика
│   │   ├── __init__.py
│   │   ├── placeholder_service.py
│   │   ├── profile_service.py
│   │   ├── user_service.py
│   │   └── prompt_service.py
│   ├── repositories/              # Паттерн Repository для работы с БД
│   │   ├── __init__.py
│   │   ├── placeholder_repo.py
│   │   ├── profile_repo.py
│   │   └── user_settings_repo.py
│   ├── utils/                     # Вспомогательные функции
│   │   ├── __init__.py
│   │   ├── template_loader.py    # Загрузка шаблонов из configs/prompts.yaml
│   │   └── jinja_renderer.py     # Рендеринг Jinja2 шаблонов
│   └── seed/                      # Начальные данные
│       ├── __init__.py
│       ├── seed_data.py          # Скрипт заполнения БД
│       └── initial_data.json     # JSON с начальными данными
├── pyproject.toml
└── Dockerfile
```

### 2. Компоненты системы

#### 2.1 Модели данных (SQLAlchemy ORM)

**models/placeholder.py:**
```python
class Placeholder:
    - id: UUID (primary key)
    - name: str (unique, e.g., "role_perspective", "generating_content_material_type")
    - display_name: str ("Роль эксперта")
    - description: text
    - created_at: datetime
    - updated_at: datetime

class PlaceholderValue:
    - id: UUID (primary key)
    - placeholder_id: UUID (FK)
    - value: text (actual value)
    - display_name: str ("Старший технический эксперт")
    - description: text (optional)
    - created_at: datetime
```

**models/profile.py:**
```python
class Profile:
    - id: UUID (primary key)
    - name: str (unique, e.g., "technical_expert")
    - display_name: str ("Технический эксперт")
    - description: text
    - category: str ("style", "subject")
    - created_at: datetime
    - updated_at: datetime

class ProfilePlaceholderSetting:
    - profile_id: UUID (FK, composite PK)
    - placeholder_id: UUID (FK, composite PK)
    - placeholder_value_id: UUID (FK)
    - created_at: datetime
```

**models/user_settings.py:**
```python
class UserPlaceholderSetting:
    - user_id: BigInt (PK, Telegram user ID)
    - placeholder_id: UUID (FK, composite PK)
    - placeholder_value_id: UUID (FK)
    - updated_at: datetime

class UserProfile:
    - user_id: BigInt (PK)
    - created_at: datetime
    - updated_at: datetime
```

#### 2.2 API Endpoints

**1. GET /api/v1/profiles**
- Возвращает список всех доступных профилей
- Response: List[ProfileSchema]

**2. GET /api/v1/users/{user_id}/placeholders**
- Возвращает текущие настройки плейсхолдеров пользователя
- Если пользователь новый - создает дефолтные настройки
- Response: Dict[str, PlaceholderValueSchema]

**3. PUT /api/v1/users/{user_id}/placeholders/{placeholder_id}**
- Изменяет значение конкретного плейсхолдера
- Body: {"value_id": "uuid"}
- Response: PlaceholderSettingSchema

**4. POST /api/v1/users/{user_id}/apply-profile/{profile_id}**
- Применяет профиль к пользователю (копирует все настройки)
- Response: UserSettingsSchema

**5. GET /api/v1/placeholders/{placeholder_id}/values**
- Возвращает все доступные значения для плейсхолдера
- Response: List[PlaceholderValueSchema]

**6. POST /api/v1/generate-prompt**
- Генерирует промпт с динамическим определением плейсхолдеров
- Body: {"user_id": int, "node_name": str, "context": dict}
- Response: {"prompt": str, "used_placeholders": dict}
- Логика: извлекает плейсхолдеры из шаблона, использует context в приоритете, затем БД
- Логирует WARNING для отсутствующих плейсхолдеров

### 3. Сервисный слой

#### 3.1 PlaceholderService
```python
class PlaceholderService:
    async def get_all_placeholders() -> List[Placeholder]
    async def get_placeholder_values(placeholder_id: UUID) -> List[PlaceholderValue]
    async def create_placeholder(data: PlaceholderCreateSchema) -> Placeholder
    async def update_placeholder_value(value_id: UUID, data: dict) -> PlaceholderValue
```

#### 3.2 ProfileService
```python
class ProfileService:
    async def get_all_profiles(category: Optional[str] = None) -> List[Profile]  # category для профилей остается
    async def get_profile_settings(profile_id: UUID) -> Dict[str, str]
    async def create_profile(data: ProfileCreateSchema) -> Profile
    async def update_profile_settings(profile_id: UUID, settings: dict) -> None
```

#### 3.3 UserService
```python
class UserService:
    async def get_user_settings(user_id: int) -> Dict[str, PlaceholderValue]
    async def get_user_placeholder_values(user_id: int, placeholder_names: List[str]) -> Dict[str, str]:
        """Получает значения только для запрошенных плейсхолдеров пользователя"""
    async def set_user_placeholder(user_id: int, placeholder_id: UUID, value_id: UUID) -> None
    async def apply_profile_to_user(user_id: int, profile_id: UUID) -> None
    async def reset_to_defaults(user_id: int) -> None
    async def ensure_user_exists(user_id: int) -> None
```

#### 3.4 PromptService
```python
class PromptService:
    async def generate_prompt(user_id: int, node_name: str, context: dict) -> str:
        """
        Генерирует промпт с динамическим определением плейсхолдеров:
        1. Загружает шаблон из YAML по node_name
        2. Извлекает все плейсхолдеры из шаблона через Jinja2 meta
        3. Проверяет какие плейсхолдеры есть в context (они имеют приоритет)
        4. Запрашивает из БД только отсутствующие в context плейсхолдеры
        5. Логирует warning для плейсхолдеров не найденных ни в context, ни в БД
        6. Рендерит финальный промпт
        """
    
    def extract_placeholders(template_str: str) -> List[str]:
        """Извлекает все плейсхолдеры из Jinja2 шаблона"""
    
    async def load_template(node_name: str) -> str:
        """Загружает шаблон из configs/prompts.yaml"""
    
    async def render_template(template: str, values: dict) -> str:
        """Рендерит Jinja2 шаблон с подстановкой значений"""
```

**Примерная реализация generate_prompt:**
```python
async def generate_prompt(self, user_id: int, node_name: str, context: dict) -> dict:
    # 1. Загружаем шаблон
    template_str = await self.load_template(node_name)
    
    # 2. Извлекаем все плейсхолдеры из шаблона
    all_placeholders = self.extract_placeholders(template_str)
    logger.debug(f"Found placeholders in template: {all_placeholders}")
    
    # 3. Определяем какие плейсхолдеры уже есть в context
    context_placeholders = set(all_placeholders) & set(context.keys())
    missing_placeholders = set(all_placeholders) - set(context.keys())
    
    logger.debug(f"Placeholders from context: {context_placeholders}")
    logger.debug(f"Need to fetch from DB: {missing_placeholders}")
    
    # 4. Запрашиваем из БД только отсутствующие в context
    db_values = {}
    if missing_placeholders:
        db_values = await self.user_service.get_user_placeholder_values(
            user_id, list(missing_placeholders)
        )
    
    # 5. Проверяем что все плейсхолдеры найдены
    final_values = {**db_values, **context}  # context имеет приоритет
    not_found = set(all_placeholders) - set(final_values.keys())
    
    if not_found:
        logger.warning(
            f"Missing placeholders for user {user_id}, node {node_name}: {not_found}. "
            f"These will be rendered as empty strings."
        )
    
    # 6. Рендерим шаблон
    prompt = await self.render_template(template_str, final_values)
    
    return {
        "prompt": prompt,
        "used_placeholders": final_values
    }

def extract_placeholders(self, template_str: str) -> List[str]:
    from jinja2 import Environment, meta
    env = Environment()
    parsed = env.parse(template_str)
    return list(meta.find_undeclared_variables(parsed))
```

#### 3.5 Константы дефолтных значений
```python
# В services/user_service.py или config.py
DEFAULT_PLACEHOLDER_VALUES = {
    "role_perspective": "uuid-senior-technical-expert",
    "subject_name": "uuid-cryptography", 
    "language": "uuid-russian",
    "style": "uuid-detailed",
    "target_audience_inline": "uuid-students",
    # Добавить остальные общие плейсхолдеры
}

async def apply_default_settings(user_id: int):
    """Применяет дефолтные настройки (для новых пользователей и сброса)"""
    for placeholder_name, value_id in DEFAULT_PLACEHOLDER_VALUES.items():
        placeholder = await get_placeholder_by_name(placeholder_name)
        await upsert_user_setting(user_id, placeholder.id, value_id)
```

### 4. Репозитории (Repository Pattern)

#### 4.1 PlaceholderRepository
```python
class PlaceholderRepository:
    async def find_by_id(id: UUID) -> Optional[Placeholder]
    async def find_by_name(name: str) -> Optional[Placeholder]
    async def find_all(filters: dict) -> List[Placeholder]
    async def create(data: dict) -> Placeholder
    async def update(id: UUID, data: dict) -> Placeholder
    async def get_values(placeholder_id: UUID) -> List[PlaceholderValue]
```

#### 4.2 ProfileRepository
```python
class ProfileRepository:
    async def find_by_id(id: UUID) -> Optional[Profile]
    async def find_all(filters: dict) -> List[Profile]
    async def get_settings(profile_id: UUID) -> List[ProfilePlaceholderSetting]
    async def update_settings(profile_id: UUID, settings: List[dict]) -> None
```

#### 4.3 UserSettingsRepository
```python
class UserSettingsRepository:
    async def get_user_settings(user_id: int) -> List[UserPlaceholderSetting]
    async def get_user_settings_by_names(user_id: int, placeholder_names: List[str]) -> Dict[str, str]:
        """
        Получает значения плейсхолдеров по их именам для конкретного пользователя.
        Выполняет JOIN с таблицами placeholders и placeholder_values.
        Возвращает словарь {placeholder_name: value}
        """
    async def upsert_setting(user_id: int, placeholder_id: UUID, value_id: UUID) -> None
    async def delete_user_settings(user_id: int) -> None
    async def bulk_upsert(user_id: int, settings: List[dict]) -> None
```

### 5. Конфигурация и настройки

**config.py:**
```python
class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://..."
    database_pool_size: int = 10
    database_max_overflow: int = 20
    
    # Service
    service_name: str = "prompt-config-service"
    service_version: str = "1.0.0"
    service_port: int = 8001
    
    # Paths
    prompts_config_path: str = "/app/configs/prompts.yaml"
    initial_data_path: str = "/app/src/seed/initial_data.json"
    
    # Cache
    cache_ttl: int = 300  # 5 минут
    
    # Logging
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
```

### 6. База данных и миграции

#### 6.1 Инициализация Alembic
```bash
alembic init alembic
alembic revision --autogenerate -m "Initial migration"
alembic upgrade head
```

#### 6.2 database.py
```python
engine = create_async_engine(settings.database_url)
async_session = sessionmaker(engine, class_=AsyncSession)

async def get_db():
    async with async_session() as session:
        yield session

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

### 7. Seed данные

**initial_data.json структура:**
```json
{
  "placeholders": [
    {
      "name": "role_perspective",
      "display_name": "Роль эксперта",
      "values": [
        {
          "value": "senior technical expert",
          "display_name": "Старший технический эксперт"
        },
        {
          "value": "educational mentor",
          "display_name": "Образовательный наставник"
        }
      ]
    }
  ],
  "profiles": [
    {
      "name": "technical_expert",
      "display_name": "Технический эксперт",
      "category": "style",
      "settings": {
        "role_perspective": "senior technical expert",
        "explanation_depth": "detailed technical analysis"
      }
    }
  ],
  "default_values": {
    "role_perspective": "senior technical expert",
    "subject_name": "cryptography",
    "language": "russian",
    "style": "detailed"
  }
}
```

#### 7.1 Скрипт seed_data.py
```python
async def seed_database():
    # 1. Загрузка данных из JSON
    # 2. Создание плейсхолдеров и их значений
    # 3. Создание профилей и настройка связей профиль-плейсхолдер
    # 4. Создание константы DEFAULT_PLACEHOLDER_VALUES на основе default_values из JSON
    # 5. Валидация что все дефолтные значения существуют в БД
    
async def create_default_values_constant():
    """Генерирует константу DEFAULT_PLACEHOLDER_VALUES из JSON и UUID значений"""
    # Читаем default_values из JSON
    # Находим соответствующие UUID значений в БД
    # Генерируем код константы для вставки в user_service.py
```

### 8. Docker и UV интеграция

**Dockerfile:**
```dockerfile
# Базовый образ с UV
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

WORKDIR /app

# Копируем файлы проекта
COPY pyproject.toml uv.lock ./
COPY prompt-config-service/ ./prompt-config-service/
COPY configs/ ./configs/

# Устанавливаем зависимости через UV для конкретного пакета
RUN uv sync --package prompt-config-service --no-dev

# Запуск сервиса
CMD ["uv", "run", "--package", "prompt-config-service", "python", "-m", "prompt_config_service.main"]
```

**Добавление в docker-compose.yaml:**
```yaml
prompt-config:
  build:
    context: ./prompt-config-service
    dockerfile: Dockerfile
  environment:
    - DATABASE_URL=postgresql://user:pass@postgres:5432/prompts
    - PROMPTS_CONFIG_PATH=/app/configs/prompts.yaml
  ports:
    - "8001:8001"
  volumes:
    - ./configs:/app/configs:ro
  depends_on:
    - postgres
  restart: always
```

### 9. Переменные окружения

**.env.example:**
```env
# Database
DATABASE_URL=postgresql://prompts_user:prompts_pass@localhost:5432/prompts_db

# Service
SERVICE_PORT=8001
LOG_LEVEL=INFO

# Paths
PROMPTS_CONFIG_PATH=../configs/prompts.yaml
INITIAL_DATA_PATH=./src/seed/initial_data.json

# Cache
CACHE_TTL=300
```

## Последовательность реализации

### Этап 0: Инициализация через UV (День 1 - утро)
1. **Добавить сервис в UV workspace:**
   ```bash
   # В корневом pyproject.toml добавить в [tool.uv.workspace]
   members = [
       "bot",
       "learnflow",
       "artifacts-service",
       "prompt-config-service",  # Новый сервис
   ]
   ```

2. **Инициализировать пакет через UV:**
   ```bash
   uv init --package prompt-config-service
   # Это создаст базовую структуру с правильным pyproject.toml
   ```

3. **Добавить основные зависимости:**
   ```bash
   # Production зависимости
   uv add --package prompt-config-service fastapi uvicorn sqlalchemy alembic asyncpg httpx pydantic-settings jinja2
   
   # Dev зависимости в группу dev
   uv add --package prompt-config-service --group dev ruff mypy types-pyyaml sqlalchemy[mypy]
   ```

4. **Синхронизировать зависимости:**
   ```bash
   uv sync --package prompt-config-service --all-groups
   ```

5. **Добавить команды в Makefile:**
   ```makefile
   # В корневой Makefile добавить:
   
   sync-prompt-config:
   	uv sync --package prompt-config-service --all-groups
   
   run-prompt-config:
   	uv run --package prompt-config-service python -m prompt_config_service.main
   
   ruff-check-prompt-config:
   	uv run --package prompt-config-service --group dev ruff check prompt-config-service/
   
   ruff-fix-prompt-config:
   	uv run --package prompt-config-service --group dev ruff check prompt-config-service/ --fix
   
   ruff-format-prompt-config:
   	uv run --package prompt-config-service --group dev ruff format prompt-config-service/
   
   mypy-prompt-config:
   	uv run --package prompt-config-service --group dev mypy prompt-config-service/
   
   fix-prompt-config:
   	uv run --package prompt-config-service --group dev ruff check prompt-config-service/ --fix
   	uv run --package prompt-config-service --group dev ruff format prompt-config-service/
   	uv run --package prompt-config-service --group dev mypy prompt-config-service/
   ```

### Этап 1: Базовая структура (День 1)
1. Создать структуру каталогов prompt-config-service/ через UV init
2. Настроить зависимости через UV команды (НЕ редактировать pyproject.toml вручную)
3. Создать базовые файлы конфигурации (config.py, database.py)
4. Инициализировать Alembic для миграций через UV:
   ```bash
   uv run --package prompt-config-service alembic init alembic
   ```

### Этап 2: Модели и БД (День 1-2)
1. Реализовать SQLAlchemy модели (5 таблиц)
2. Создать первую миграцию Alembic:
   ```bash
   uv run --package prompt-config-service alembic revision --autogenerate -m "Initial migration"
   uv run --package prompt-config-service alembic upgrade head
   ```
3. Реализовать репозитории для каждой модели

### Этап 3: Сервисный слой (День 2)
1. Реализовать PlaceholderService
2. Реализовать ProfileService
3. Реализовать UserService
4. Реализовать PromptService с Jinja2 рендерингом

### Этап 4: API Endpoints (День 3)
1. Создать FastAPI приложение в main.py
2. Реализовать все 6 endpoints
3. Создать Pydantic схемы для request/response
4. Добавить валидацию и обработку ошибок

### Этап 5: Seed данные и инициализация (День 3-4)
1. Проанализировать configs/prompts.yaml и извлечь все плейсхолдеры
2. Создать initial_data.json с ~25 плейсхолдерами
3. Определить 8 профилей (3 стилевых + 5 предметных)
4. Реализовать скрипт seed_data.py
5. Добавить команду инициализации БД:
   ```bash
   # Создать команду в Makefile
   seed-prompt-config:
   	uv run --package prompt-config-service python -m prompt_config_service.seed.seed_data
   ```

### Этап 6: Docker и интеграция (День 4)
1. Создать Dockerfile для сервиса с UV
2. Добавить сервис в docker-compose.yaml
3. Настроить сетевое взаимодействие между сервисами
4. Протестировать работу в Docker окружении:
   ```bash
   # Обновить dev-services в Makefile
   dev-services:
   	docker compose down -v && docker compose up --build bot graph artifacts-service prompt-config web-ui postgres
   ```

### Этап 7: Документация (День 5)
1. Написать README с инструкциями по запуску через UV:
   ```markdown
   # Разработка
   make sync-prompt-config     # Установить зависимости
   make run-prompt-config      # Запустить сервис
   make fix-prompt-config      # Исправить линтинг и форматирование
   ```

## Edge Cases и особенности

### 1. Обработка новых пользователей
- При первом обращении вызывается `apply_default_settings(user_id)`
- Дефолтные значения берутся из константы `DEFAULT_PLACEHOLDER_VALUES`
- Автоматическое создание полного набора настроек для немедленного использования

### 2. Сброс настроек пользователя
- Команда `/reset_prompts` использует тот же метод `apply_default_settings(user_id)`
- Гарантируется консистентность между новыми пользователями и сбросом
- Перезаписывает все существующие настройки дефолтными

### 3. Отказоустойчивость (MVP подход без кэширования)
- **НЕТ fallback на статичные промпты** - качество важнее доступности
- **НЕТ кэширования в MVP версии** - избегаем проблем с устаревшими данными
- Простой retry механизм с таймаутами в клиенте LearnFlow
- При недоступности сервиса - явная ошибка пользователю

### 4. Валидация
- Проверка существования плейсхолдера и значения при установке
- Валидация обязательных плейсхолдеров при генерации промпта
- Проверка соответствия плейсхолдеров для конкретного node_name

### 5. Производительность (для будущих версий)
- В MVP версии кэширование НЕ реализуется
- Планируется в Production версии: кэширование шаблонов и настроек
- Batch операции для применения профилей остаются для оптимизации БД запросов

### 6. Безопасность
- Валидация user_id (должен быть положительным числом)
- Экранирование значений при рендеринге Jinja2
- Rate limiting на API endpoints

### 7. Миграция существующих данных
- Автоматическое извлечение плейсхолдеров из configs/prompts.yaml при инициализации
- Константа DEFAULT_PLACEHOLDER_VALUES генерируется из seed данных
- **НЕТ fallback на старую систему** - при недоступности сервиса workflow останавливается с ошибкой

## Команды разработки через UV

### Часто используемые команды:
```bash
# Установка/обновление зависимостей
uv sync --package prompt-config-service --all-groups

# Добавление новой зависимости
uv add --package prompt-config-service <package-name>
uv add --package prompt-config-service --group dev <dev-package>
uv add --package prompt-config-service --group test <test-package>

# Запуск сервиса
uv run --package prompt-config-service python -m prompt_config_service.main

# Работа с Alembic
uv run --package prompt-config-service alembic revision --autogenerate -m "Description"
uv run --package prompt-config-service alembic upgrade head
uv run --package prompt-config-service alembic downgrade -1

# Линтинг и форматирование
uv run --package prompt-config-service --group dev ruff check .
uv run --package prompt-config-service --group dev ruff format .
uv run --package prompt-config-service --group dev mypy .
```

### Структура pyproject.toml сервиса:
```toml
# prompt-config-service/pyproject.toml (создается автоматически через uv init)
[project]
name = "prompt-config-service"
version = "0.1.0"
description = "Stateless service for prompt configuration management"
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    # Будут добавлены через uv add
]

[project.optional-dependencies]
dev = [
    # Будут добавлены через uv add --group dev
]
test = [
    # Будут добавлены через uv add --group test
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

## Метрики успеха реализации

1. **Функциональность:**
   - Все 6 API endpoints работают корректно
   - Успешная генерация промптов для всех узлов LearnFlow
   - Корректное применение профилей и индивидуальных настроек

2. **Производительность:**
   - Время генерации промпта < 100ms
   - Поддержка 100+ одновременных пользователей
   - Размер БД оптимизирован (индексы на часто используемые поля)

3. **Надежность:**
   - Retry механизм для временных сбоев
   - Явные ошибки при недоступности (без silent failures)
   - Логирование всех операций для отладки

4. **Интеграция:**
   - Seamless интеграция с docker-compose инфраструктурой
   - Совместимость с существующими промптами
   - Возможность постепенной миграции