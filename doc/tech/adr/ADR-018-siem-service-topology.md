# ADR-018: SIEM Service Topology

## Статус

Принято

## Контекст

Security 1.0 (feat-004) реализовал три слоя защиты от prompt injection. Все компоненты логируют инциденты через `structlog` и отправляют observability в Langfuse. События безопасности **не сохраняются** в БД, **не коррелируются** и **не отображаются** на админской панели.

feat-005 добавляет SIEM-подсистему: сбор, хранение, корреляцию security-событий и UI мониторинга. SIEM ортогонален security layers — producers (guard, auth, rate limiter) порождают события, SIEM их потребляет. Разделение реализовано на уровне ответственности: producer не знает о SIEM, SIEM не знает о конкретных producer'ах. Контракт событий — единственная точка соприкосновения.

Фундаментальный вопрос: **где живёт SIEM-код** — как модуль в main app или как отдельный сервис? Первоначальная рекомендация (session notes) — модуль в main app (`app/security_pipeline/`): нулевой ops overhead, shared connection pool, shared auth middleware. Архитектор отложил решение на этап проектирования. После анализа — выбран отдельный сервис.

## Решения

### 1. SIEM — отдельный backend-сервис (D1)

SIEM запускается как собственный FastAPI-процесс в собственном Docker-контейнере. Main app и SIEM-сервис — два процесса, связанных через Redis Streams (transport) и HTTP (username enrichment).

**Альтернатива: модуль в main app** (`app/siem/`)

- За: нулевой ops overhead — один контейнер, один compose-сервис, shared env; shared PostgreSQL connection pool; shared auth middleware (RBAC бесплатно); проще разработка (один `uv run`)
- Против: blast radius — correlation query или subscriber зависли, тянут за собой весь main app; event loop contention — фоновые задачи (subscriber, correlation engine, retention cron) делят loop с request handling; producer и consumer в одном процессе — физической изоляции нет, producer/consumer разделение только логическое; миграции SIEM и основного app в одной цепочке

**Выбор: отдельный сервис.**

Обоснование: SIEM — полноценная самостоятельная логика (subscriber, correlation engine, alert lifecycle, REST API). Смешивать её с main app нет причин — нет shared state, нет shared queries, нет shared request lifecycle. Отдельный сервис даёт:

- **Blast radius isolation** — SIEM crash/restart не влияет на main app. Main app продолжит публиковать события в Redis Stream; SIEM подхватит pending events после рестарта.
- **Выделенный event loop** — correlation queries (time-window SQL с GROUP BY по большим таблицам) не конкурируют с user-facing requests за CPU и DB connections.
- **Физическое Producer/Consumer разделение** — архитектурный инсайт (producer/consumer ортогональны) получает техническое воплощение: процессы разные, связка — только через транспорт и контракт.
- **Чистота кодовой базы** — SIEM-сервис не загрязняет main app; каждый сервис — свой uv workspace member.

Операционный overhead принят как trade-off: отдельный Dockerfile, compose entry, env, health checks. Для двух сервисов overhead управляем.

### 2. Один процесс, asyncio loop (D3)

SIEM-сервис = один FastAPI-процесс. Subscriber, EventWriter, CorrelationEngine, RetentionTask — `asyncio.create_task` в lifespan.

**Альтернатива: multi-worker** (gunicorn/uvicorn workers)

Subscriber и correlation engine — singleton-задачи: только один экземпляр каждого должен работать. При multi-worker нужна координация: кто запускает subscriber?谁来 correlation engine? Решения — leader election, distributed lock, или выделение background-tasks в отдельный процесс — усложняют SIEM без выигрыша на текущем масштабе.

Масштабирование по процессам отложено до реальной нагрузки. Если API SIEM-сервиса станет bottleneck — добавляются gunicorn workers для API, а background tasks выделяются в отдельный процесс.

### 3. Отдельная PostgreSQL-БД, тот же инстанс (D4)

SIEM использует отдельную логическую БД (`siem_db`) на том же PostgreSQL-инстансе.

**Спектр изоляции:**

| Вариант | Изоляция | Migrations | Ops cost |
|---------|----------|------------|----------|
| Shared DB, shared schema | Нет | Единая цепочка | Минимальный |
| Shared DB, separate schemas | Частичная | Одна БД, разные schemas | Минимальный |
| **Отдельная БД, тот же инстанс** | **Логическая** | **Независимые** | **Минимальный** |
| Отдельная БД, отдельный инстанс | Полная | Независимые | Высокий |

