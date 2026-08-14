# Code Review Report — режим B (соответствие контракту)

Итерация: dogfooding feat-008 (OAuth-вход Яндекс/Google/GitHub + гео-разделение + каркас `/login`), ветка `dogf/feat-008-oauth-auth-screens`, base `develop`.
Проверено: `git diff develop...HEAD` (52e1733 T2, e195068 T1, 4bb1fa2 фикс логирования), `tracks/T{1,2}/{plan,summary}.md`, `design-brief.md`, `conventions.md` + `conventions/{db,api,frontend,testing}.md`, затронутые `doc/tech/**`.
Детерминированный слой (import-linter, AST-ассерты, eslint-boundaries, ruff/mypy/tsc/prettier) не перепроверялся — по вводным зелёный.

### Summary
- blocker: 1
- nit: 7
- pre-existing: 1

### Замечания

| Severity | Намерение | Файл:строка | Норма (ссылка) | Замечание | Предложение |
|---|---|---|---|---|---|
| blocker | Ветка «отказ провайдера» на callback'е | `backend/app/api/routes/oauth.py:244-247` | conventions.md § Обработка ошибок → Восстановление («graceful degradation — fallback + **наблюдаемый** лог»; «Молчаливая деградация запрещена»); § Барьерный стек («`except`, который глотает без логирования и решения, — антипаттерн»); design-brief.md § Эндпоинты, реестр кодов | Ветка ловит **любой** `?error=` провайдера и (а) не пишет в лог ни строки, (б) сводит всё к коду `access_denied`. Реестр брифа резервирует `access_denied` строго за «пользователь отказал на экране провайдера», а `server_error`/`temporarily_unavailable` — это ровно категория `provider_unavailable` («5xx/невалидный ответ провайдера»). Практическое следствие: прод-мисконфиг (`invalid_client`, `redirect_uri_mismatch`, отозванный secret) отдаёт пользователю «Вход отменён», а в stdout/`app.log`/SIEM не оставляет **ничего** — операционно слепая зона на критпути auth. Расхождение не зафиксировано ни в `## Решения и обоснования`, ни тестами (`test_callback.py` прогоняет только `error=access_denied`) — то есть незамеченное, а не принятое. | Разделить: `error == "access_denied"` → как сейчас (тихо, не событие — по брифу); любое другое значение → `logger.warning("oauth provider returned error", provider=..., error=<код провайдера>)` и редирект на `provider_unavailable` (уже существующий код закрытого реестра, новых кодов не нужно). Ветка остаётся до сверки state, порядок диаграммы не меняется. **✅ применено** ровно по предложению (см. tracks/T1/summary.md; тестовый кейс на новую ветку — за test-author). |
| nit | Уровень лога на retry/деградации find-or-create | `backend/app/services/oauth.py:145`, `:152` | conventions.md § Logging → Семантика уровней: WARNING — «система справилась, но что-то было не так: fallback сработал, **retry**, деградация» | «oauth user name collision, retrying with suffix» и «oauth account race detected on create, degrading to lookup» — буквально retry и деградация, но пишутся `logger.info`. Соседний `logger.warning` на исчерпанном бюджете попыток (`:162`) уровень держит верно, внутри одного файла шкала разъезжается. | Поднять оба до `logger.warning`. **✅ применено** (см. tracks/T1/summary.md). |
| nit | Единственный источник списка провайдеров | `backend/app/models/oauth_account.py:23` | conventions.md § Code Quality (ruff ловит мёртвый код; module-level константа под правило не попадает); db.md § Схема БД («Enum-подобные строки … CHECK-constraint») | `OAUTH_PROVIDERS = ("yandex", "google", "github")` не используется нигде (grep по репо — одна строка определения), при этом `CheckConstraint` рядом повторяет тот же состав строковым литералом. Мёртвая константа, которая читается как источник правды, но им не является — при добавлении четвёртого провайдера обновят одно из двух. | Либо удалить константу, либо собрать CHECK из неё (`f"provider IN ({', '.join(...)})"`) — тогда состав живёт в одном месте. **✅ применено** (см. tracks/T1/summary.md). |
| nit | Доккомментарии, разошедшиеся с кодом | `backend/app/api/schemas/oauth.py:9`; `backend/app/infra/oauth/base.py:26`; `frontend/src/pages/login/ui/LoginScreenView.tsx:28`; `frontend/src/pages/login/ui/LoginPage.tsx:44` | CLAUDE.md § Документация («без временных метапометок»; «исправляй дрейф на месте») | Докстринги фиксируют состояние промежуточных фаз трека и теперь неверны: `ProvidersResponse` утверждает «гео-фильтрация подключается в T1.7 — на этой фазе состав равен активным провайдерам **без геоограничений**» (гео-фильтр реализован и работает); `OAuthProvider` — «реализации (`yandex.py`, and later `google.py`/`github.py`)» (оба существуют); `providersSlot` — «наполняется в T2.4, здесь только слот» (наполнен); `LoginPage` — «блок кнопок … обработка `?error=` — T2.4» (всё в этом же файле). Читатель после merge номеров фаз не знает, а утверждения читает как факт. | Переписать в настоящем времени, без ссылок на фазы. (Сами по себе T-ссылки в комментариях — пре-существующий паттерн репо, см. ниже; чинить нужно те, что стали ложными.) **✅ применено** — все четыре докстринга переписаны (см. tracks/T1/summary.md, tracks/T2/summary.md). |
| nit | Env-контур: форма записи в `.env.local.example` | `.env.local.example:12-15` | conventions.md § Docker → Конфигурация через env-файлы (`.env.local` — «только переопределения для local dev»; atomic change четырёх мест) | Шесть credential-переменных перечислены прозаическим списком внутри комментария, а не в принятой этим файлом форме `# KEY=value` (как рядом `# CLIENT_IP_SOURCE=socket`, `# GEOIP_DB_PATH=...`). Именно креды — канонический случай local-dev-переопределения, разработчик копирует строки, а не разбирает список имён. Отступление зафиксировано в `## Решения и обоснования` T1 (мотив — grep-проверяемость), но цена — файл теряет свойство «раскомментируй нужное». | Привести к стилю файла: шесть строк `# OAUTH_*_CLIENT_ID=` / `# OAUTH_*_CLIENT_SECRET=`. Grep-проверяемость при этом только улучшается. **✅ применено** (см. tracks/T1/summary.md). |
| nit | Гео-база в docker-топологии | `docker-compose.yml:70,103` | conventions.md § Docker → Конфигурация через env-файлы; design-brief.md § Гео-gate (fail-closed) | Mount `./data/geoip:/app/data/geoip:ro` добавлен, но `GEOIP_DB_PATH` и в compose, и в `.env.example` пуст → в docker-режиме reader не открывается никогда, каждый lookup уходит в фолбэк `RU`. Деградация безопасная и логируется warning'ом, но mount при этом мёртвый, а «почему у нас все страны RU» выясняется по логу, а не по конфигу. | Поставить в `.env.example` путь, совпадающий с mount'ом (`GEOIP_DB_PATH=/app/data/geoip/ipinfo_lite.mmdb`) — тогда docker-топология самосогласована, а отсутствие файла даёт тот же fail-closed с явным warning'ом. **✅ применено** ровно по предложению (см. tracks/T1/summary.md). |
| nit | Форма ответа `GET /api/auth/providers` | `backend/app/api/schemas/oauth.py:12-14` | conventions/api.md § Pagination и list envelope («Envelope списочных ответов един для **всех** list-эндпоинтов, включая маленькие фиксированные списки») | Ответ `{providers: [...], password: true}` — не list-envelope. Расхождение выглядит оправданным (это дескриптор способов входа, а не коллекция ресурсов; поле `password` в envelope не ложится) и зафиксировано брифом § Контракты, утверждённым архитектором, — но в api.md прецедента «capability-дескриптор — не list-эндпоинт» нет, и следующий читатель прочтёт это как дрейф. | Не менять код. Внести в api.md одну строку-исключение (кандидат в harvest) — либо явно отнести к уже существующему исключению «`/auth/*` — RPC-семантика». **⏭ отложено** — вне мандата фикс-прохода (санкционировано брифом, правка документации — DOC_UPDATE). |
| nit | Зависимость route → route | `backend/app/api/routes/oauth.py:15` | conventions.md § Интерфейсы / § Барьерный стек (протечка ответственности между модулями одного слоя) | `from app.api.routes.auth import _set_refresh_cookie` — импорт приватного имени соседнего роутера. Вариант санкционирован планом T1.6 («переиспользовать импортом либо поднять в общий модуль»), ruff его не ловит; но связка «два роутера, один владеет приватным хелпером другого» — это то, что при следующей правке `routes/auth.py` ломается молча. | Оставить как есть допустимо; при первом же поводе тронуть `routes/auth.py` — вынести в `app/api/cookies.py` (или `deps.py`) как публичную функцию. **✅ применено** ровно по предложению — новый `app/api/cookies.py` (см. tracks/T1/summary.md). |
| pre-existing | Метки фаз треков в комментариях кода | `backend/app/agent/subagents/runner.py`, `app/agent/tools/registry.py`, `frontend/src/pages/chat/ui/ChatView.tsx` и др. (feat-011, чат-итерации) | CLAUDE.md § Документация («никаких маркеров итераций и истории») | Ссылки вида «(T1.3)», «(T2.6)» в докстринг ах — устоявшийся паттерн репозитория до этой итерации; feat-008 его наследует (`exceptions.py:11`, `services/exceptions.py:158`, `services/oauth.py:88`, `github.py:29`, `RequireAuth.tsx:13`). Сами по себе они не ложны, поэтому не чиню в рамках итерации. | Кандидат в harvest: решить, распространяется ли запрет метапометок на комментарии кода, и либо зафиксировать исключение в conventions.md, либо завести разовую чистку. |

