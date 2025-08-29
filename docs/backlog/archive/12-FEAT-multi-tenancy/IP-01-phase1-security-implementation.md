# Implementation Plan: Phase 1 - Multi-Tenancy Security

## Смысл и цель задачи

Устранение критической уязвимости безопасности в artifacts-service, где любой пользователь может получить доступ к образовательным материалам других пользователей через прямые API вызовы. Реализация базовой аутентификации и авторизации для защиты пользовательских данных в MVP версии системы. Создание foundation для будущей интеграции с web-ui через механизм временных кодов авторизации.

## Архитектура решения

### Компоненты для реализации

1. **База данных (PostgreSQL)**
   - Новая таблица `auth_codes` в базе `learnflow`
   - Хранение временных кодов авторизации для web-ui

2. **Artifacts Service** (`artifacts-service/`)
   - Новый модуль `auth.py` - middleware для аутентификации
   - Модификация `main.py` - добавление защиты endpoints
   - Новые endpoints для верификации кодов и генерации JWT

3. **Telegram Bot** (`bot/`)
   - Новый handler для команды `/web_auth`
   - Модуль для работы с базой данных PostgreSQL
   - Передача API ключа в заголовках при вызове artifacts-service

4. **Конфигурация** 
   - Новые переменные окружения для API ключей и JWT
   - Обновление settings в обоих сервисах

## Полный flow работы функционала

### Flow 1: Bot → Artifacts Service (Service-to-Service)
1. Бот получает команду от пользователя
2. Формирует запрос к artifacts-service с заголовками:
   - `X-API-Key: <bot-api-key>`
   - `X-User-Id: <telegram-user-id>`
3. Artifacts-service проверяет API ключ
4. Извлекает user_id из заголовка
5. Проверяет, что запрашиваемый thread_id == user_id
6. Возвращает данные или 403 Forbidden

### Flow 2: Генерация кода для Web-UI
1. Пользователь отправляет боту команду `/web_auth`
2. Бот генерирует 6-символьный код (буквенно-цифровой)
3. Сохраняет в PostgreSQL: username, код, user_id, timestamp
4. Отправляет пользователю код с инструкцией
5. Код действителен 5 минут

### Flow 3: Web-UI авторизация (подготовка для Phase 2)
1. Web-UI отправляет POST `/auth/verify` с username и кодом
2. Artifacts-service проверяет код в БД
3. Если валиден - генерирует JWT токен
4. Удаляет использованный код
5. Возвращает JWT для последующих запросов

## API и интерфейсы

### Database Schema
```
auth_codes:
- username: VARCHAR(255)
- code: VARCHAR(10) 
- user_id: BIGINT
- created_at: TIMESTAMP
- PRIMARY KEY (username, code)
- INDEX on created_at
```

### Artifacts Service - новые endpoints
- `POST /auth/verify` - проверка кода и получение JWT
  - Параметры: username, code
  - Возвращает: JWT token или ошибку

### Artifacts Service - модифицированные endpoints
- Все существующие endpoints получают dependency injection для auth
  - Извлечение user_id из токена/заголовка
  - Проверка владельца ресурса

### Bot - новые команды
- `/web_auth` - генерация кода авторизации
  - Генерирует код
  - Сохраняет в БД
  - Отправляет пользователю

## Взаимодействие компонентов

```
Telegram User -> Bot -> [X-API-Key, X-User-Id] -> Artifacts Service
                  |
                  v
             PostgreSQL (auth_codes)
                  ^
                  |
        Web-UI -> Artifacts Service -> JWT Token
```

## Порядок реализации

### Step 1: Подготовка базы данных
1. Создать migration для таблицы auth_codes
2. Добавить asyncpg в зависимости бота
3. Создать модуль database.py в боте для работы с PostgreSQL

### Step 2: Реализация аутентификации в Artifacts Service
1. Создать auth.py с middleware функциями
2. Добавить проверку API ключа для bot requests
3. Добавить извлечение user_id из заголовков/JWT
4. Создать endpoint /auth/verify (заготовка для Phase 2)

### Step 3: Защита существующих endpoints
1. Добавить dependency injection во все endpoints
2. Реализовать проверку thread_id == user_id
3. Исправить /users/{user_id}/sessions/recent для фильтрации

### Step 4: Telegram Bot интеграция
1. Реализовать команду /web_auth
2. Добавить генерацию и сохранение кодов
3. Модифицировать API client для передачи заголовков

### Step 5: Конфигурация и тестирование
1. Добавить переменные окружения
2. Обновить env.example
3. Протестировать все flows

## Критичные граничные случаи

### Безопасность
- Истекшие коды должны автоматически удаляться (cron job или при проверке)
- Один код может быть использован только один раз
- API ключ бота должен быть длинным и случайным

### Обратная совместимость
- Artifacts service должен поддерживать оба типа auth (API key и JWT)
- Если auth отсутствует - возвращать 401 Unauthorized
- Если user_id не совпадает с thread_id - возвращать 403 Forbidden

### Производительность
- Индекс на created_at для быстрой очистки старых кодов
- Кеширование проверки API ключа (опционально для MVP)