# ADR-011: Auth Architecture

## Статус

Принято

## Контекст

MVP-заглушка: frontend показывает модалку ввода username, сохраняет в localStorage, передаёт как `X-User-Name` header. Backend (`deps.py:get_current_user()`) извлекает header и делает `get_or_create` по имени. Никакой защиты — любой может представиться кем угодно. Внешний слой — Nginx basic auth на сервере.

Нужно: полноценная аутентификация для нескольких пользователей. Архитектура API-first (vision.md) — помимо SPA, потенциально CLI, Telegram bot, MCP-клиенты.

## Решения

### Auth-схема: JWT + Refresh Token (гибрид)

Access token (JWT, short-lived) для аутентификации API-запросов + refresh token (opaque, long-lived, хранится в БД) для обновления пары.

Access token stateless — сервер не обращается к БД на каждый запрос, только верифицирует подпись. Refresh token stateful — возможность отзыва. Максимальное окно уязвимости при компрометации access token = его lifetime (30 мин), после чего нужен refresh, который можно отозвать мгновенно.

**Отклонено:**
- **Pure JWT (без refresh)** — невозможно отозвать токен до истечения. При компрометации — ждать expiration или вводить blocklist, что убивает stateless-преимущество.
- **Server-side sessions** — каждый запрос = обращение к хранилищу сессий. Cookie-based аутентификация плохо ложится на multi-client архитектуру (CLI, Telegram, MCP). CSRF-защита обязательна. Для текущего масштаба допустимо, но не масштабируется.

### Хэширование: Argon2id (argon2-cffi)

Argon2id — рекомендация OWASP (#1), NIST SP 800-63B Rev.4, стандартизирован в RFC 9106. Memory-hard + CPU-hard — устойчив к GPU/ASIC brute force.

Параметры: дефолты argon2-cffi v25.1.0 (совпадают с RFC 9106 low-memory profile): `memory_cost=65536` (64 MiB), `time_cost=3`, `parallelism=4`. Целевое время хэширования ~50ms, при необходимости подстроить `time_cost` под production-железо.

Библиотека: `argon2-cffi` — Production/Stable, Python 3.8-3.14, активная поддержка (Hynek Schlawack, Tidelift), v25.1.0 (июнь 2025).

**Отклонено:**
- **bcrypt** — не memory-hard (только CPU-hard), уступает Argon2id по устойчивости к современным атакам. Ограничение 72 байта на пароль.
- **passlib** — последний релиз октябрь 2020, сломан на Python 3.13+ (удалён модуль `crypt`, PEP 594). Мёртв.
- **pwdlib** — обёртка над argon2-cffi от автора fastapi-users. Beta (v0.3.0). Главная фича — автоматический upgrade legacy-хэшей — не нужна (нет legacy). Лишний слой абстракции без пользы.

### JWT: PyJWT + HS256

PyJWT — де-факто стандарт Python-экосистемы: ~449M downloads/мес, Python 3.9-3.14, чистая история безопасности. FastAPI официально мигрировал с python-jose на PyJWT (май 2024). fastapi-users зависит от PyJWT.

HS256 (HMAC-SHA256) — симметричный алгоритм. Один секрет для подписи и верификации. Достаточен при single-service архитектуре (один backend подписывает и проверяет). Асимметричные алгоритмы (RS256) нужны, когда токены верифицируют несколько сервисов с разными уровнями доверия — не наш случай.

**Отклонено:**
- **python-jose** — заброшен 4 года (2021-2025), множественные CVE (CVE-2024-33663, CVE-2024-33664, CVE-2024-23342), timing-атаки. Возрождён, но security debt накоплен. Нет поддержки Python 3.14.
- **joserfc** — сильная библиотека (автор Authlib), но нишевая (~33M downloads). Оправдана при потребности в JWE, JSON serialization — не наш случай.

### Token storage: access → localStorage, refresh → httpOnly cookie

Два типа токенов — два типа хранилища, компенсирующих слабости друг друга:

**Access token в localStorage:** JS имеет доступ (уязвим к XSS), но токен short-lived (30 мин) — окно атаки ограничено. Не отправляется автоматически (иммунен к CSRF). Работает через `Authorization: Bearer` header — единообразно для SPA, CLI, любого клиента. Переживает перезагрузку страницы.

**Refresh token в httpOnly cookie:** JS не имеет доступа (защищён от XSS). Отправляется автоматически (теоретически уязвим к CSRF), но: `SameSite=Lax` блокирует cross-origin POST, `Path=/api/auth/refresh` ограничивает scope, а access token возвращается в response body (CORS не даёт evil.com прочитать). Атрибуты: `httpOnly`, `Secure`, `SameSite=Lax`, `Path=/api/auth/refresh`.

**Отклонено:**
- **Оба в localStorage** — XSS получает полный доступ к refresh token, компрометация без ограничения по времени. Неприемлемо.
- **Оба в httpOnly cookie** — CSRF-защита обязательна для всех API-эндпоинтов, не только auth. Сложнее для non-browser клиентов.
- **Access в памяти (JS variable)** — каждая перезагрузка страницы = silent refresh + мигание UI. Сложнее в реализации, выигрыш минимален для short-lived токена.

### Token rotation: одноразовые refresh tokens

При каждом использовании refresh token инвалидируется, выдаётся новая пара (access + refresh). Повторное использование уже инвалидированного токена — сигнал компрометации → инвалидация всех refresh tokens пользователя (force re-login).

Механизм обнаружения replay-атак: если атакующий и реальный пользователь оба имеют один refresh token, первый использовавший получает новую пару, второй триггерит alarm.

## Следствия

- Новые зависимости: `argon2-cffi`, `PyJWT`
- `JWT_SECRET` — новый секрет в env, критичен для безопасности (компрометация = forge любого токена)
- `get_current_user()` в deps.py — единственная точка изменения backend-аутентификации. Все роуты, использующие `CurrentUser`, не меняются
- Точка расширения: email (добавление nullable поля + SMTP), OAuth (дополнительные auth endpoints), 2FA — не требуют изменения JWT/refresh схемы
- После реализации feat-002 — Nginx basic auth на сервере становится избыточным и убирается отдельно