### Blocker без прецедента в conventions

Нет. Единственный blocker опирается на прямую норму conventions.md § Восстановление и на реестр кодов из design-brief.md — эскалация архитектору не требуется, правка укладывается в существующий закрытый реестр ошибок (новых кодов не заводится).

### Проверенные и **не** ставшие находками места

Фиксирую явно, чтобы не перепроверялось на следующем круге:

- **Открытый редирект через `next`.** `is_safe_next_path` — денилист (`не начинается с //`), и форма `/\evil.example` его проходит. Открытым редиректом это не становится: Starlette `RedirectResponse` квотирует URL, backslash уезжает в `%5C` (проверено прямым вызовом), браузер authority из него не соберёт. Тест-автор запинил и сам обход (`test_flow_state.py:58-68`), и итоговое свойство на `Location` в `test_callback.py`. `next` попадает в подписанный `JWT_SECRET`-ом claim, подделка исключена.
- **Границы партиции соблюдены.** `shared/api/client.ts` — ноль изменений; `features/auth/**` и `shared/ui/{AuthLayout,ProviderButton}.tsx` не созданы; catch-all `path="*"` в `router.tsx` не появился; `Makefile`, `doc/tech/**` не тронуты. Весь UI каркаса — локальные компоненты `pages/login/**`.
- **Исключённое брифом не сделано:** авто-линковки по email нет, `users.email` не заведено, `vk` не в CHECK-constraint и не в реестре, реактивного mid-session-редиректа нет, нового auth-стора нет (`RequireAuth` читает токен синхронно, как раньше `AuthGate`).
- **Слои и состояние.** `infra/oauth` (Protocol + три реализации + фабрика реестра), `infra/geoip` (свободные функции), `services/oauth`, `repositories/oauth_account` — ответственность не протекла: `infra/oauth/**` не ссылается на `services`/`api`; module-level state отсутствует, ресурсы (`httpx.AsyncClient`, MMDB reader, реестр) живут в `app.state` из lifespan и закрываются до `engine.dispose()` — паттерн existing-ресурсов соблюдён (api.md § Владение состоянием).
- **Транзакция find-or-create** — одна, retry через `begin_nested()` (SAVEPOINT), constraint различается по `exc.orig.diag.constraint_name` (psycopg3) — db.md § DB-сессии не нарушена, полного `rollback()` внешней транзакции нет.
- **SIEM.** Три новых типа добавлены двойным добавлением (константа + член `Literal`) + ре-экспорт в `__all__`; эмит-сайты несут `security_event`/`event_type`/`severity`; гео-отказ сознательно без этих полей (`logger.info`) — ровно маппинг брифа; `access_denied` события не порождает.
- **Тесты** (`backend/tests/oauth/**`, колокация на фронте) лежат по testing.md: свой скоуп-каталог, маркеры `unit`/`integration` расставлены (46/85), `ASGITransport`, `app.dependency_overrides`, `structlog.testing.capture_logs` вместо `caplog`, MSW-фабрика вместо ручных моков `fetch`. Чужие тест-файлы не правились и не удалялись — `router.test.tsx` только дополнен.
- **Миграция** `e7fac2fe3bdf` — autogenerate, руками не правлена, naming convention соблюдена, FK с `index=True` и явным `ondelete`, `Text`/`timestamptz`/`server_default=func.now()` — db.md § Схема БД.
- **Фикс 4bb1fa2** (`show_locals=False` у rich-трейсбеков) — точечный, закрывает утечку секретов `Settings` в человекочитаемые рендеры, JSON-формат не затронут; правка в одном месте инфраструктуры логирования, а не по эмит-сайтам.

