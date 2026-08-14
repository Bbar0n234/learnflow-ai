# Implementation Plan: feat-008 / трек T1 — Backend: OAuth-вертикаль, гео-gate, SIEM-словарь

## Контекст

Трек добавляет на бэкенде вход через внешних провайдеров (Яндекс ID, Google, GitHub) и серверное гео-разделение их доступности. OAuth заканчивается в момент надёжного получения `(provider, provider_account_id)`; дальше без изменений работает существующая сессионная машина (`AuthService`, ротация refresh, replay-детекция). Фронтенд (`/login`, guard, бутстрап) — трек T2, файлового пересечения нет; стык — контракт `GET /api/auth/providers` и закрытый реестр кодов `/login?error=`.

Источники:

- Запись итерации — [tasklist-dogfooding.md](../../../../../tasklist-dogfooding.md) § «feat-008 (I): OAuth + auth-экраны + 404»
- [design-brief.md](../../design-brief.md) — архитектура, контракты, коды ошибок, env-таблица, § «Партиция треков» (границы T1)
- Ресёрч: [research-data-model.md](../../research-data-model.md) (DDL, таблица решений), [research-legal-geo.md](../../research-legal-geo.md) (юр. рамка, выбор гео-стека), [research-provider-libs.md](../../research-provider-libs.md) (ручной httpx-слой, специфика провайдеров)
- Архитектура: [auth.md](../../../../../../tech/auth.md), [backend.md](../../../../../../tech/backend.md) § Layered Architecture / Правила вызовов, [conventions/db.md](../../../../../../tech/conventions/db.md), [conventions/api.md](../../../../../../tech/conventions/api.md), [conventions.md](../../../../../../tech/conventions.md) §§ Обработка ошибок, Logging, Docker/env, [ADR-011](../../../../../../tech/adr/ADR-011-auth-architecture.md)

Порядок фаз следует рамочному решению архитектора (бриф § Порядок реализации): модель+миграция → абстракция+Яндекс (сквозная проверка) → гео-gate → Google → GitHub. Промежуточное состояние `/api/auth/providers` без гео (после T1.6, до T1.7) — следствие этого порядка, не контракт: наружу трек отдаёт гео-версию.

Верификация опирается на критерии приёмки брифа; автотесты по треку пишет независимый `test-author` — фазы их не создают. `make check` в каждой фазе — ruff + mypy + arch-check (import-linter).

Проверено при планировании (не повторять ресёрч): `maxminddb` в окружении **отсутствует**, актуальная версия 3.1.1 (requires-python ≥3.10), в колесе есть `py.typed` → `[[tool.mypy.overrides]]` в корневом `pyproject.toml` **не нужен**. API: `maxminddb.open_database(path) -> Reader`, `Reader.get(ip: str | IPv4Address | IPv6Address) -> Record | None`, `Reader.close()`; на нераспарсиваемой строке (`"unknown"` из `get_client_ip`) `ip_address()` внутри поднимает `ValueError` — это обязательная ветка обработки.

## Фазы

### T1.1: Модель данных — `oauth_accounts`, nullable `password_hash`, миграция

**Цель:** схема БД и ORM-модели готовы принять OAuth-связки, парольный вход при отсутствующем пароле отклоняется тем же 401.

**Изменения:**