Выбран средний вариант: логическая изоляция (отдельные миграции, независимые backup/restore), минимальный ops cost (тот же PostgreSQL-контейнер). Cross-DB joins невозможны — это не баг, а enforcement изоляции: SIEM не может протащить зависимость на схему основного app.

Следствие: username resolution по `user_id` в UI требует back-channel вызова в main app (D22).

### 4. Frontend — роут `/security` в основном SPA (D2)

Страница мониторинга — lazy-loaded route в существующем React SPA, защищённый RBAC guard по `is_admin` claim из JWT.

**Альтернатива: отдельный SPA-приложение**

SIEM UI пассивен: только читает данные (events, alerts, rules) и вызывает CRUD на alerts/rules. Блокировать запросы, управлять agent-ом, модифицировать security layers UI не может. Изолировать пассивный UI нет причин. Отдельный SPA дублирует дизайн-систему, auth-flow, API client, navigation — без выгоды.

### 5. Кросс-сервисный Identity (D14, D15, D22)

SIEM не имеет собственной таблицы `users` и не дублирует auth-логику. Валидация JWT — по тому же `JWT_SECRET` (HS256), что и в main app, через env обоих сервисов. SIEM читает `is_admin` claim и не делает back-channel вызов в main app на каждый запрос для проверки валидности сессии.

**Альтернатива: RS256 (асимметричный)**

RS256 позволяет верифицировать токен по public key без доступа к secret. Оправдан, когда в системе есть менее доверенные сервисы, которым нельзя давать signing key. SIEM — trusted-class сервис (shared host, trusted network, admin-only). HS256 достаточен. Переход на RS256 — отдельный ADR при появлении менее доверенных интеграций.

**Admin bootstrap:** миграция добавляет `users.is_admin BOOLEAN` в основную БД. Env-переменная `INITIAL_ADMIN_USERNAME` — при старте main app, если пользователь с таким именем существует, ему выставляется `is_admin = true` (идемпотентно).

**Username enrichment (D22):** SIEM делает `GET /api/internal/users?ids=<csv>` в main app, forward'ит admin JWT текущего запроса. Кеш TTL 5 мин. При недоступности main app UI показывает `user_id` без имени (graceful degradation). Authoritative source (`users` table) доступен только через публичный контракт своего сервиса.

### 6. Сетевая модель — trusted network (D23)

Main app, SIEM, Redis, PostgreSQL — один host. Порты не выставлены наружу. Redis без AUTH. Service-to-service HTTP между SIEM и main app без mTLS.

Соразмерно текущему deployment-сценарию (single VM, trusted environment). Ужесточение (Redis ACL, mTLS, network segmentation) — отдельный ADR при выходе за пределы текущего host.

## Последствия

**Положительные:**

- Физическая изоляция producer/consumer — крах SIEM не влияет на main app, и наоборот
- Независимые миграции — SIEM-схема эволюционирует без координации с основным app
- Чистые кодовые границы — каждый сервис решает свою задачу
- Естественный scale path — SIEM масштабируется отдельно при необходимости

**Отрицательные:**

- Операционный overhead: два контейнера, два набора env, два health check
- Cross-service identity через shared secret — при появлении третьего сервиса потребуется пересмотр (RS256 / gateway)
- Username resolution через HTTP — дополнительная зависимость SIEM от доступности main app (митигирована graceful degradation)

**Риски:**

- Shared `JWT_SECRET` — компрометация даёт доступ к обоим сервисам. Соразмерно trusted-network модели: секрет живёт только на одном host в env.
- Producer/consumer self-loop (D16): meta-event из SIEM идёт через тот же pipeline (structlog → Redis → subscriber). Зацикливание исключено архитектурно: meta-event — обычное событие, correlation rules не триггерят на `siem.*` event types (по design).

## Связанные документы

- [design-brief.md](../../tasks/iterations/post-mvp/feat-005-security-event-pipeline/design-brief.md) — полная спецификация feat-005, все decisions
- [session-notes.md](../../tasks/iterations/post-mvp/feat-005-security-event-pipeline/session-notes.md) — контекст архитектурной сессии
- [ADR-011](ADR-011-auth-architecture.md) — auth-архитектура основного app (JWT + refresh tokens)
- [ADR-017](ADR-017-prompt-injection-defense.md) — Security 1.0, producer-side