### Незамеченный дрейф документации

Вход для фазы DOC_UPDATE. Всё перечисленное — расхождение **текущей** доки с кодом на HEAD; правок в `doc/tech/**` итерация пока не вносила.

**`doc/tech/auth.md`** (самый нагруженный):
- § AuthGate (строка 138) описывает удалённый компонент — заменяется описанием страницы `/login` + guard `RequireAuth` + app-уровневого бутстрапа.
- § Поток аутентификации на frontend / Axios interceptor (111-137) — не упоминает, что бутстрап-refresh идёт **мимо** `apiClient` прямым `fetch` (и почему: 401 анонима не должен писать `logger.error`).
- § API endpoints (155-166) — нет `GET /auth/providers`, `GET /auth/oauth/{provider}/authorize`, `GET /auth/oauth/{provider}/callback`.
- § Ограничение частоты запросов (83-96) — таблица без двух новых бюджетов (`oauth_authorize:{ip}`, `oauth_callback:{ip}`, 10/мин).
- § Конфигурация cookie (97-110) — нет cookie `oauth_flow` (httpOnly, Lax, `Path=/api/auth/oauth`, 600 с, JWT на `JWT_SECRET`).
- § Auth Scheme Overview / § Хеширование паролей — не отражено, что `password_hash` теперь nullable и что вход паролем в OAuth-аккаунт отдаёт тот же 401 без утечки способа входа.
- § Конфигурация (167+) — нет десяти новых env (`OAUTH_*` × 8, `GEOIP_DB_PATH`, `GEOIP_FALLBACK_COUNTRY`).
- Атрибуция IPinfo — бриф предписывает упоминание в `auth.md` (в README уже есть).
- Отсутствует описание закрытого реестра кодов `/login?error=` — контракт стыка backend↔frontend, сейчас живёт только в брифе.