- `backend/app/models/oauth_account.py` — новая `OAuthAccount` по DDL-эскизу research-data-model § Итоговый DDL (UUID PK, FK `user_id` с `ondelete=CASCADE` + `index=True`, `provider`/`provider_account_id` Text, nullable `email`, `created_at`/`updated_at`, `UniqueConstraint(provider, provider_account_id)`). CHECK-constraint — по фактическому составу `('yandex', 'google', 'github')`, без `vk` (отступление от эскиза зафиксировано брифом § Модель данных).
- `backend/app/models/user.py` — `password_hash` → `Mapped[str | None]` (nullable), relationship `oauth_accounts` (`cascade="all, delete-orphan"`).
- `backend/app/models/__init__.py` — экспорт новой модели (иначе autogenerate её не увидит).
- `backend/app/services/auth.py` — `login`: `password_hash IS NULL` даёт `InvalidCredentialsError` (тот же 401, без утечки способа входа аккаунта); заодно снимается несовместимость типов `verify_password(str, ...)` с nullable-полем. *Примечание к скоупу:* партиция называет это изменение как правку `app/api/routes/auth.py`; фактическое место — сервисный слой (транспорт трогать не нужно), оба файла внутри `backend/**` и вне скоупа T2, конфликта не создаёт.
- `backend/alembic/versions/<rev>_oauth_accounts.py` — одна autogenerate-ревизия против запущенной БД: `make docker-up-db` → `make migrate` → правка моделей → `make migration msg="oauth accounts"` → прочитать сгенерированный файл. Руками миграция не пишется (conventions/db.md § Database migrations).

**Verification:**

- `make check` проходит.
- Миграция применяется на чистой БД: `docker compose down -v` → `make docker-up-db` → `make migrate` без ошибок; в БД есть `oauth_accounts` с `uq_`/`ix_`/`ck_`-именами из naming convention, `users.password_hash` — nullable.
- `make test-scope P=backend/tests/migrations` — drift-гвард зелёный (модели ↔ миграции без расхождений).
- `make test-scope P=backend/tests/auth` — существующие парольные сценарии не сломаны.
- Критерий брифа: логин по паролю пользователем с `password_hash IS NULL` → 401 «Invalid credentials», не 500.

### T1.2: Конфигурация провайдеров (env-контур)

**Цель:** креды трёх провайдеров и база redirect_uri читаются через `Settings`; провайдер без кредов считается выключенным.

**Изменения:**

- `backend/app/config.py` — восемь полей: семь из брифовой env-таблицы — `oauth_yandex_client_id/secret`, `oauth_google_client_id/secret`, `oauth_github_client_id/secret` (default `""`), `oauth_redirect_base_url` (default `http://localhost:5173`) — плюс `oauth_http_timeout_seconds` (default `10`) по резолюции архитектора (Open Questions № 1): таймаут httpx-вызовов к провайдерам как операционная ручка. Дефолт `""` — сознательно не fail-fast-секрет: пустое значение выключает провайдера (бриф § Конфигурация).
- `.env.example`, `.env.local.example`, `docker-compose.yml` (блок `app.environment`, по одной переменной, `${VAR:-default}`) — atomic change четырёх мест вместе с `Settings` (conventions.md § Что попадает в env). Для `OAUTH_REDIRECT_BASE_URL` дефолты в compose и в `Settings` **различаются** (резолюция Open Questions № 2): в `docker-compose.yml` — `${OAUTH_REDIRECT_BASE_URL:-http://localhost:8000}` (в docker-топологии SPA отдаёт backend), в `Settings` остаётся `http://localhost:5173` (local dev через Vite). Это не рассинхрон, а «своё окружение — свой host флоу»; инвариант единого host'а внутри окружения соблюдён. В `.env.local.example` — комментарий, что реальные пары client_id/secret лежат в локальном `.env.local` и в репозиторий не едут.

**Verification:**

- `make check` проходит.
- `docker compose config` рендерится без ошибок, новые переменные видны в окружении сервиса `app`.
- `Settings()` без переменных в окружении даёт пустые креды и брифовый дефолт `OAUTH_REDIRECT_BASE_URL` (проверяется запуском приложения: `make dev` стартует).
- Дефолты `OAUTH_REDIRECT_BASE_URL` разведены как решено: в `docker-compose.yml` — `http://localhost:8000`, в `Settings` — `http://localhost:5173` (grep по обоим местам).
- Все восемь переменных (включая `OAUTH_HTTP_TIMEOUT_SECONDS`) присутствуют одновременно в `Settings`, `.env.example`, `.env.local.example`, `docker-compose.yml` (grep-сверка).

