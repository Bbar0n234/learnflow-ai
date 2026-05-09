# Implementation Plan: feat-005 — Security Event Pipeline (SIEM Core)

## Контекст

**Цель итерации:** Реализовать SIEM-подсистему для сбора, нормализации, хранения и корреляции security-событий из всех источников (SecurityGuard, auth, rate limiter). Закрывает academic requirements R1–R10 и backlog P2.

**Запись в tasklist:** [feat-005: Security Event Pipeline](../../../tasklist-post-mvp.md#feat-005-security-event-pipeline-siem-core)

**Design brief:** [design-brief.md](design-brief.md) — полная архитектура, контракты, 23 решения (D1–D23, C1–C14), функциональная карта, scope boundaries

**Test cases:** [test-cases.md](test-cases.md) — 60 кейсов по слоям (Layer 0–3), используются для verification

**Ключевые решения:**
- D1: SIEM — отдельный backend-сервис (FastAPI в docker-compose, выделенная PostgreSQL БД, собственные миграции)
- D2: Frontend — роут `/security` в основном SPA (lazy chunk + RBAC guard)
- D5: Транспорт — Redis Streams + Consumer Group с at-least-once семантикой
- D6: Идемпотентность по `event_id` + UNIQUE constraint
- D11: Correlation engine — polling (10 сек, configurable) с `ingested_at` фильтром
- D13: Alert dedup — open-alert policy с 24h возрастным лимитом
- C1: Контракт = Pydantic модель в shared-пакете `packages/siem-contracts/`
- C2: Identifiers через structlog contextvars (HTTP middleware, auth, chat route)

**Архитектурные документы:**
- [ADR-018: SIEM Service Topology](../../../../tech/adr/ADR-018-siem-service-topology.md) — процессный дизайн, изоляция
- [ADR-019: Security Event Transport](../../../../tech/adr/ADR-019-security-event-transport.md) — Redis Streams, semantics
- [ADR-020: Security Event Contract](../../../../tech/adr/ADR-020-security-event-contract.md) — Pydantic model, vocabulary
- [ADR-021: SIEM Correlation Engine](../../../../tech/adr/ADR-021-siem-correlation-engine.md) — правила, стратегии
- [security/architecture.md](../../../../security/architecture.md) — Security 1.0 (producers)
- [tech/observability.md](../../../../tech/observability.md) — Langfuse integration

---

## Фазы реализации

### T1: Vocabulary + Contracts + Producer

**Цель:** Установить контракт событий между producer и consumer; реализовать producer-side normalization и transport publisher; рефакторить существующие producers.

**Изменения по файлам:**

| Файл/Модуль | Действие | Содержание |
|------------|---------|-----------|
| `doc/tech/security-events.md` (новый) | Создать | Полный vocabulary: список всех event_type, форма metadata per type, обязательность identifiers. Включает domains (`auth`, `rate_limit`, `agent.guard`, `agent.runtime`, `siem`) и примеры. Pre-implementation deliverable для Literal-аннотаций |
| `packages/siem-contracts/` (новая подпапка) | Создать как uv-workspace member | Pydantic-контракты между producer и consumer |
| `packages/siem-contracts/pyproject.toml` | Создать | Базовая конфигурация: название `siem-contracts`, version `0.1.0`, зависимость `pydantic>=2.0` |
| `packages/siem-contracts/siem_contracts/__init__.py` | Создать | Публичный API модуля |
| `packages/siem-contracts/siem_contracts/vocabulary.py` | Создать | `EVENT_TYPES` — полный список значений для Literal-аннотаций, организованный по доменам |
| `packages/siem-contracts/siem_contracts/events.py` | Создать | `SecurityEvent` (основная модель), `SecurityEventIdentifiers` (submodel), `Severity` (Literal), `SecurityEventSchema` (для REST, если отличается) |
| `packages/siem-contracts/siem_contracts/alerts.py` | Создать | `AlertDTO`, `AlertStatus` (Literal: new, acknowledged, resolved) для REST API |
| `packages/siem-contracts/siem_contracts/rules.py` | Создать | `RuleConfig` (discriminated union по rule_type: Threshold / Sequence / Aggregate); per-rule параметры (window, group_key, threshold, event_type_pattern) |
| `backend/app/security_pipeline/` (новая папка) | Создать | Весь код producer-side SIEM |
| `backend/app/security_pipeline/__init__.py` | Создать | |
| `backend/app/security_pipeline/vocabulary.py` | Создать | Импорт EVENT_TYPES из shared-пакета; реэкспорт для типизации на producer-сайде |
| `backend/app/security_pipeline/processor.py` | Создать | `SecurityEventProcessor` — structlog processor, собирающий SecurityEvent из `logger.*(security_event=True, ...)` + contextvars; validate & serialize |
| `backend/app/security_pipeline/transport.py` | Создать | `EventTransport` — interface для публикации (Redis реализация); `RedisEventTransport.publish(event: SecurityEvent)` → XADD; `publisher_loop()` фоновая задача (asyncio.Queue) |
| `backend/app/security_pipeline/context.py` | Создать | contextvars: `ip`, `request_id`, `user_id`, `session_id`, `thread_id`, `project_id`, `user_agent_hash` |
| `backend/app/middleware.py` (модифицировать) | Обновить | HTTP middleware: bind `ip` (X-Forwarded-For или REMOTE_ADDR), `request_id` (uuid.uuid4), `user_agent_hash` (sha256(User-Agent header)) в contextvars |
| `backend/app/api/deps.py` (модифицировать) | Обновить | Auth dependency: bind `user_id` и `session_id` в contextvars при аутентифицированном запросе |
| `backend/app/api/routes/chat.py` (модифицировать) | Обновить | Chat route handler: bind `thread_id` и `project_id` из URL params в contextvars на входе |
| `backend/app/agent/security/guard.py` (модифицировать) | Рефакторить | Заменить существующие `logger.info("...", identifiers={})` вызовы на `logger.warning("...", security_event=True, event_type=CANONICAL_TYPE, severity=..., metadata={...})` per checkpoint; использовать Literal для event_type из vocabulary |
| `backend/app/api/auth.py` (модифицировать) | Рефакторить | Add security logging: `auth.login.failed`, `auth.login.success`, `auth.refresh.replay_detected` и т.п. через canonical event_type |
| `backend/app/middleware.py` (модифицировать) | Рефакторить | Add rate-limiter log: `rate_limit.<scope>.exceeded` (например, `rate_limit.login.exceeded`) |
| `backend/app/lifespan.py` (модифицировать) | Обновить | Добавить publisher_loop в lifespan startup; graceful drain в shutdown |
| `backend/pyproject.toml` (модифицировать) | Обновить | Добавить зависимость на `siem-contracts` (workspace source) и `redis[asyncio]` если ещё нет |
| `root/pyproject.toml` (модифицировать) | Обновить | Добавить `packages/siem-contracts` в workspace members |

**Verification (test-cases):**
- {T1.1} Pydantic-валидация SecurityEvent: positive
- {T1.2} Pydantic-валидация SecurityEvent: negative
- {T1.3} Literal-vocabulary mypy-проверяемо
- {T1.4} structlog processor: сборка SecurityEvent
- {T1.5} contextvars binding: HTTP middleware
- {T1.6} contextvars binding: auth dependency
- {T1.7} contextvars binding: chat route
- {T1.8} Producer-side bounded queue (overflow, drop-newest)
- {T1.9} Publisher loop: graceful shutdown
- {T1.10} Existing producers переведены на canonical event_type
- {T1.11} Redis Stream: producer пишет (XLEN, XREAD)

**Декомпозиция T1 (если неделима):** 
Если размер слишком велик, split на T1.a (contracts + processor) и T1.b (producer rework + transport), но в результате обе подфазы образуют целый коммит в feature branch.

---

### T2: SIEM service skeleton + ingestion

**Цель:** Развернуть отдельный backend-сервис для SIEM; реализовать subscriber (Redis Consumer Group), валидатор, Event Writer; REST GET /security/events с фильтрацией и пагинацией.

**Изменения по файлам:**

| Файл/Модуль | Действие | Содержание |
|-----------|---------|-----------|
| `packages/siem-service/` (новая подпапка) | Создать | Отдельное FastAPI приложение (monorepo в workspace) |
| `packages/siem-service/pyproject.toml` | Создать | Зависимости: `fastapi`, `sqlalchemy[asyncio]`, `alembic`, `redis[asyncio]`, `pydantic`, `siem-contracts` (workspace) и др. |
| `packages/siem-service/alembic/` | Создать | Миграции для SIEM БД (отдельные от main app) |
| `packages/siem-service/alembic/env.py` | Создать | Конфиг Alembic (DATABASE_URL с переменной окружения, например SIEM_DATABASE_URL) |
| `packages/siem-service/alembic/versions/001_initial_schema.py` | Создать | DDL: таблицы `siem_events`, `siem_alerts`, `correlation_rules`, индексы (см. T3) |
| `packages/siem-service/siem_service/` | Создать | Пакет приложения |
| `packages/siem-service/siem_service/main.py` | Создать | FastAPI app, lifespan (startup/shutdown для фоновых задач) |
| `packages/siem-service/siem_service/config.py` | Создать | Settings: DATABASE_URL, REDIS_URL, JWT_SECRET (общий с main app), XREAD_BATCH_SIZE (default ~100), POLL_INTERVAL (default ~10 сек) |
| `packages/siem-service/siem_service/db.py` | Создать | SQLAlchemy engine, session factory, dependency для routes |
| `packages/siem-service/siem_service/models.py` | Создать | ORM-модели: `SiemEvent`, `SiemAlert`, `CorrelationRule` (таблица, не хардкод) |
| `packages/siem-service/siem_service/schemas.py` | Создать | Pydantic schemas для API response (EventResponse, AlertResponse, RuleResponse с пагинацией) |
| `packages/siem-service/siem_service/subscriber.py` | Создать | XREADGROUP loop, Pydantic-валидация, dедуп по event_id (ON CONFLICT), XACK; при validation error → drop + метрика + warning-лог |
| `packages/siem-service/siem_service/event_writer.py` | Создать | Единственная точка INSERT в siem_events; при дедупе → no-op |
| `packages/siem-service/siem_service/repositories.py` | Создать | EventRepository (list + filters), AlertRepository (list + filters), RuleRepository (CRUD); пагинация (offset, limit) |
| `packages/siem-service/siem_service/services.py` | Создать | EventService, AlertService (PATCH acknowledge/resolve с мета-логированием), RuleService (CRUD с seed) |
| `packages/siem-service/siem_service/auth.py` | Создать | JWT validation (HS256 с JWT_SECRET), чтение claim `is_admin`; dependency для admin-only routes |
| `packages/siem-service/siem_service/api/` | Создать | API routes |
| `packages/siem-service/siem_service/api/routes.py` | Создать | `GET /security/events` (pagination, filters: event_type, severity, timestamp range) |
| `packages/siem-service/siem_service/supervisor.py` | Создать | Standard async task wrapper: try/except + restart с exponential backoff (1s → 60s cap); используется для subscriber, correlation engine (Phase 3), retention task |
| `docker-compose.yml` (модифицировать) | Обновить | Добавить service siem-service (image: learnflow-siem:latest, зависит от siem-db и redis), переменные окружения (DATABASE_URL, REDIS_URL, JWT_SECRET) |
| `packages/siem-service/Dockerfile` | Создать | Базовый Dockerfile для siem-service (FROM python:3.11, UV install, CMD uvicorn) |
| `.dockerignore` (модифицировать, если есть) | Обновить | Исключить __pycache__, .git, *.pyc и т.п. |
| `Makefile` (модифицировать) | Обновить | Таргеты: `migrate-siem` (Alembic upgrade для siem-service БД), `docker-up` включает siem-service автоматически |
| `packages/siem-service/.env.example` | Создать | Шаблон с SIEM_DATABASE_URL, REDIS_URL и т.п. (или один .env.example в root covers all) |

**Дизайн таблиц (DDL в миграции T2.1):**

```sql
-- siem_events (основное хранилище событий)
CREATE TABLE siem_events (
    id BIGSERIAL PRIMARY KEY,
    event_id UUID NOT NULL UNIQUE,  -- идемпотентность для at-least-once
    event_type VARCHAR(255) NOT NULL,  -- открытая схема, no CHECK
    severity VARCHAR(20) NOT NULL,  -- info | warning | critical
    event_timestamp TIMESTAMP NOT NULL,  -- UTC, от producer
    ingested_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,  -- consumer time (для окна правил)
    identifiers JSONB,  -- { ip?, user_id?, request_id?, thread_id?, ... }
    metadata JSONB,  -- event-specific детали, форма per event_type
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_siem_events_event_type ON siem_events(event_type);
CREATE INDEX idx_siem_events_severity ON siem_events(severity);
CREATE INDEX idx_siem_events_ingested_at ON siem_events(ingested_at);
CREATE INDEX idx_siem_events_identifiers_ip ON siem_events USING GIN(identifiers);  -- для WHERE identifiers @> '{"ip": "..."}'
```

**Verification:**
- {T2.1} Pydantic-валидация на consumer
- {T2.2} Дедупликация по event_id
- {T2.3} XREADGROUP → INSERT → XACK atomicity + restart recovery
- {T2.4} Unknown event_type принимается (vocabulary-soft)
- {T2.5} Dual timestamp (event_timestamp vs ingested_at)
- {T2.6} REST GET /security/events: pagination
- {T2.7} REST GET /security/events: фильтры

---

### T3: Correlation + Alerts + RBAC + полный API + Meta-log

**Цель:** Реализовать correlation engine с тремя типами правил (Threshold, Sequence, Aggregate); alert deduplication; RBAC с JWT + admin bootstrap; мета-логирование; полный REST API для alerts и rules.

**Изменения по файлам:**

| Файл/Модуль | Действие | Содержание |
|-----------|---------|-----------|
| `packages/siem-service/alembic/versions/002_alerts_and_rules.py` | Создать | Миграция: таблицы `siem_alerts`, `correlation_rules` |
| `packages/siem-service/siem_service/models.py` (обновить) | Добавить | `SiemAlert` (rule_id FK, severity, status enum, group_key, matched_events_count, first_event_id FK, latest_event_id FK, created_at, acknowledged_at, resolved_at) |
| `packages/siem-service/siem_service/models.py` (обновить) | Добавить | `CorrelationRule` (name, description, rule_type enum: Threshold/Sequence/Aggregate, enabled, config JSONB: { window: int, group_key?: str, threshold?: int, event_type_pattern?: str, sequence_a?: str, sequence_b?: str, ...}, created_at, updated_at) |
| `packages/siem-service/alembic/versions/002_alerts_and_rules.py` (обновить) | Добавить | DDL индексов: `idx_siem_alerts_status`, `idx_siem_alerts_rule_id`, `idx_siem_alerts_created_at` |
| `packages/siem-service/alembic/versions/003_baseline_rules.py` | Создать | Seed idempotent: INSERT INTO correlation_rules VALUES (... baseline 4+ rules ...) ON CONFLICT DO NOTHING; baseline rules: `brute_force_auth` (≥5 auth.login.failed за 60с, group_key=ip), `injection_spike` (≥10 `agent.guard.%.injection` за 5м, no grouping), `targeted_user_attack` (≥3 guard события за 10м, group_key=user_id), `mass_suspicious` (≥15 SUSPICIOUS verdicts за 10м, no grouping) — точный состав уточняется в ходе планирования, минимум 4 правила |
| `packages/siem-service/siem_service/correlation/` | Создать | Пакет с логикой корреляции |
| `packages/siem-service/siem_service/correlation/__init__.py` | Создать | |
| `packages/siem-service/siem_service/correlation/engine.py` | Создать | `CorrelationEngine` — main entry point: load active rules, polling-цикл (10 сек configurable), делегирование в стратегии, dedup через open-alert policy |
| `packages/siem-service/siem_service/correlation/strategies.py` | Создать | `ThresholdStrategy`, `SequenceStrategy`, `AggregateStrategy` — каждая реализует `evaluate(rule: CorrelationRule, events: List[SiemEvent]) -> Optional[AlertCandidate]` |
| `packages/siem-service/siem_service/correlation/deduper.py` | Создать | `AlertDeduper`: open-alert policy, 24h возрастной лимит (MAX_ALERT_AGE = 86400 сек), logic: `get_open_alert(rule_id, group_key) -> SiemAlert?` → если существует и моложе 24h → append (update matched_events_count, latest_event_id, updated_at), иначе → new alert |
| `packages/siem-service/siem_service/api/routes.py` (обновить) | Расширить | `GET /security/alerts` (pagination, filters: severity, status); `PATCH /security/alerts/:id` (acknowledge / resolve); `GET /security/rules`, `POST`, `PATCH`, `DELETE` |
| `packages/siem-service/siem_service/services.py` (обновить) | Расширить | `AlertService.acknowledge()` / `resolve()` — emit мета-event `siem.alert.acknowledged` / `resolved` через transport publisher (back-channel в main app в Redis Stream) |
| `backend/app/security_pipeline/transport.py` (обновить) | Расширить | Добавить метод `publish_meta_event()` для мета-логирования из SIEM-сервиса; это то же XADD, но вызываемое из siem-service |
| `packages/siem-service/siem_service/identity/` | Создать | `JWTValidator` — HS256 validation, claim extraction |
| `packages/siem-service/siem_service/api/deps.py` | Создать | `admin_only` dependency: JWT validation + проверка `is_admin` claim → 403 если false |
| `packages/siem-service/siem_service/lifespan.py` | Создать | lifespan: startup → запустить correlation_engine в supervisor, shutdown → graceful stop |
| `backend/app/models.py` (модифицировать) | Обновить | Добавить миграцию `users.is_admin BOOLEAN DEFAULT false` в main app |
| `backend/app/api/bootstrap.py` (модифицировать или новый) | Обновить/Создать | Идемпотентный bootstrap админа: на старте main app проверить env `INITIAL_ADMIN_USERNAME`, если exists в БД → `users.is_admin = true` (idempotent) |
| `.env.example` (модифицировать) | Обновить | Добавить `SIEM_DATABASE_URL`, `INITIAL_ADMIN_USERNAME`, убедиться что `JWT_SECRET` есть |
| `docker-compose.yml` (модифицировать) | Обновить | siem-db service (PostgreSQL), env для siem-service, health checks |

**Baseline correlation rules (точный состав):**
1. **brute_force_auth:** Threshold, event_type_pattern = `auth.login.failed`, threshold = 5, window = 60s, group_key = ip
2. **injection_spike:** Aggregate, event_type_pattern = `agent.guard.%.injection`, threshold = 10, window = 300s (5м)
3. **targeted_user_attack:** Threshold, event_type_pattern = `agent.guard.*`, threshold = 3, window = 600s (10м), group_key = user_id
4. **mass_suspicious:** Aggregate, event_type_pattern = `agent.guard.*.suspicious`, threshold = 15, window = 600s (10м)

**Verification:**
- {T3.1} Threshold rule: brute_force_auth
- {T3.2} Sequence rule
- {T3.3} Aggregate rule
- {T3.4} NULL group_key (пропуск события)
- {T3.5} Open-alert dedup: append
- {T3.6} Open-alert dedup: возрастной лимит 24h
- {T3.7} Open-alert dedup: после resolve
- {T3.8} JWT validation (is_admin claim)
- {T3.9} CRUD correlation_rules
- {T3.10} PATCH /alerts/:id — acknowledge
- {T3.11} PATCH /alerts/:id — resolve
- {T3.12} Idempotent seed правил
- {T3.13} Bootstrap админа (INITIAL_ADMIN_USERNAME)
- {T3.14} Meta-log: acknowledge
- {T3.15} Meta-log: resolve
- {T3.16} Meta-log: rule CRUD

---

### T4: Frontend + Integration + ADRs

**Цель:** Реализовать React-страницу `/security` с тремя view (events / alerts / rules); RBAC guard; RU локализация; e2e интеграция; финализировать ADR.

**Изменения по файлам:**

| Файл/Модуль | Действие | Содержание |
|-----------|---------|-----------|
| `frontend/src/pages/Security.tsx` (новый) | Создать | Lazy-loaded page с тремя табами (Events / Alerts / Rules); RBAC guard (проверка `is_admin` из JWT); общий layout |
| `frontend/src/pages/SecurityEvents.tsx` (новый) | Создать | Events view: список событий (таблица или список), фильтры (event_type dropdown, severity dropdown, date range picker), пагинация, drill-down для metadata (expand или modal) |
| `frontend/src/pages/SecurityAlerts.tsx` (новый) | Создать | Alerts view: список алертов, фильтры (severity, status), пагинация, кнопки Acknowledge / Resolve с toast уведомлениями, drill-down к связанным событиям |
| `frontend/src/pages/SecurityRules.tsx` (новый) | Создать | Rules view: список правил CRUD, кнопки Create / Edit / Delete, модальные формы (разные поля в зависимости от rule_type: Threshold / Sequence / Aggregate) |
| `frontend/src/hooks/useSecurityAPI.ts` (новый) | Создать | RQ-хуки: `useEvents()`, `useAlerts()`, `useRules()` с фильтрацией, пагинацией, мутациями (acknowledge, resolve, CRUD rules) |
| `frontend/src/components/SecurityFilter.tsx` (новый) | Создать | Shared компонент для фильтров (event_type, severity, status, date range) с контролем на query params (useSearchParams) |
| `frontend/src/components/SecurityPagination.tsx` (новый) | Создать | Shared компонент для пагинации (prev/next, page indicator) |
| `frontend/src/locales/ru.json` (модифицировать) | Обновить | RU-переводы для всех labels на /security: "События" (Events), "Алерты" (Alerts), "Правила" (Rules), "Тип события" (Event Type), "Серьезность" (Severity), "Статус" (Status), "Подтвердить" (Acknowledge), "Разрешить" (Resolve), "Создать правило" (Create Rule), severity values ("INFO", "WARNING", "CRITICAL"), status values ("Новое" = new, "Подтверждено" = acknowledged, "Решено" = resolved) |
| `frontend/src/App.tsx` (модифицировать) | Обновить | Добавить маршрут `/security` (lazy chunk), RBAC guard обёртка |
| `frontend/src/layouts/Navigation.tsx` (модифицировать) | Обновить | Добавить ссылку на `/security` в сайдбар (видна только если `is_admin`), иконка и русский label |
| `frontend/src/types/security.ts` (новый) | Создать | TypeScript types для Events, Alerts, Rules (дублируют schemas из siem-service для type safety на frontend) |
| `frontend/src/api/security.ts` (новый) | Создать | API клиент: fetch wrapper для `/api/security/...` эндпоинтов (GET events, GET alerts, PATCH alerts, GET/POST/PATCH/DELETE rules) |
| `doc/tech/adr/ADR-018-siem-service-topology.md` (финализировать) | Пересмотреть | Убедиться что решения матчат реальной реализации; обновить если были отклонения |
| `doc/tech/adr/ADR-019-security-event-transport.md` (финализировать) | Пересмотреть | Проверить, что Redis Streams + Consumer Group реализованы per spec |
| `doc/tech/adr/ADR-020-security-event-contract.md` (финализировать) | Пересмотреть | Проверить, что Pydantic-контракты матчат C1–C14 decisions |
| `doc/tech/adr/ADR-021-siem-correlation-engine.md` (финализировать) | Пересмотреть | Проверить, что правила, стратегии, open-alert policy реализованы per spec |
| `doc/tech/observability.md` (обновить) | Добавить | Секция про SIEM observability: структуры логов, метрики, Langfuse scoring (если применимо) |
| `doc/tech/backend.md` (обновить) | Добавить | Секция про SIEM API endpoints и слои (по аналогии с backend.md) |
| `doc/security/architecture.md` (обновить) | Добавить | Упоминание SIEM как consumer-слоя; как события интегрируются |

**UI Spec (детальное наполнение):**

**Events View:**
- Таблица: Timestamp (asc/desc sort), Event Type, Severity (badge цвета: blue=info, yellow=warning, red=critical), Identifiers (ip, user_id, thread_id), Actions (Expand)
- Expand row: Show full metadata как JSON или structured view per event_type
- Фильтры: Event Type (multi-select dropdown), Severity (checkboxes), Date Range (date picker from/to)
- Pagination: Limit (10/20/50), Page indicator, Prev/Next buttons

**Alerts View:**
- Таблица: Rule Name, Severity (badge), Status (new/acknowledged/resolved), Group Key, Matched Events Count, Created At, Latest At, Actions (Acknowledge / Resolve buttons if status=new, disabled if acknowledged/resolved)
- Фильтры: Severity, Status (radio: All/New/Acknowledged/Resolved)
- Drill-down: Click alert → show matched events list (modal or sidebar)
- Toast на successful acknowledge/resolve

**Rules View:**
- Таблица: Name, Type (Threshold/Sequence/Aggregate), Enabled (toggle), Created At, Actions (Edit / Delete)
- Edit button → modal with form fields per type:
  - Threshold: rule name, enabled, event_type_pattern, threshold count, window seconds, group_key (optional dropdown: ip/user_id/thread_id/none)
  - Sequence: name, enabled, event_a pattern, event_b pattern, window, group_key (optional)
  - Aggregate: name, enabled, event_type_pattern, threshold, window (no group_key)
- Create button → rule type selection modal → then edit form
- Delete → confirmation dialog

**Verification:**
- {T4.1} RBAC guard на роуте /security
- {T4.2} Localization (все labels на RU)
- {T4.3} RQ-хуки: фильтры и пагинация
- {T4.4} UI: events view
- {T4.5} UI: alerts view
- {T4.6} UI: rules view

---

## Cross-cutting

Финальная verifikation после всех фаз:

| Тест | Тест кейсы | Описание |
|------|------------|---------|
| Automated gate | Layer 0 | `make check`, `make check-fe`, миграции clean БД |
| E2E producer→consumer | {INT.1} | SecurityGuard.check() → event в siem_events за <2s |
| Integration layer | {INT.2}–{INT.7} | Backpressure, ingested_at фильтр, supervisor, username enrichment, forward compat |
| E2E scenarios | {E2E-1}–{E2E-8} | UI: login, live event flow, brute force, filters, alerts, rules, localization |

**Forward compatibility {INT.7}:**
- Добавить новый event_type в Literal в shared-пакете
- Producer пишет событие с новым типом
- SIEM-сервис принимает (vocabulary-soft), пишет в БД, UI отображает
- Никаких миграций SIEM не требуется

---

## Декомпозиция по комитам

Каждая фаза (T1–T4) образует несколько atomарных коммитов в рамках feature branch (например, `be/feat-005-security-event-pipeline`):

**T1 коммиты:**
1. `feat(siem): add shared contracts and vocabulary`
2. `feat(siem): implement producer-side event normalization`
3. `feat(siem): add structlog processor and transport publisher`
4. `refactor(security): migrate SecurityGuard to canonical event types`
5. `refactor(auth): add security event logging for auth flows`
6. `refactor(rate-limiter): add security event logging`

**T2 коммиты:**
1. `feat(siem-service): add skeleton and database schema`
2. `feat(siem-service): implement subscriber and event ingestion`
3. `feat(siem-service): add REST API for events endpoint`

**T3 коммиты:**
1. `feat(siem-service): add correlation engine and rule strategies`
2. `feat(siem-service): implement alert deduplication and management`
3. `feat(siem-service): add RBAC and admin bootstrap`
4. `feat(siem-service): implement meta-logging pipeline`
5. `feat(siem-service): add complete alerts and rules CRUD API`

**T4 коммиты:**
1. `feat(frontend): add Security page with Events, Alerts, Rules views`
2. `feat(frontend): add RBAC guard and Russian localization`
3. `docs(adr): finalize ADR-018..021 and update architecture docs`

---

## Open Questions

**Нет открытых вопросов.** Все архитектурные решения зафиксированы в design-brief (D1–D23, C1–C14) и ADR-018..021. Параметры, детализируемые на этапе реализации:

### Уточнения, которые появятся в процессе:

1. **Точный SQL для strategies** — будут ли это отдельные SQL-queries per strategy, или ORM-выражения в Python? Рекомендация: SQL in `correlation/queries.sql`, выполняемые через raw conn для производительности. Кэширование активных правил в памяти engine'а (reload каждый polling-cycle).

2. **UI detail: drill-down от алерта к событиям** — modal, sidebar или отдельная страница? Рекомендация: modal с фильтром на matched_events_count, fetch связанных событий через `GET /security/events?matched_alert_id=...` или внутри alert detail.

3. **Метрики в SIEM** — какие? Рекомендация (minimal): Prometheus metrics через fastapi-prometheus или встроенные счётчики (producer_drop_newest, siem_unknown_event_type, siem_events_invalid, alerts_created_total). Экспорт в `/metrics` endpoint'е.

4. **Retention cron для siem_events** — есть ли? Рекомендация: async background task в supervisor, удалить события старше 90 дней (configurable via env DELETE_AFTER_DAYS). Schedule: 1x per day в midnight UTC.

5. **Username enrichment кеш** — где и как? Рекомендация: in-memory dict в service, TTL 5 мин; при miss — fetch `GET /api/internal/users?ids=...` из main app, admin-only.

Все эти уточнения — implementation details, не архитектурные решения. При возникновении неоднозначности на этапе кода — обсудить с архитектором, но не блокировать реализацию.

### Потенциальные friction points (требуют внимания):

1. **workspace dependency между main app и siem-service** — оба импортируют siem-contracts из локального source. При добавлении зависимостей в siem-contracts (например, нестандартный JSON encoder) убедиться что они совместимы с обоими сервисами.

2. **JWT shared secret** — main app и siem-service читают одинаковый JWT_SECRET из env. При ротации секрета — скоординировать развёртывание.

3. **Мета-логирование (back-channel)** — SIEM эмитит события через Redis Stream в основной app's producer. Цикл замыкается: основной app читает (если используется log-reader), pишет в SIEM. Это by-design, но следить, чтобы не было infinite loop'а (основное приложение должно отвергать мета-события с `siem.*` префиксом при их появлении как пользовательские логи).

4. **Rate limiter в основном app** — сейчас может быть реализован как middleware; при добавлении security logging убедиться, что логирование не попадёт на hot path (перенести в background task, если нужно).

---

## Итоговая сводка

**Фазы:** T1 (Vocabulary + Producer) → T2 (SIEM Service + Ingestion) → T3 (Correlation + Alerts + RBAC) → T4 (Frontend)

**Артефакты (deliverables):**
- Shared-пакет `packages/siem-contracts/` с Pydantic-контрактами
- Отдельный backend-сервис `packages/siem-service/` с собственной БД
- React-страница `/security` в основном SPA (lazy chunk)
- Документ `doc/tech/security-events.md` с vocabulary
- 4 ADR (ADR-018..021) — финализированные per реализацию
- 60 test-cases, прогнанные по слоям (Layer 0–3)

**Scope MVP (feat-005):** Сбор, нормализация, хранение, корреляция, алерты, REST API, monitoring UI, RBAC, мета-логирование, RU локализация. Закрывает R1–R10, backlog P2, forward compatible с Security 2.0.

**Deferred (feat-007):** Dashboard & Metrics, response actions (ban IP/user), extended search, notifications, export.