**`doc/tech/backend.md`**:
- § Module Structure / **infra/** (445) — нет `infra/oauth/` (Protocol + три провайдера + фабрика реестра) и `infra/geoip.py`.
- § Module Structure / **services/** (433) и **repositories/** (439) — нет `OAuthService`, `OAuthAccountRepository`.
- § Layered Architecture, mermaid-диаграмма слоёв (24-60) — новые модули на схеме отсутствуют.
- § API Layer → Endpoints (189+) — нет OAuth-эндпоинтов.
- § Persistence → App-managed (497+) — в списке таблиц нет `OAuthAccount`; у `User` в списке полей `password_hash` без пометки nullable; § Связи (535) — нет `User 1 → N OAuthAccount`.
- § Logging → Setup (550) — уместно упомянуть `show_locals=False` как инвариант (почему rich-трейсбеки не печатают locals).

**`doc/tech/frontend.md`**:
- Строки 72, 354, 361, 424, 431-432 — `AuthGate` фигурирует и в описании, и в двух деревьях модулей, и на mermaid-диаграмме; компонент удалён.
- Дерево модулей — нет `pages/login/`, `app/components/RequireAuth.tsx`, нового сегмента `app/model/` (`useAuthBootstrap.ts`).
- Строка 287 (`auth.ts — register/login/refresh/getMe/logout`) — добавились `getAuthProviders`/`useAuthProviders` + DTO.
- Не описан вход как маршрут (публичный `/login`, guard на layout-группе, транспорт `from` → `next`) и порядок бутстрапа.

**`doc/tech/security-events.md`**:
- § Complete Event Type Catalog → Authentication Events (23-32) — нет `auth.oauth.success` / `auth.oauth.failed`; Rate Limit Events (34+) — нет `rate_limit.oauth.exceeded`.
- § Event-Specific Metadata (119-126) — нет строк по метаданным новых событий (`provider`, `new_user` у success; `provider`, `reason` у failed; `key`/`limit`/`window` у rate-limit).

**`doc/security/architecture.md`** — здесь есть **противоречие вводных**: бриф предписывает внести «новую поверхность: OAuth-callback, гео-gate», а сам документ во вводном абзаце (строка 7) явно выводит auth/rate limiting/RBAC за свой скоуп («обычная app-security, а не предмет этого документа»). Решение — за архитектором: либо OAuth-поверхность описывается в `auth.md` (консистентно с текущим скоупом документа), либо скоуп `security/architecture.md` расширяется явно. Молча дописать раздел в документ, который сам себя ограничивает, нельзя.

**ADR** — бриф фиксирует новый ADR по identity model (отдельная таблица связок, запрет авто-линковки, nullable-пароль). В `doc/tech/adr/` его нет.

**`doc/tech/conventions/api.md`** — кандидат на одну строку про capability-дескриптор вне list-envelope (см. nit выше); не блокирует DOC_UPDATE, идёт через harvest/архитектора.
