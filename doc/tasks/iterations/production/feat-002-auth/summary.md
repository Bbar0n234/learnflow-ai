# Post-Implementation Summary: feat-002 Auth

## Результат

Полноценная аутентификация (JWT + Refresh Token) реализована и заменила MVP-заглушку (X-User-Name header). Все критерии приёмки из tasklist выполнены.

## Отклонения от design brief

### Осознанные решения архитектора (зафиксированы в implementation plan)

| Design Brief | Реализация | Обоснование |
|---|---|---|
| Rename `name` → `username` в модели User | Оставлен `name` | Семантика "username" — в UI и документации. На уровне DB/model — `name`. Избегаем миграции rename без необходимости |
| Cookie `Path=/api/auth/refresh` | `Path=/api/auth` | Logout endpoint тоже должен иметь доступ к cookie для revoke |
| Миграция: добавить `password_hash` к существующей | Clean slate: удалить старые миграции, создать новую initial | MVP не имеет данных для сохранения |

### Адаптации при реализации

| Design Brief | Реализация | Обоснование |
|---|---|---|
| Rate limit `/refresh` — ключ `user_id` | Ключ `IP` | Извлечение user_id из refresh token требует hash + DB lookup до rate check, что противоречит цели rate limiting |
| `hashlib` inline в auth service | Вынесен в `security.py` как `hash_raw_token()` | Единое место для всех hash-операций |

### Дополнения (не в design brief / plan)

| Что | Причина |
|---|---|
| `GET /api/auth/me` endpoint | Необходим для отображения username в sidebar. Возвращает `{id, name}` |
| Logout кнопка в sidebar footer | Отсутствовала и в MVP, и в плане. Без неё невозможно сменить пользователя |
| `UserResponse` schema | Для endpoint `/me` |
| `variant="link"` на toggle Login/Register | UX: hover feedback для переключателя |

## Что не вошло в scope

- Автотесты (pytest) — по conventions, добавляются после MVP
- SSE token expiry E2E тест (требует ожидания 30 мин или временной конфигурации)
- Multi-tab / multi-user изоляция (ручной тест)

## Нюансы

- **Sandbox Claude Code блокирует TCP к Docker-портам.** `make migration` и `make migrate` требуют `dangerouslyDisableSandbox: true` или отключения sandbox. Причина: Docker port forwarding через iptables NAT невидим для sandbox proxy (socat на 3128/1080).
- **PyJWT 2.11.0** установлен вместо 2.12.1 (указан в плане). API идентичен, `InsecureKeyLengthWarning` работает так же.
- **`jwt_secret: str = ""`** в первоначальной реализации нарушал fail-fast. Исправлено на `jwt_secret: str` (без дефолта) по результатам ревью архитектора.
