# Design Brief: OAuth-вход — Яндекс ID / VK ID / Google / GitHub с гео-разделением + каркас `/login`

**Итерация:** dogfooding feat-008 (I) — [tasklist-dogfooding.md](../../../tasklist-dogfooding.md)
**Scope:** cross-cutting (Frontend + Backend + Design-branding)
**Ресёрч-артефакты:** [research-legal-geo.md](research-legal-geo.md) · [research-data-model.md](research-data-model.md) · [research-provider-libs.md](research-provider-libs.md)

## Контекст и цель

Сегодня единственный способ входа — логин/пароль в блокирующей модалке `AuthGate` над роутером. Итерация добавляет вход через внешних провайдеров (пользователь не заводит отдельный пароль) и перестраивает вход на полноценную страницу `/login`. Состав провайдеров продиктован ч. 10 ст. 8 149-ФЗ (штрафы по ст. 13.55 КоАП с 07.07.2026): пользователям из РФ показываются и разрешаются только Яндекс ID / VK ID (+ пароль), остальным — Google / GitHub (+ пароль, + опционально российские кнопки). Юридическая рамка, ответственность и границы — [research-legal-geo.md](research-legal-geo.md).

Ключевая рамка архитектуры: **OAuth заканчивается в момент, когда мы надёжно узнали `(provider, provider_account_id)`**. Дальше без изменений работает существующая сессионная машина (`_create_access` / `_create_refresh`, ротация refresh, replay-детекция) — итерация не трогает [auth.md](../../../../tech/auth.md)-механику токенов.

Утверждённые решения взятия в работу (состав провайдеров, серверный гео-enforcement, модель данных, ручной httpx-слой без authlib, порядок «Яндекс первым», граница с feat-013) — в секции итерации в tasklist; бриф их детализирует, не пересматривает.

## Целевой UX

- **Страница `/login`** заменяет модалку: неаутентифицированный пользователь на любом маршруте попадает на `/login` (с запоминанием исходного пути), после входа возвращается. Логин и регистрация — два режима одной страницы (как сейчас в `AuthGate`), копирайт русский.
- Сверху — **кнопки провайдеров**, состав приходит с бэкенда (`GET /api/auth/providers`, по гео): РФ — «Войти с Яндексом», «Войти через VK», не-РФ — Google, GitHub. Ниже — парольная форма (для всех).
- Для OAuth-регистрации отдельного шага нет: первый вход провайдером создаёт аккаунт (find-or-create), различие login/register для OAuth-пользователя не существует.
- **Каркас, не дизайн** (граница с feat-013): существующие shadcn-примитивы, целевая FSD-структура `pages/login`, русские тексты; wordmark/иллюстрации/полировка — feat-013 поверх, после merge этой итерации.
- Ошибки OAuth-флоу (отказ пользователя на экране провайдера, гео-запрет, протухший state) возвращают на `/login` с человекочитаемым сообщением — не белый экран.

## Архитектура

### Флоу целиком

```mermaid
sequenceDiagram
    participant B as Браузер (SPA)
    participant BE as Backend
    participant P as Провайдер

    B->>BE: GET /api/auth/oauth/{provider}/authorize
    Note over BE: гео-gate: провайдер разрешён для страны IP?<br/>rate limit; state + PKCE-пара
    BE-->>B: 302 на провайдера + Set-Cookie: oauth_flow (httpOnly, 10 мин)
    B->>P: authorize-страница, согласие пользователя
    P-->>B: 302 /api/auth/oauth/{provider}/callback?code&state(+device_id у VK)
    B->>BE: GET callback (cookie oauth_flow приедет: top-level GET, SameSite=Lax)
    Note over BE: гео-gate повторно; сверка state (query ↔ cookie);<br/>обмен code+verifier(+secret) → токен провайдера;<br/>userinfo → (provider, account_id, email)
    Note over BE: find-or-create user + oauth_account (одна транзакция)
    BE-->>B: 302 на SPA + Set-Cookie: refresh_token (штатная механика)<br/>+ Set-Cookie: oauth_flow удалена
    B->>BE: POST /api/auth/refresh (существующий)
    BE-->>B: access token + ротированный refresh
```

Существенное свойство: **access token не передаётся через redirect-URL** (грязный канал). Callback ставит только штатную httpOnly refresh-cookie и редиректит на SPA; SPA получает access существующим `POST /api/auth/refresh`. Ротация одноразового refresh при этом срабатывает штатно — выданный в callback токен гасится первым же refresh. Ноль новых механик доставки токенов.

### Хранение state / PKCE-verifier: подписанная httpOnly-cookie

Решение открытого вопроса. Между `/authorize` и `/callback` бэкенду нужно помнить `state` и `code_verifier` того браузера, который начал флоу. БД-таблица и server-side session не нужны:

- На `/authorize` бэкенд генерит `state` (`secrets.token_urlsafe(32)`) и `code_verifier` (`secrets.token_urlsafe(64)`), кладёт их в **JWT, подписанный существующим `JWT_SECRET`** (pyjwt уже в зависимостях), claims: `{state, verifier, provider, exp: +10 мин}` — и ставит cookie `oauth_flow`: httpOnly, `SameSite=Lax`, `Secure` по `SECURE_COOKIES`, `Path=/api/auth/oauth`, `max_age=600`.
- Redirect от провайдера — top-level GET-навигация, `SameSite=Lax` такую cookie отправляет (ровно кейс, под который Lax спроектирован).
- На `/callback`: декод и валидация подписи/exp/`provider`-совпадения, сверка `state` из query с claim — затем cookie удаляется. Подпись исключает подделку содержимого клиентом; httpOnly исключает чтение из JS.
- Ограничение: два параллельных флоу в соседних вкладках перезапишут cookie друг друга — старшая вкладка упадёт на state mismatch с редиректом на `/login` и сообщением «попробуйте ещё раз». Принимаем.

### Провайдер-слой (backend)

Собственная тонкая абстракция на httpx (решение зафиксировано; сравнение с authlib — [research-provider-libs.md](research-provider-libs.md)):

```
app/infra/oauth/
├── base.py        # OAuthProvider (typing.Protocol): authorize_url(state, challenge, redirect_uri) /
│                  #   exchange_code(code, verifier, redirect_uri, extra) / fetch_profile(token) → OAuthProfile
├── yandex.py      # обычный code flow; профиль GET login.yandex.ru/info
├── vk.py          # PKCE+device_id+state в теле обмена, service_token; POST id.vk.ru/oauth2/user_info
├── google.py      # code flow; профиль через userinfo-endpoint (JWKS-валидация id_token не требуется)
└── github.py      # code flow; email добором через /user/emails при null (scope user:email)
```

- `OAuthProfile` — нормализованный результат: `provider`, `provider_account_id: str`, `email: str | None`, `display_name: str | None` (кандидат для `users.name`).
- Интерфейс — `typing.Protocol` (конвенция); реализации — классы с конфигом из `Settings`, без module-level state; реестр активных провайдеров собирается в lifespan и живёт в `app.state` (провайдер активен ⇔ его креды заданы в env — dev-окружение может гонять один Яндекс).
- VK-особенности (обязательный `device_id` из callback-query в теле обмена, `state` в теле token-запроса, `service_token` вместо secret) локализованы внутри `vk.py` — наружу тот же Protocol.
- Сетевые вызовы — httpx AsyncClient с таймаутом; отказ провайдера (5xx, таймаут, невалидный код) — доменное исключение → редирект на `/login?error=provider_unavailable`, `logger.warning`.

### Гео-gate

- `app/infra/geoip.py`: reader MMDB (пакет `geoip2`), база **IPinfo Lite** (fallback — MaxMind GeoLite2), путь из `GEOIP_DB_PATH`. Reader открывается в lifespan → `app.state` (mmap, микросекунды на запрос). Обновление базы — вне процесса (cron/deploy-артефакт), процесс перечитывает файл при рестарте; горячая перезагрузка не нужна.
- IP — строго через существующий `app.infra.client_ip.get_client_ip`.
- **Fallback-страна при недоступной/несконфигурированной базе — `GEOIP_FALLBACK_COUNTRY`, default `RU`** (fail-closed в сторону закона: деградация «иностранец видит только Яндекс/VK + пароль» юридически безопасна и функционально не блокирует вход — пароль работает для всех; обратный отказ открыл бы Google/GitHub для РФ). В dev без базы можно выставить `US` для проверки не-РФ ветки.
- Enforcement в трёх точках: `GET /api/auth/providers` (состав кнопок), `/authorize` и `/callback` (отклонение запрещённого провайдера для RU-IP → редирект на `/login?error=provider_not_available_in_region`). Проверка в callback обязательна: смена IP между шагами и прямое обращение к callback мимо UI.
- Атрибуция IPinfo (CC BY-SA) — строка в футере страницы `/login` и/или в README — финализируется в реализации.

### Эндпоинты и сервисный слой

| Метод | Путь | Назначение | Rate limit | Auth |
|-------|------|-----------|------------|------|
| GET | `/api/auth/providers` | Доступные способы входа по гео: `{providers: ["yandex","vk"], password: true}` | — | — |
| GET | `/api/auth/oauth/{provider}/authorize` | Гео-gate → state/PKCE → cookie `oauth_flow` → 302 на провайдера | 10/мин/IP | — |
| GET | `/api/auth/oauth/{provider}/callback` | Сверки → обмен → профиль → find-or-create → refresh-cookie → 302 на SPA | 10/мин/IP | cookie `oauth_flow` |

