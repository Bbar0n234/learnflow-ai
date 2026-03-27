# Implementation Plan: feat-002 Auth

## Context

MVP-заглушка аутентификации: frontend показывает модалку ввода username, сохраняет в localStorage, передаёт как `X-User-Name` header. Backend `get_current_user()` в `deps.py` извлекает header и делает `get_or_create` по имени. Никакой защиты — любой может представиться кем угодно.

Цель feat-002: полноценная аутентификация (JWT + Refresh Token), замена MVP-заглушки. Безопасный доступ для нескольких пользователей.

## References

- [ADR-011: Auth Architecture](doc/tech/adr/ADR-011-auth-architecture.md) — архитектурные решения
- [Design Brief](doc/tasks/iterations/production/feat-002-auth/design-brief.md) — контекст реализации
- [Tasklist](doc/tasks/tasklist-production.md) — состав работ и критерии приёмки
- [Conventions](doc/tech/conventions.md) — git flow, именование, code quality
- [Workflow](doc/workflow.md) — процесс итерации

## API verification (inspect)

Таблица «Быстро меняющиеся инструменты» (Langfuse SDK v4, structlog, GitHub Actions) — не релевантна для feat-002. Проверены библиотеки feat-002:

**argon2-cffi v25.1.0:**
- `PasswordHasher()` — defaults: time_cost=3, memory_cost=65536, parallelism=4, type=Argon2id (совпадают с ADR-011)
- `ph.hash(password) → str` (формат `$argon2id$v=19$m=65536,t=3,p=4$...`)
- `ph.verify(hash, password) → True` или `VerifyMismatchError`
- `ph.check_needs_rehash(hash) → bool`
- Note: `argon2.__version__` deprecated — не использовать

**PyJWT v2.12.1:**
- `jwt.encode(payload: dict, key: str, algorithm: str = 'HS256') → str`
- `jwt.decode(jwt: str, key: str, algorithms: list[str]) → dict`
- Exceptions: `ExpiredSignatureError`, `InvalidTokenError`, `DecodeError`, `InvalidSignatureError`
- **Важно:** PyJWT 2.12.1 выдаёт `InsecureKeyLengthWarning` при HMAC key < 32 байт для HS256. `JWT_SECRET` должен быть >= 32 символов — указать в .env.example

## Решения архитектора

| Вопрос | Решение |
|--------|---------|
| Cookie Path | `Path=/api/auth` — cookie на все auth endpoints (refresh, logout). Отклонение от brief `/api/auth/refresh` обосновано: logout должен иметь доступ к cookie для revoke |
| Secure flag | `SECURE_COOKIES: bool = True` в Settings. `.env.local.example` → `false`. Production — `true` по умолчанию |
| Миграция | Clean slate: удалить 2 существующих файла миграции, сгенерировать новую initial. Drop DB + migrate |
| User.name | Оставить `name` на уровне DB/model. Семантика "username" — только в документации и UI labels |

---

## План реализации

### Шаг 0: Зависимости

**Файлы:** `backend/pyproject.toml`

- `uv add --package learnflow-backend argon2-cffi PyJWT`
- Зависимости уже проверены через inspect (см. выше)

### Шаг 1: Config

**Файлы:** `backend/app/config.py`, `.env.example`, `.env.local.example`

Settings — новые поля:
```python
jwt_secret: str          # обязательная, без дефолта — fail-fast
access_token_expire_minutes: int = 30
refresh_token_expire_days: int = 30
secure_cookies: bool = True  # false для local dev (.env.local)
```

`.env.example`:
```
JWT_SECRET=change-me-to-a-random-string-at-least-32-chars
```

`.env.local.example`:
```
SECURE_COOKIES=false
```

### Шаг 2: DB — модели

**Файлы:**
- `backend/app/models/user.py` — добавить `password_hash: Mapped[str]`
- `backend/app/models/refresh_token.py` — новая модель RefreshToken
- `backend/app/models/__init__.py` — экспорт RefreshToken

**User — изменения:**
```python
class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # relationships ...
```

**RefreshToken (новая):**
```python
class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64))  # SHA-256 hex digest
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship()
```

Индексы: `user_id` (FK index), `token_hash` (для lookup при refresh/logout).

### Шаг 3: Миграция

**Файлы:** `backend/alembic/versions/`

- Удалить `4512c02eeb05_create_app_tables.py` и `6b69e2cad2ae_add_message_id_to_artifacts.py`
- `make migration msg="initial schema with auth"`
- Проверить сгенерированный файл (users.password_hash, refresh_tokens table, индексы)

### Шаг 4: Repository — RefreshToken

**Файлы:**
- `backend/app/repositories/refresh_token.py` — новый
- `backend/app/repositories/user.py` — добавить `get_by_name()`
- `backend/app/repositories/__init__.py` — экспорт

**RefreshTokenRepository:**
- `create(user_id, token_hash, expires_at) → RefreshToken`
- `get_by_hash(token_hash) → RefreshToken | None` — без фильтров по статусу (для replay detection в service)
- `revoke(token_id)` — set revoked_at = now
- `revoke_all_for_user(user_id)` — revoke все активные tokens пользователя (replay detection)

