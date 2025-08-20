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

### Разделение данных

**Хранится в сервисе (по user_id):**
- Плейсхолдеры конфигурации: subject_domain, complexity_level, target_audience, exposition_style

**Передается из LearnFlow в context:**
- Контентные данные: exam_question, study_material, lecture_notes, recognized_notes

## План реализации

### Этап 1: Микросервис и БД (2 дня)
- [ ] Создать структуру микросервиса Prompt Configuration Service
- [ ] Реализовать схему БД (2 таблицы: user_prompt_configs, prompt_profiles)
- [ ] Настроить Docker контейнер для сервиса
- [ ] Интегрировать с docker-compose проекта

### Этап 2: Статическая библиотека значений (2 дня)
- [ ] Создать предустановленные значения для 6 предметов:
  - Криптография (существующая)
  - Математика
  - Физика  
  - Биология
  - Химия
  - История
- [ ] Определить 4 уровня сложности (elementary, high_school, undergraduate, graduate)
- [ ] Задать 3 сценария использования (exam_prep, tutoring, self_study)

### Этап 3: REST API (2 дня)
- [ ] GET /placeholder-options/{type} - получение доступных значений
- [ ] GET /profiles/{user_id} - список профилей пользователя
- [ ] POST /profiles/{user_id} - создание профиля
- [ ] PUT /profiles/{user_id}/active/{profile_id} - активация профиля
- [ ] POST /generate-prompt - генерация промпта для узла

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

### Схема БД (упрощенная для MVP)
```sql
CREATE TABLE user_prompt_configs (
    user_id BIGINT PRIMARY KEY,
    active_profile_id UUID,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE prompt_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id BIGINT REFERENCES user_prompt_configs(user_id),
    name VARCHAR(255),
    subject_domain VARCHAR(50),
    complexity_level VARCHAR(50),
    use_case VARCHAR(50),
    created_at TIMESTAMP DEFAULT NOW()
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

#### Создание профиля
```json
POST /profiles/123456
{
  "name": "Школьная биология",
  "subject_domain": "biology",
  "complexity_level": "high_school",
  "use_case": "exam_prep"
}
```

### Интеграция в LangGraph
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
- [ ] Минимум 6 предметов доступно для выбора
- [ ] Документация по использованию написана

## Что НЕ включаем в MVP

- ❌ LLM-генерация новых placeholder значений
- ❌ Анализ описаний пользователей в свободной форме
- ❌ Семантический поиск существующих конфигураций
- ❌ Версионирование профилей
- ❌ Таблица placeholder_values в БД (хардкод в коде)

## Метрики успеха
- Время переключения между дисциплинами < 1 сек
- Поддержка минимум 6 дисциплин
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