- `{provider}` валидируется по реестру активных провайдеров (неизвестный/выключенный → 404).
- `OAuthService` (`app/services/oauth.py`): `login_with_provider(profile) → (user, access, refresh)` — одна транзакция: lookup `oauth_accounts` по `(provider, account_id)` → найден: пользователь + освежение `email`; не найден: создание `User` (без пароля) + `OAuthAccount` атомарно, генерация `users.name` из `display_name` с суффиксом на unique violation (алгоритм — [research-data-model.md](research-data-model.md)); далее — существующие `_create_access`/`_create_refresh` из `AuthService` (переиспользование, не копия).
- SIEM: callback эмитит события входа по образцу существующего `login` (успех/отказ, поле способа входа) — состав полей выравнивается с текущими событиями auth-роутов на реализации.
- Редирект на SPA: успех — `/{next}` (валидированный **относительный** путь из claim `next` cookie, default `/`; никаких открытых редиректов), ошибка — `/login?error=<код>`.

### Модель данных и миграция

Зафиксирована в [research-data-model.md](research-data-model.md) (DDL-эскиз, таблица решений, postgresql-ревью): новая `oauth_accounts`, `users.password_hash → nullable`, `users.email` не вводится, токены провайдера не хранятся. Одна autogenerate-ревизия против запущенной БД. Инвариант «пароль ИЛИ oauth-связка» — сервисный слой (одна транзакция создания). Парольный логин при `password_hash IS NULL` отклоняется тем же 401, что и неверный пароль (без утечки способа входа аккаунта).

Решение модели тянет **ADR** (identity model: отдельная таблица связок, запрет авто-линковки, nullable-пароль) — пишется в итерации на базе research-документа, номер по очереди ADR.

### Конфигурация (env)

Atomic change четырёх мест: `Settings` + `.env.example` + `.env.local.example` + `docker-compose.yml`.

| Переменная | Default | Назначение |
|-----------|---------|-----------|
| `OAUTH_YANDEX_CLIENT_ID` / `OAUTH_YANDEX_CLIENT_SECRET` | `""` | Пара Яндекс OAuth; пусто → провайдер выключен |
| `OAUTH_VK_CLIENT_ID` / `OAUTH_VK_SERVICE_TOKEN` | `""` | VK ID (confidential: service_token вместо secret) |
| `OAUTH_GOOGLE_CLIENT_ID` / `OAUTH_GOOGLE_CLIENT_SECRET` | `""` | Google |
| `OAUTH_GITHUB_CLIENT_ID` / `OAUTH_GITHUB_CLIENT_SECRET` | `""` | GitHub |
| `OAUTH_REDIRECT_BASE_URL` | `http://localhost:8000` | База для redirect_uri (`{base}/api/auth/oauth/{provider}/callback`); прод — `https://learnflow.me` |
| `GEOIP_DB_PATH` | `""` | Путь к MMDB; пусто → fallback-страна |
| `GEOIP_FALLBACK_COUNTRY` | `RU` | Страна при недоступной базе (fail-closed в сторону закона) |

Секреты провайдеров — операционные значения, не бизнес-инварианты; список разрешённых провайдеров для RU (`{"yandex","vk"}`) — бизнес-инвариант, живёт в коде.

### Frontend

- **`AuthGate` умирает.** Вход перестраивается: `BrowserRouter` оборачивает всё приложение; guard-компонент (`RequireAuth`) на layout-маршруте редиректит неаутентифицированных на `/login` с сохранением `from`; `/login` — публичный маршрут.
- **`pages/login`** (FSD): режимы вход/регистрация, парольная форма (существующие `shared/api/auth.ts` функции), блок кнопок провайдеров из `GET /api/auth/providers` (данные — TanStack Query). Кнопка провайдера — **полный переход страницы** `window.location.assign('/api/auth/oauth/{p}/authorize')`, не fetch (флоу редиректный). Обработка `?error=<код>` — инлайн-сообщение.
- **Возврат из OAuth:** SPA загружается по редиректу callback'а; бутстрап аутентификации один для всех путей: нет access в localStorage → `POST /api/auth/refresh` → есть refresh-cookie (OAuth только что поставил) → access получен, вход завершён; нет — `/login`. Отдельный callback-маршрут SPA не нужен.
- Существующие interceptor, `ensureFreshToken`, ключ localStorage — без изменений.
- Новый auth-стор не заводится: состояние — страница `/login` (локально) + существующий механизм токена; если реализация упрётся в необходимость шаринга — эскалация, не молчаливый стор.
- Тесты: `router.test.tsx` расширяется (редирект на `/login`, публичность `/login`); MSW-хендлеры для `/providers`.

## Контракты (сводно)