### T1.3: SIEM-словарь — новые event types

**Цель:** закрытый словарь `packages/siem-contracts` расширен типами OAuth-входа и rate-limit'а oauth-эндпоинтов, чтобы эмит-сайты последующих фаз были типово легальны.

**Изменения:**

- `packages/siem-contracts/siem_contracts/vocabulary.py` — три новых типа (состав зафиксирован брифом § Эндпоинты, имена выравниваются по существующему стилю `<domain>.<subject>.<outcome>`, минимум три сегмента, lowercase): успех входа через провайдера, отказ входа через провайдера, превышение rate limit на oauth-эндпоинтах. Существующие `RATE_LIMIT_LOGIN/REGISTER/REFRESH` не переиспользуются — другие эндпоинты. Каждый тип добавляется **дважды**: константа + член `Literal EventType`.
- `packages/siem-contracts/siem_contracts/__init__.py` — импорт + `__all__` (гварды пакета требуют re-export каждой константы).

**Verification:**

- `make check` проходит.
- `make test-contracts` — гварды словаря зелёные (Literal ↔ константы ↔ `__all__` в lockstep, нейминг проходит регекс `^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){2,}$`, дубликатов нет).
- `make test-scope P=backend/tests/security/test_event_vocabulary_contract.py` — двусторонняя полнота producer ↔ vocabulary не сломана (на этой фазе эмит-сайтов ещё нет, тест обязан остаться зелёным).

### T1.4: Провайдер-абстракция + Яндекс + ресурсы lifespan

**Цель:** есть тонкий httpx-слой провайдеров с рабочей реализацией Яндекс ID и реестр активных провайдеров в `app.state`.

**Изменения:**

- `backend/app/infra/oauth/base.py` — `OAuthProvider` как `typing.Protocol` (`authorize_url(state, challenge, redirect_uri)` / `exchange_code(code, verifier, redirect_uri)` / `fetch_profile(token)`), нормализованный результат `OAuthProfile` (`provider`, `provider_account_id`, `email: str | None`, `display_name: str | None`) — frozen dataclass (внутренний value-объект, conventions.md § Типизация).
- `backend/app/infra/oauth/pkce.py` (или эквивалентный модуль рядом) — генерация `state` (`secrets.token_urlsafe(32)`), `code_verifier` (`secrets.token_urlsafe(64)`), `code_challenge = base64url(sha256(verifier))`, S256. Чистые функции без состояния.
- `backend/app/infra/oauth/yandex.py` — обычный code flow: `https://oauth.yandex.ru/authorize`, `POST https://oauth.yandex.ru/token`, профиль `GET https://login.yandex.ru/info` с заголовком `Authorization: OAuth <token>`, маппинг `id`/`login`/`default_email` → `OAuthProfile` (research-provider-libs § Яндекс ID).
- `backend/app/infra/oauth/__init__.py` — сборка реестра активных провайдеров из `Settings` (активен ⇔ заданы обе креды) без module-level state: фабрика вызывается из lifespan.
- `backend/app/main.py` (lifespan) — shared `httpx.AsyncClient` в `app.state` (общий пул) с таймаутом из `OAUTH_HTTP_TIMEOUT_SECONDS` (поле `Settings`, заведено в T1.2 — хардкод таймаута не заводится), реестр провайдеров в `app.state`, закрытие клиента на shutdown **до** `engine.dispose()` (паттерн существующих ресурсов). Клиент per-request не создаётся.
- Ошибки провайдера (5xx, таймаут, невалидный ответ) — узкое доменное исключение, живущее рядом с oauth-подсистемой; HTTP-семантики не несёт, наружу графа не летит (conventions.md § Модель ошибок, второй уровень нормы — прецедент `AuthError`).

**Verification:**