**UserRepository — добавить:**
- `get_by_name(name) → User | None` — для login (без get_or_create, т.к. пользователь должен быть зарегистрирован)

### Шаг 5: Auth Service

**Файлы:**
- `backend/app/services/auth.py` — новый
- `backend/app/services/__init__.py` — экспорт

Чистый service layer — бизнес-логика аутентификации:

**Методы:**

`register(name, password, session) → (User, access_token, refresh_token_raw)`
- Проверить уникальность username
- Hash password (argon2)
- Создать User
- Создать refresh token (secrets.token_urlsafe + SHA-256 hash в БД)
- Encode access JWT
- Return

`login(name, password, session) → (User, access_token, refresh_token_raw)`
- Lookup user by name
- Verify password (argon2 ph.verify)
- Создать refresh token
- Encode access JWT
- Return
- Generic error "Invalid credentials" при неудаче

`refresh(token_raw, session) → (access_token, new_refresh_token_raw)`
- Hash incoming token → `repo.get_by_hash(hash)` (без фильтра по статусу)
- Если None → raise InvalidToken (токен не существует)
- Если `revoked_at is not None` → replay detected → `repo.revoke_all_for_user(user_id)`, raise ReplayDetected
- Если `expires_at < now` → raise TokenExpired
- Активный → revoke текущий, создать новый refresh token, encode new access JWT
- Return

`logout(token_raw, session) → None`
- Hash → lookup → revoke
- Если не найден — silent success (idempotent)

**Вспомогательные функции (внутри модуля или отдельный `security.py`):**
- `hash_password(password) → str` — argon2 PasswordHasher().hash()
- `verify_password(hash, password) → bool` — try/except VerifyMismatchError
- `create_access_token(user_id, secret, expire_minutes) → str` — jwt.encode
- `decode_access_token(token, secret) → uuid.UUID` — jwt.decode, extract sub
- `generate_refresh_token() → (raw, hash)` — secrets.token_urlsafe(32), hashlib.sha256

### Шаг 6: Auth Schemas

**Файлы:** `backend/app/api/schemas/auth.py` — новый

```python
class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=8)

class LoginRequest(BaseModel):
    name: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class MessageResponse(BaseModel):
    detail: str
```

### Шаг 7: Auth Router

**Файлы:**
- `backend/app/api/routes/auth.py` — новый
- `backend/app/api/routes/__init__.py` — экспорт
- `backend/app/main.py` — include router

Router `APIRouter(prefix="/auth", tags=["auth"])`:

`POST /register`:
- Body: RegisterRequest
- Вызов auth_service.register()
- Set refresh cookie (httpOnly, Secure=settings.secure_cookies, SameSite=Lax, Path=/api/auth, Max-Age=30d)
- Return TokenResponse (access_token)

`POST /login`:
- Body: LoginRequest
- Вызов auth_service.login()
- Set refresh cookie
- Return TokenResponse

`POST /refresh`:
- Извлечь refresh_token из cookie
- Вызов auth_service.refresh()
- Set new refresh cookie
- Return TokenResponse

`POST /logout`:
- Извлечь refresh_token из cookie
- Вызов auth_service.logout()
- Delete cookie (Set-Cookie с Max-Age=0)
- Return MessageResponse

main.py: `app.include_router(auth.router, prefix=api_prefix)`

### Шаг 8: Rate Limiting Middleware

**Файлы:** `backend/app/infra/rate_limit.py` — новый, `backend/app/main.py` — подключение

In-memory rate limiter (dict-based):

```python
class RateLimiter:
    def __init__(self):
        self._buckets: dict[str, list[float]] = {}

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> tuple[bool, int | None]:
        """Returns (allowed, retry_after_seconds)."""
        ...
```

Middleware/dependency для auth endpoints:
| Endpoint | Лимит | Ключ |
|----------|-------|------|
| POST /auth/login | 5 req/мин | username + IP |
| POST /auth/register | 3 req/час | IP |
| POST /auth/refresh | 10 req/мин | user_id (из refresh token) |

Реализация: FastAPI dependency на каждый endpoint (не глобальный middleware), т.к. лимиты и ключи разные для каждого endpoint. Cleanup старых записей — lazy (при каждой проверке).

429 response с `Retry-After` header.

### Шаг 9: deps.py — переключение аутентификации

**Файлы:** `backend/app/api/deps.py`

`get_current_user()` — единственная точка изменения:

```python
async def get_current_user(
    request: Request,
    session: DBSession,
) -> User:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header.removeprefix("Bearer ")
    try:
        user_id = decode_access_token(token, settings.jwt_secret)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user
```

`CurrentUser` / `UserProject` — без изменений. Все существующие роуты (projects, chats, messages, artifacts, sphere) продолжают работать.

Нужен доступ к Settings — через `request.app.state` или повторный `Settings()`.

### Шаг 10: Frontend — Auth UI