| Контракт | Изменение |
|----------|-----------|
| `GET /api/auth/providers` | новый; `{providers: string[], password: bool}` по гео IP |
| `GET /api/auth/oauth/{provider}/authorize` | новый; 302 + cookie `oauth_flow` |
| `GET /api/auth/oauth/{provider}/callback` | новый; 302 на SPA + штатная refresh-cookie |
| Cookie `oauth_flow` | новая; httpOnly, Lax, `Path=/api/auth/oauth`, 600 с, JWT-подпись `JWT_SECRET` |
| БД | `oauth_accounts` (новая), `users.password_hash` → nullable; autogenerate-миграция |
| `Settings`/env | 11 переменных (таблица выше), atomic change 4 мест |
| Роутинг SPA | `/login` публичный; guard на layout; `AuthGate` удаляется |
| `router.tsx` | правки только структуры входа — catch-all `path="*"` принадлежит feat-013 |

Актуализация документации по итогам: `auth.md` (OAuth-флоу, эндпоинты, cookie `oauth_flow`, env-таблица), `backend.md` (слои: `infra/oauth`, `infra/geoip`, `OAuthService`), `frontend.md` (вход страницей, дерево модулей), `security/architecture.md` (новая поверхность: OAuth-callback, гео-gate), новый ADR.

## Ручные шаги архитектора

1. **Сейчас (разблокирует T1-вертикаль):** dev-приложение Яндекс OAuth (oauth.yandex.ru, redirect `http://localhost:8000/api/auth/oauth/yandex/callback`, без верификации) → пара в `.env.local`.
2. Prod-приложение Яндекс (redirect на `https://learnflow.me/...`) — к деплою.
3. VK ID: dev-инфраструктура `dev.learnflow.me` → 127.0.0.1 + локальный TLS (DNS-01), регистрация приложения (проверить доступность физлицу без бизнес-верификации).
4. Google (testing mode) и GitHub (два приложения: loopback dev + prod) — к соответствующим шагам конвейера.
5. Токен IPinfo Lite (бесплатный аккаунт) для скачивания MMDB.

Точные значения redirect_uri и чек-лист по каждой консоли — [research-provider-libs.md](research-provider-libs.md) § Схема dev/prod-окружений.

## Партиция треков

**T1 — Backend: OAuth-вертикаль + гео.** `backend/**` (модели, миграция, `infra/oauth/`, `infra/geoip.py`, `services/oauth.py`, роуты, `config.py`), env-файлы, `docker-compose.yml`. Порядок фаз: модель+миграция → абстракция+Яндекс (сквозная проверка на dev-приложении) → гео-gate → VK → Google → GitHub. Тесты: `backend/tests/auth/` — провайдер-слой на замоканном httpx (respx), сервис find-or-create (включая гонку unique violation), гео-gate (fallback, RU/не-RU), state-cookie (подпись, exp, mismatch).

**T2 — Frontend: вход страницей + каркас `/login`.** `frontend/src/**` (`app/router.tsx`, `App.tsx`, удаление `AuthGate`, `pages/login`, `shared/api`). Тесты: `router.test.tsx`, страница с MSW.

Общих файлов нет; общая точка — контракты этого брифа. Сквозной ручной прогон (реальный Яндекс-флоу end-to-end, гео-ветки через `GEOIP_FALLBACK_COUNTRY`) — после интеграции треков.

## Scope boundaries — сознательно вне итерации

- **Ручная линковка провайдеров** к существующему аккаунту (настройки) и **авто-склейка по email** — за скоупом v1; схема БД будущей линковке не мешает.
- **`users.email`** и любые email-фичи (верификация, нотификации).
- **Брендовый дизайн auth-экранов и 404** — feat-013 (контракт стыка — tasklist).
- **Telegram Login / Sber ID / ЕСИА** — возможные будущие провайдеры; абстракция расширяема, сейчас четыре.
- **Отвязка/удаление oauth-связки, смена пароля OAuth-пользователем** — вместе с линковкой.
- **Гео-детекция сверх IP** (Accept-Language, история) — перестраховка, не требуется.

## SOFA consulted

Ресёрч проведён (8 запросов: oauth authorization code flow, PKCE state, social login provider, fastapi oauth, geoip country detection, oauth callback redirect, yandex vk id, jwt refresh token). Прямо релевантных Blueprint/TIL по OAuth-флоу, PKCE и гео-gating нет — валидный пустой исход. Касательные: TIL `954f579d` (стейл-данные в JWT-claims при обновлении профиля) — перекликается с известным backlog-пунктом «JWT `is_admin` не освежается», на решения брифа не влияет; TIL `4c12ce92` (subresource-запросы не проходят Bearer-interceptor) — не про наш флоу (OAuth-редиректы — top-level навигация, аутентификация в них cookie-based by design).

## Ревью брифа

_Прогон свежим агентом по чек-листу conventions § Ревью дизайн-брифа — выполняется перед финализацией; находки и их разрешение фиксируются здесь._
