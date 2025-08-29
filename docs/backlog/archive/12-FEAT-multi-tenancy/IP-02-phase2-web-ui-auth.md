# Implementation Plan: Phase 2 - Web UI Authentication

## Смысл и цель задачи

Реализация полноценной системы аутентификации в Web UI для защиты пользовательских данных. Интеграция с подготовленной в Phase 1 инфраструктурой безопасности artifacts-service, включая обмен временных кодов на JWT токены. Обеспечение корректной фильтрации данных по пользователям и поддержка deep linking с учетом авторизации.

## Архитектура решения

### Новые компоненты Web UI
- **Auth компоненты** (`web-ui/src/components/auth/`)
  - `LoginPage.tsx` - экран входа с формой авторизации
  - `AuthGuard.tsx` - защита роутов от неавторизованного доступа
  - `UserIndicator.tsx` - отображение текущего пользователя

- **Auth сервисы** (`web-ui/src/services/`)
  - `AuthService.ts` - управление JWT токенами и авторизацией
  - Модификация `ApiClient.ts` - автоматическое добавление токена в запросы

- **Auth хуки** (`web-ui/src/hooks/`)
  - `useAuth.ts` - хук для работы с контекстом авторизации
  - `useAuthGuard.ts` - проверка авторизации и редиректы

- **Auth контекст** (`web-ui/src/contexts/`)
  - `AuthContext.tsx` - глобальный контекст авторизации

### Используемые существующие компоненты
- `artifacts-service/auth.py` - endpoint `/auth/verify` для обмена кодов
- База данных `auth_codes` - хранение временных кодов
- Telegram bot команда `/web_auth` - генерация кодов

## Полный flow работы функционала

### 1. Первичная авторизация
1. Пользователь открывает Web UI
2. AuthGuard проверяет наличие JWT в localStorage
3. Если токена нет - redirect на `/login`
4. LoginPage показывает инструкции:
   - Откройте @LearnFlowBot в Telegram
   - Отправьте команду /web_auth
   - Введите полученный код
5. Пользователь вводит username и 6-символьный код
6. Web UI отправляет POST `/auth/verify` к artifacts-service
7. При успехе получает JWT токен (действителен 24 часа)
8. Токен сохраняется в localStorage
9. Пользователь перенаправляется на изначально запрошенную страницу

### 2. Работа с авторизованным пользователем
1. Все API запросы автоматически включают `Authorization: Bearer <token>`
2. ApiClient фильтрует threads по текущему user_id
3. При 401 ошибке - автоматический logout и redirect на `/login`
4. UserIndicator показывает username в header приложения

### 3. Deep linking с авторизацией
1. При переходе по прямой ссылке (например `/thread/123/session/456`)
2. AuthGuard сохраняет target URL в sessionStorage
3. После успешной авторизации - redirect на сохраненный URL
4. Валидация что thread_id совпадает с user_id из токена

### 4. Обновление токена и logout
1. При истечении токена (через 24 часа) - автоматический logout
2. Кнопка "Выйти" очищает localStorage и redirect на `/login`
3. При закрытии браузера токен сохраняется (persistent login)

## API и интерфейсы

### AuthService
- `login(username, code)` - обмен кода на JWT
  - Вызывает POST `/auth/verify`
  - Сохраняет токен в localStorage
  - Возвращает user info из токена

- `logout()` - выход из системы
  - Очищает localStorage
  - Сбрасывает auth context

- `getToken()` - получение текущего токена
  - Проверяет валидность по expiration
  - Возвращает null если истек

- `getCurrentUser()` - извлечение user info из JWT
  - Парсит payload токена
  - Возвращает {userId, username}

### ApiClient модификации
- Добавление interceptor для Authorization header
- Обработка 401 ошибок с auto-logout
- Фильтрация threads по userId из токена

### AuthContext
- `isAuthenticated` - флаг авторизации
- `currentUser` - данные текущего пользователя
- `login()` - метод входа
- `logout()` - метод выхода
- `loading` - состояние загрузки

## Взаимодействие компонентов

```
User -> LoginPage -> AuthService -> Artifacts API -> JWT Token
                          |
                          v
                    localStorage -> ApiClient interceptor
                          |
                          v
                    All API calls include Bearer token
                          |
                          v
                    AuthGuard validates routes
```

## Порядок реализации

### 1. Создание базовой инфраструктуры аутентификации
1. Создать AuthService с методами login/logout/getToken
2. Создать AuthContext для глобального состояния
3. Добавить useAuth хук для удобного доступа

### 2. Реализация экрана входа
1. Создать LoginPage компонент с формой
2. Добавить инструкции для получения кода
3. Реализовать обработку ошибок (неверный/истекший код)
4. Добавить loading состояние при проверке

### 3. Интеграция с ApiClient
1. Добавить request interceptor для Authorization header
2. Реализовать response interceptor для 401 ошибок
3. Модифицировать getThreads() для фильтрации по userId

### 4. Защита роутов
1. Создать AuthGuard компонент
2. Обернуть защищенные роуты в RouterWrapper
3. Реализовать сохранение target URL при редиректе
4. Добавить валидацию thread ownership

### 5. UI индикаторы авторизации
1. Создать UserIndicator для header
2. Добавить кнопку logout
3. Показывать loading при проверке токена
4. Добавить toast уведомления

### 6. Поддержка deep linking
1. Модифицировать RouteGuard для проверки владельца
2. Сохранять запрошенный URL перед login redirect
3. Восстанавливать URL после успешной авторизации

### 7. Обработка edge cases
1. Refresh при истечении токена
2. Graceful degradation при недоступности API
3. Валидация формата username (user_XXXXXX)
4. Очистка старых истекших токенов

## Критичные граничные случаи

### Безопасность
- JWT токен должен проверяться на валидность перед каждым использованием
- При любой 401 ошибке - немедленный logout
- Не показывать данные других пользователей даже при ошибке фильтрации

### User Experience
- Сохранение состояния приложения после login
- Понятные сообщения об ошибках на русском языке
- Автоматический retry при временных сбоях сети
- Индикация загрузки во всех async операциях

### Совместимость с существующим функционалом
- Deep linking должен продолжать работать
- Export функциональность должна учитывать авторизацию
- Accordion состояние должно сохраняться после login