- `make check` проходит (в т.ч. import-linter: `infra` не тянет `services`/`api`).
- Приложение стартует с заполненными кредами Яндекса из `.env.local` и логирует состав активного реестра; стартует и с пустыми кредами (реестр пуст, ошибки старта нет).
- `authorize_url` Яндекса содержит `response_type=code`, `client_id`, `redirect_uri`, `state`, `code_challenge` + `code_challenge_method=S256`.
- Реестр и httpx-клиент живут в `app.state`, module-level синглтонов нет (grep).

### T1.5: `OAuthService` — find-or-create и выдача сессии

**Цель:** по нормализованному `OAuthProfile` в одной транзакции находится или создаётся пользователь и его связка, дальше выдаётся штатная пара токенов.

**Изменения:**

- `backend/app/repositories/oauth_account.py` — lookup по `(provider, provider_account_id)`, create; ORM-CRUD без бизнес-логики.
- `backend/app/services/oauth.py` — `login_with_provider(profile) -> (user, access, refresh)`: lookup связки → найдена: пользователь + освежение `email`; не найдена: создание `User` (без пароля) + `OAuthAccount` атомарно. Оба constraint-пути обрабатываются **явно** (бриф § Эндпоинты): unique violation на `users.name` → суффикс к имени и retry с ограничением попыток (кандидат имени и нормализация — research-data-model § Генерация `users.name`); unique violation на `(provider, provider_account_id)` (гонка двойного callback'а) → деградация в повторный lookup, login-путь, не 500. Гонки решаются constraint'ом, не «SELECT, потом INSERT» (conventions/db.md § Схема БД).
- `backend/app/services/auth.py` — механика `_create_access` / `_create_refresh` **переиспользуется, не копируется** (бриф): доступ к ней оформляется явным методом `AuthService` (выдача сессии по пользователю), которым дальше пользуются оба сервиса; обращение к приватным членам чужого класса — не вариант.
- Инвариант «пароль ИЛИ oauth-связка» держит сервисный слой: создание пользователя и связки — одна транзакция.

**Verification:**

- `make check` проходит (import-linter: `services` не импортирует `fastapi` и не ходит вверх по слоям).
- `make test-scope P=backend/tests/auth` — регрессия по существующему парольному пути отсутствует после выделения метода выдачи сессии.
- Критерии брифа, проверяемые на этой фазе кодом (автотесты — за `test-author`): повторный вход тем же провайдер-аккаунтом не создаёт второго пользователя; коллизия `users.name` разрешается суффиксом; коллизия связки не даёт 500.

### T1.6: Эндпоинты OAuth — cookie `oauth_flow`, authorize, callback, `/providers`

**Цель:** сквозной рабочий вход через Яндекс: браузер уходит на провайдера и возвращается аутентифицированным, ошибки редиректят на `/login` с кодом из закрытого реестра.

**Изменения:**

- `backend/app/infra/oauth/flow_state.py` (или эквивалент рядом с провайдерами) — JWT-механика cookie `oauth_flow` на существующем `JWT_SECRET` (pyjwt уже в зависимостях): выпуск claims `{state, verifier, provider, next, exp: +10 мин}`, декод с валидацией подписи/exp/совпадения `provider`; валидация `next` (относительный путь: начинается с `/`, не с `//`) **до** записи в claim. Вынос вспомогательной механики из route-модуля — заодно держит его в пределах size-чека (conventions.md § Size-чек).
- `backend/app/api/schemas/oauth.py` — Pydantic-схема ответа `/providers` (`{providers: string[], password: bool}`, `password` в v1 всегда `true`).
- `backend/app/api/routes/oauth.py` — новый роутер:
  - `GET /auth/providers` — на этой фазе состав = активные провайдеры реестра (гео добавляется в T1.7);
  - `GET /auth/oauth/{provider}/authorize?next=<path>` — `{provider}` валидируется по реестру активных (неизвестный/выключенный → 404), rate limit 10/мин/IP через существующий `RateLimiter` + `get_client_ip`, генерация state/PKCE, `Set-Cookie: oauth_flow` (httpOnly, `SameSite=Lax`, `Secure` по `SECURE_COOKIES`, `Path=/api/auth/oauth`, `max_age=600`), 302 на провайдера;
  - `GET /auth/oauth/{provider}/callback` — после общих гейтов (валидация `{provider}`, rate limit — два пункта ниже) ветки идут строго в порядке диаграммы брифа § Эндпоинты: `?error` провайдера → cookie/state → (гео — с T1.7) → обмен кода → профиль → find-or-create → refresh-cookie → 302 на `/{next}` (default `/`). Cookie `oauth_flow` гасится на **каждой** терминальной ветке, кроме «cookie отсутствует». Redirect-коды — только из закрытой таблицы брифа (`access_denied`, `flow_expired`, `provider_not_available_in_region`, `provider_unavailable`, `oauth_failed`); открытых редиректов нет.
  - **Валидация `{provider}` по реестру — на обоих эндпоинтах** (бриф § Эндпоинты, утверждение под таблицей): неизвестный или выключенный провайдер → 404, проверка идёт **до всех остальных веток** — в callback'е в том числе до разбора `?error` (обращение к несуществующему провайдеру не должно превращаться в редирект на `/login`).
  - **Rate limit callback'а — 10/мин/IP** (та же строка таблицы брифа, ребро CB → RL на диаграмме компонентов), тем же существующим `RateLimiter` + `get_client_ip`, что у authorize. **Ключи лимитера раздельные: `oauth_authorize:{ip}` и `oauth_callback:{ip}`** — бриф даёт `10/мин/IP` отдельной строкой на каждый эндпоинт (бюджет побюджетно), а общий ключ резал бы бюджет вдвое (один вход = authorize + callback) и делал бы недетерминированным критерий verification «11-й запрос callback за минуту → 429». При превышении на callback'е эмитится тот же SIEM-тип rate-limit'а из T1.3, что и на authorize. Позиция проверки в цепочке — по порядку брифа: сразу после валидации `{provider}` и **до** ветки `?error` провайдера (лимит стоит до разбора `?error` и обмена кода). Ответ на превышение — штатный JSON 429 с `Retry-After` (сознательное решение брифа: redirect-путь для 429 не строится). 404 и 429 — не терминальные ветки диаграммы callback'а: cookie `oauth_flow` на них не гасится, флоу остаётся валидным до своего `exp` (гасить её здесь значило бы дать одним лишним запросом ломать чужой начатый вход).
  - **Сборка redirect_uri** (бриф § Конфигурация) — строго `{OAUTH_REDIRECT_BASE_URL}/api/auth/oauth/{provider}/callback`, одинаково в authorize и в обмене кода на callback'е (провайдеры сверяют совпадение). Значение берётся только из настройки, host не подменяется ни из `Request.url`, ни из `Host`/`X-Forwarded-Host` — инвариант host'а брифа (весь флоу и SPA-origin на одном host).
  - refresh-cookie ставится **существующей** механикой из `routes/auth.py` (общий helper — переиспользовать импортом либо поднять в общий модуль; дублировать атрибуты cookie нельзя).
- `backend/app/main.py` — регистрация роутера с префиксом `/api`.
- SIEM-эмиссия по маппингу брифа: успех входа (поля `provider`, `new_user: bool`), отказ — только ветки `flow_expired` и `oauth_failed`; `provider_unavailable` — `logger.warning` без SIEM; `access_denied` и гео-отказ — не security-события. Rate-limit-событие — новый тип из T1.3, и **эмитится оно в самом `routes/oauth.py`** формой, которую резолвер контракт-теста (`backend/tests/security/test_event_vocabulary_contract.py`, `_resolve_parameter`) видит в этом же модуле: либо локальный guard-хелпер в `routes/oauth.py` с вызовами рядом (проброс константы через параметр резолвится только внутри модуля), либо `logger.warning(..., event_type=<импортированная константа>)` прямо на месте проверки. Форма не оставляется на усмотрение реализации: вынос хелпера в общий модуль делает параметр нерезолвимым (тест красный), а импорт приватного `_check_rate_limit` из `routes/auth.py` даёт слепое пятно — константа не попадает в набор emitted.

**Verification:**

- `make check` проходит (import-linter: `api/routes` не импортирует `repositories`/`storage`/`agent` напрямую).
- `make test-scope P=backend/tests/security/test_event_vocabulary_contract.py` — зелёный: новые эмит-сайты обязаны использовать формы, которые резолвер теста понимает (импортированная константа, локальный `A if cond else B`, один уровень проброса через параметр-хелпер); незнакомая форма красит тест намеренно.
- Ручной сквозной прогон на dev-приложении Яндекса (весь флоу через Vite-proxy, host `localhost`): вход первым разом создаёт пользователя и связку, `POST /api/auth/refresh` отдаёт access, повторный вход логинит того же пользователя, `next` возвращает на исходный путь.
- Ветки ошибок наблюдаемы: отказ на экране провайдера → `/login?error=access_denied`; повторный заход на callback / протухшая cookie → `flow_expired`; 11-й запрос `authorize` за минуту → 429 с `Retry-After`.
- Rate limit закрывает **оба** эндпоинта: 11-й запрос `callback` за минуту с того же IP → 429 с `Retry-After` (не редирект на `/login`), в SIEM видно rate-limit-событие.
- Неизвестный/выключенный провайдер даёт 404 на **обоих** эндпоинтах: `GET /api/auth/oauth/nosuch/authorize` и `GET /api/auth/oauth/nosuch/callback?error=access_denied` — 404, а не редирект.
- redirect_uri, уходящий провайдеру в authorize и в обмене кода, совпадает буква-в-букву и равен `{OAUTH_REDIRECT_BASE_URL}/api/auth/oauth/{provider}/callback` (проверяется по Location authorize-ответа; заголовок `Host` на значение не влияет).
- Access token нигде не появляется в redirect-URL (проверяется по Location-заголовкам ответа callback'а).

### T1.7: Гео-gate — MMDB-reader и enforcement в трёх точках

**Цель:** состав провайдеров и допустимость флоу определяются страной клиентского IP; РФ получает только российского провайдера (+ пароль), деградация — fail-closed в сторону закона.

**Изменения:**

- Зависимость: `uv add maxminddb` в пакете `backend` → регенерация корневого `uv.lock`. Override в `[[tool.mypy.overrides]]` не нужен — пакет ships `py.typed` (проверено на 3.1.1).
- `backend/app/infra/geoip.py` — открытие reader'а (`maxminddb.open_database`) и резолв страны: чтение записи через `Reader.get(ip)` с извлечением country-кода, совместимым и с плоской структурой IPinfo Lite, и с вложенной GeoLite2 (`Record` — рекурсивный union, навигация с явными isinstance-проверками). Fallback-страна применяется при: несконфигурированной/отсутствующей базе, промахе lookup'а (приватные адреса dev), **и `ValueError` от неразбираемой строки IP** (`get_client_ip` возвращает `"unknown"`, когда клиента нет). IP — строго через существующий `app.infra.client_ip.get_client_ip`, свои чтения proxy-заголовков запрещены.
- `backend/app/config.py` + `.env.example` + `.env.local.example` + `docker-compose.yml` — `GEOIP_DB_PATH` (default `""`), `GEOIP_FALLBACK_COUNTRY` (default `RU`); в compose дополнительно read-only mount `./data/geoip`. В `.env.local.example` — путь-образец с комментарием (реальный абсолютный путь живёт в локальном `.env.local`; файл базы в worktree отсутствует и **не скачивается заново**).
- `backend/app/main.py` (lifespan) — reader в `app.state` (mmap), graceful-деградация при отсутствии файла (warning + `None`, старт не блокируется), `close()` на shutdown рядом с остальными ресурсами.
- Бизнес-инвариант «разрешённые для РФ провайдеры» = `{"yandex"}` — константа в коде, не env (бриф § Конфигурация).
- Enforcement в трёх точках (`backend/app/api/routes/oauth.py`): `/providers` — RU → `{yandex} ∩ активные` (при незаполненных кредах Яндекса RU-пользователь получает только пароль, кнопки в 404 быть не должно), иначе все активные; `authorize` и `callback` — запрещённый для RU-IP провайдер → 302 `/login?error=provider_not_available_in_region` (проверка в callback обязательна: смена IP между шагами и прямое обращение мимо UI). Гео-отказ — structlog-инфо, не SIEM.
- `README.md` — атрибуция IPinfo (CC BY-SA), как решено брифом § Гео-gate.

**Verification:**

- `make check` проходит; `uv.lock` содержит `maxminddb`, `make check`/`make test` не требуют новых mypy-подавлений.
- Дефолтный fallback (`RU`, база не подхвачена): `GET /api/auth/providers` отдаёт только `yandex` (пересечённый с активными) и `password: true`; `authorize` на Google/GitHub с того же IP → 302 на `/login?error=provider_not_available_in_region`.
- `GEOIP_FALLBACK_COUNTRY=US`: `/providers` отдаёт все активные провайдеры, `authorize` любого из них проходит.
- С подключённой базой (`GEOIP_DB_PATH` на файл в основном checkout) приложение стартует, reader открывается, lookup не ломает запрос ни на приватном IP, ни на `"unknown"`.
- Отсутствующий файл базы: старт с warning, все запросы работают по fallback-стране (никакого 500).

### T1.8: Провайдер Google

**Цель:** Google встроен в готовую вертикаль как второй провайдер реестра.

**Изменения:**

- `backend/app/infra/oauth/google.py` — code flow (`accounts.google.com` authorize + token endpoint), scopes `openid email profile`, профиль через userinfo-endpoint по access token; JWKS-валидация `id_token` не требуется и не делается (бриф § Провайдер-слой). Маппинг `sub`/`email`/`given_name` → `OAuthProfile`.
- Регистрация в реестре активных провайдеров (креды из `Settings`, добавлены в T1.2).

**Verification:**

- `make check` проходит.
- С заполненными dev-кредами Google провайдер появляется в `/api/auth/providers` при не-РФ стране и отсутствует при РФ.
- Ручной сквозной прогон Google-флоу на dev-приложении (testing mode, redirect_uri `http://localhost:5173/api/auth/oauth/google/callback`): вход создаёт пользователя, повторный — логинит его же.
- Гео-ветка: `authorize` Google при `GEOIP_FALLBACK_COUNTRY=RU` → `provider_not_available_in_region`.

### T1.9: Провайдер GitHub

**Цель:** GitHub встроен как третий провайдер, включая добор email отдельным запросом.

**Изменения:**

- `backend/app/infra/oauth/github.py` — code flow (`github.com/login/oauth/*`), профиль `GET /user`; при `email: null` — добор через `GET /user/emails` со scope `user:email` (research-provider-libs § подводные камни). Маппинг `id`/`login` → `OAuthProfile`.
- Регистрация в реестре активных провайдеров.
- Инвариант host'а: dev-приложение GitHub зарегистрировано на `localhost` (не `127.0.0.1`) — ручной шаг уже выполнен архитектором, код ничего дополнительно не делает, но redirect_uri обязан собираться из `OAUTH_REDIRECT_BASE_URL` без подмены host'а (правило зафиксировано в T1.6).
- **PKCE у GitHub — no-op** (решение оркестратора, Open Questions № 3): GitHub OAuth Apps PKCE не поддерживают, `code_challenge`/`code_verifier` молча игнорируются. Единый интерфейс абстракции при этом не разветвляется: `authorize_url`/`exchange_code` принимают те же PKCE-параметры, реализация GitHub передаёт их провайдеру (или опускает — на её усмотрение), но на их проверку не рассчитывает. Безопасность ветки держит сверка `state` из cookie `oauth_flow` — она у GitHub такая же, как у остальных; отдельного отступления от общего флоу не заводится.

**Verification:**

- `make check` проходит.
- Ручной сквозной прогон GitHub-флоу на dev-приложении: вход создаёт пользователя; аккаунт со скрытым email даёт связку с `email = NULL` без ошибки (либо email добирается через `/user/emails`, если scope позволяет). Успешность обмена кода не ставится в зависимость от PKCE — критерий прохождения ветки — сверка `state` и полученный профиль.
- `/api/auth/providers` при не-РФ отдаёт все три провайдера; при РФ — только `yandex`.

## Cross-cutting

После всех фаз трека:

- `make check` и `make test` зелёные целиком (включая `packages/siem-contracts` гварды и двусторонний vocabulary-контракт бэкенда).
- Миграции применяются на **чистой** БД: `docker compose down -v` → `make docker-up-db` → `make migrate`; drift-тест `backend/tests/migrations` зелёный.
- Все десять env-переменных (девять из брифовой таблицы + `OAUTH_HTTP_TIMEOUT_SECONDS` по резолюции архитектора) присутствуют одновременно в `Settings`, `.env.example`, `.env.local.example`, `docker-compose.yml`; `docker compose config` рендерится, mount `./data/geoip` на месте.
- Реестр кодов `/login?error=` закрыт: ни одна ветка callback'а не редиректит с кодом вне таблицы брифа; cookie `oauth_flow` гасится на каждой терминальной ветке, кроме «cookie отсутствует». 404 (неизвестный провайдер) и 429 терминальными ветками не считаются — cookie на них не гасится (согласовано с T1.6).
- Access token не проходит через redirect-URL ни в одной ветке; SPA получает его существующим `POST /api/auth/refresh`.
- Гео-enforcement работает во всех трёх точках, в том числе при прямом обращении к callback мимо UI.
- Module-level state не заведён: httpx-клиент, geoip-reader и реестр провайдеров живут в `app.state`, закрываются в lifespan до `engine.dispose()`.
- Скоуп не расширен: изменения ограничены `backend/**`, `packages/siem-contracts/**`, env-файлами, `docker-compose.yml`, `README.md`, корневым `uv.lock`. `frontend/**`, `doc/**`, `Makefile` не трогались.
- Сквозной ручной прогон (реальный Яндекс-флоу end-to-end, гео-ветки через `GEOIP_FALLBACK_COUNTRY`) — на барьере после интеграции треков, не внутри T1.

## Open Questions

Открытых вопросов нет — все закрыты (№ 1–2 — решением архитектора по эскалации оркестратора, № 3 — решением оркестратора по итогам ревью плана, 2026-08-12):

1. **Таймаут HTTP-вызовов к провайдерам — РЕШЕНО: вариант (а).** Заводится десятая env-переменная `OAUTH_HTTP_TIMEOUT_SECONDS` (default 10) в `Settings` + atomic change 4 мест — по conventions.md § Таймауты (операционная ручка). Env-таблица брифа дополняется при DOC_UPDATE. Включить в фазу env-контура (T1.2).
2. **Дефолт `OAUTH_REDIRECT_BASE_URL` в `docker-compose.yml` — РЕШЕНО: `${OAUTH_REDIRECT_BASE_URL:-http://localhost:8000}`.** В docker-compose свой топологически верный дефолт :8000 (SPA там отдаёт backend); дефолт `Settings` остаётся `http://localhost:5173` для local dev. Каждое окружение — свой host флоу, инвариант брифа соблюдён.
3. **PKCE для GitHub — РЕШЕНО (оркестратор): единый интерфейс, PKCE как no-op.** GitHub OAuth Apps не поддерживают PKCE — `code_challenge`/`code_verifier` игнорируются провайдером. Абстракция не разветвляется: параметры проходят через общий интерфейс, реализация GitHub на них не опирается; защиту ветки от CSRF держит сверка `state` из cookie `oauth_flow`. Зафиксировано в фазе T1.9 (изменения + verification).