**Файлы:**
- `frontend/src/app/components/AuthGate.tsx` — переписать: Login/Register form
- `frontend/src/shared/api/auth.ts` — новый: API-функции для auth endpoints

**AuthGate.tsx — замена:**
- Два режима: Login / Register (toggle)
- Поля: username, password (+password confirmation для Register)
- Client-side validation: непустые поля, пароль >= 8, совпадение паролей (register)
- При успехе: сохранить access_token в localStorage, рендерить children
- При ошибке: показать сообщение (generic "Invalid credentials" для login)
- Проверка: если access_token в localStorage — сразу показать children (проверка валидности — первый API-запрос вернёт 401 → refresh)

**auth.ts:**
- `register(name, password) → TokenResponse`
- `login(name, password) → TokenResponse`
- `refresh() → TokenResponse` (cookie отправится автоматически)
- `logout() → void`

### Шаг 11: Frontend — Token Management

**Файлы:**
- `frontend/src/shared/api/client.ts` — переписать interceptors
- `frontend/src/features/chat/hooks/useAgentStream.ts` — заменить X-User-Name на Bearer

**client.ts — token utilities:**

```typescript
const ACCESS_TOKEN_KEY = "learnflow-access-token";

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function setAccessToken(token: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
}
```

**client.ts — `ensureFreshToken()`:**

Проактивная проверка и обновление access token. Используется перед SSE fetch и может использоваться в request interceptor:

```typescript
export async function ensureFreshToken(): Promise<string | null> {
  const token = getAccessToken();
  if (!token) return null;

  // Decode JWT payload (base64, без библиотеки)
  const payload = JSON.parse(atob(token.split(".")[1]));
  const expiresIn = payload.exp - Date.now() / 1000;

  if (expiresIn > 30) return token;  // ещё свежий (> 30 сек до expiry)

  // Проактивный refresh
  try {
    const { data } = await apiClient.post("/auth/refresh");
    setAccessToken(data.access_token);
    return data.access_token;
  } catch {
    clearAccessToken();
    window.location.reload();
    return null;
  }
}
```

**client.ts — axios interceptors:**

Request interceptor:
```typescript
apiClient.interceptors.request.use((config) => {
  const token = getAccessToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
```

Response interceptor — reactive 401 handling (safety net):
```typescript
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;
      try {
        const { data } = await apiClient.post("/auth/refresh");
        setAccessToken(data.access_token);
        originalRequest.headers.Authorization = `Bearer ${data.access_token}`;
        return apiClient(originalRequest);
      } catch {
        clearAccessToken();
        window.location.reload();
      }
    }
    return Promise.reject(error);
  },
);
```

Queue для параллельных 401: одна переменная `isRefreshing` + массив pending promises. При первом 401 — refresh. Остальные 401 ждут результат и retry с новым token.

**useAgentStream.ts — двухуровневая обработка:**

1. **Proactive:** перед SSE fetch вызвать `ensureFreshToken()` — обновит token если close to expiry
2. **Reactive fallback:** если fetch всё равно вернул 401 → refresh → retry один раз

```typescript
// Proactive: ensure token is fresh before SSE
const token = await ensureFreshToken();
if (!token) return;

const response = await fetch(url, {
  headers: { "Authorization": `Bearer ${token}`, ... },
  ...
});

// Reactive fallback: 401 → refresh → retry once
if (response.status === 401) {
  const freshToken = await ensureFreshToken(); // force refresh
  if (!freshToken) return;
  // retry fetch with freshToken...
}
```

### Шаг 12: Frontend — Удаление legacy

**Файлы:** `frontend/src/shared/api/client.ts`, `frontend/src/features/chat/hooks/useAgentStream.ts`

- Удалить `USERNAME_KEY`, `getUsername()`, `setUsername()` из client.ts
- Убрать импорт `getUsername` из useAgentStream.ts
- AuthGate: модалка username → Login/Register form (уже в шаге 10)

### Шаг 13: Обновление .env.example / .env.local.example

**Файлы:** `.env.example`, `.env.local.example`

`.env.example` — добавить:
```
# Auth
JWT_SECRET=change-me-to-a-random-string-at-least-32-chars
```

`.env.local.example` — добавить:
```
SECURE_COOKIES=false
```

### Шаг 14: Верификация

1. `make check` — ruff + mypy проходят
2. `make lint-fe` — ESLint без ошибок
3. Drop DB + migrate: `docker compose down -v && make docker-up-db && sleep 2 && make migrate`
4. `make dev` + `make dev-fe`
5. Manual E2E:
   - Register нового пользователя → получить access token → попасть на главный экран
   - Создать проект, отправить сообщение → API-запросы с Bearer token → работает
   - Дождаться истечения access token (или вручную удалить из localStorage) → refresh → transparent recovery
   - Logout → redirect на login
   - Повторный login → всё работает
   - Rate limiting: 6x login attempt → 429
   - Второе окно → register другой user → данные изолированы

### Шаг 15: Ревью архитектора

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.
