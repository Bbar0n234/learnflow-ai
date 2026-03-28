# feat-002: Auth — Design Brief

Контекст реализации для implementation plan. Архитектурные решения: [ADR-011](../../../tech/adr/ADR-011-auth-architecture.md).

## Backend

### Auth endpoints

Новый роутер `/api/auth/`:

- `POST /register` — username + password → создание пользователя, выдача пары токенов. Валидация: username уникален, пароль >= 8 символов.
- `POST /login` — username + password → верификация, выдача пары токенов. Generic error "Invalid credentials" (не раскрывать, что именно неверно).
- `POST /refresh` — refresh token из httpOnly cookie → верификация в БД → rotation → новая пара. Access token в response body, refresh token в Set-Cookie.
- `POST /logout` — revoke refresh token в БД, удалить cookie.

### Token lifecycle

**Access token (JWT):**
- Алгоритм: HS256, подпись через `JWT_SECRET`
- Payload: `{sub: user_id, exp, iat}`
- Lifetime: 30 минут
- Передача: `Authorization: Bearer <token>`

**Refresh token:**
- Формат: opaque string (UUID или secrets.token_urlsafe)
- Хранение в БД: хэш токена (не plaintext). Хэширование: SHA-256 достаточно (токен уже high-entropy, не пароль)
- Lifetime: 30 дней
- Передача: httpOnly cookie (`refresh_token`)
- Cookie-атрибуты: `httpOnly`, `Secure`, `SameSite=Lax`, `Path=/api/auth/refresh`
- Rotation: каждое использование инвалидирует текущий, выдаёт новый
- Replay detection: повторное использование инвалидированного токена → revoke всех refresh tokens пользователя

### DB

**Модель User — изменения:**
- Добавить `password_hash: str` (Argon2id)
- `name` → семантически становится `username` (уникальный логин-идентификатор)

**Новая таблица `refresh_tokens`:**
- `id: UUID` (PK)
- `user_id: UUID` (FK → users)
- `token_hash: str` (SHA-256 хэш токена)
- `expires_at: datetime`
- `created_at: datetime`
- `revoked_at: datetime | None` (None = активен)

Миграция: drop база, накатить заново. Существующие данные не ценны (2 тестовых пользователя).

### Rate limiting

Нативная in-memory реализация (middleware). Словарь `{key → [timestamps]}`, cleanup по TTL.

| Endpoint | Лимит | Ключ |
|----------|-------|------|
| `POST /auth/login` | 5 req / мин | username + IP |
| `POST /auth/register` | 3 req / час | IP |
| `POST /auth/refresh` | 10 req / мин | user_id (из токена) |

Превышение → `429 Too Many Requests` с `Retry-After` header.

### Config

Новые переменные в `config.py` (из env):
- `JWT_SECRET` — обязательная, без дефолта (fail-fast при отсутствии)
- `ACCESS_TOKEN_EXPIRE_MINUTES` — дефолт 30
- `REFRESH_TOKEN_EXPIRE_DAYS` — дефолт 30

### deps.py — точка интеграции

`get_current_user()` — единственная функция, которая меняется:
- Было: извлечь `X-User-Name` header → `get_or_create`
- Станет: извлечь JWT из `Authorization: Bearer` → decode → достать `user_id` → lookup в БД

`CurrentUser` / `UserProject` — зависимости в роутах остаются без изменений. Все существующие роуты (projects, chats) продолжают работать.

## Frontend

### Auth UI

`AuthGate.tsx` — замена модалки username на полноценный Login/Register form:
- Два режима: Login / Register (переключение)
- Поля: username, password (+ подтверждение пароля для Register)
- Валидация на клиенте: непустые поля, совпадение паролей, минимальная длина
- При успехе: сохранить access token в localStorage, redirect на основной UI

### Token management

`client.ts` — axios interceptor:
- Было: `X-User-Name` из localStorage
- Станет: `Authorization: Bearer <access_token>` из localStorage

Refresh logic (axios response interceptor):
- 401 на любой API-запрос → `POST /auth/refresh` (cookie отправится автоматически)
- Успех → обновить access token в localStorage, retry оригинальный запрос
- 401 на refresh → redirect на login (сессия истекла)
- Queue: параллельные запросы, получившие 401, ждут один refresh, а не спамят

Logout:
- `POST /auth/logout` → удалить access token из localStorage

### Удаление legacy

- Убрать `getUsername()` / `setUsername()` из `client.ts`
- Убрать `learnflow-username` из localStorage
- Модалка AuthGate → Login/Register form

## Scope boundaries (не feat-002)

- Email-based регистрация, password reset, SMTP
- OAuth / SSO
- 2FA
- Sentry integration (frontend error reporting)
- Distributed rate limiting (Redis)
- Session management UI ("активные сессии")
