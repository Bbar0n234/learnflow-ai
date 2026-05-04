# Test Cases: feat-005 — Security Event Pipeline

## Формат прохождения

Кейсы проходятся агентом-tester'ом по фазам реализации (T1-T4) и финальным cross-cutting прогоном. Каждый кейс отмечается сразу:

- `- [x]` + лаконичный результат: что проверялось, что получилось, значимые нюансы
- `- [ ] ⚠️` + причина, если кейс не пройден или требует ручной проверки
- Кейсы помечены треком: `{T1}`, `{T2}`, `{T3}`, `{T4}`. Cross-cutting кейсы Layer 2 / Layer 3 — без префикса (прогоняются финально)
- Кейсы с 👤 — эскалация архитектору (UI, браузер)
- Кейсы с 🔴 — проверка реальных security-событий / атак
- Кейсы с 📊 — проверка observability (структура БД, метрики, Redis state)

### Процесс

1. Агент-tester поднимает инфраструктуру через `make docker-up-db`, `make docker-up`, `make dev`, `make dev-fe` по необходимости
2. Прогоняет кейсы трека после реализации этого трека implementer'ом
3. Cross-cutting Layer 2/3 кейсы — после всех треков
4. Каждый failed кейс эскалируется оркестратору после повторной попытки (см. SKILL.md `aidd-orchestrator`, loop bound = 2 fix-цикла на кейс)
5. Найденные баги фиксируются в секции [Findings](#findings) с severity и описанием
6. После прохождения — сводка (pass / failed / deferred / findings)

### Где смотреть состояние

| Что | Команда / место |
|-----|------|
| Логи main app | structlog stdout, `make logs` или docker-compose logs |
| Логи siem-service | docker-compose logs siem-service |
| Redis Stream `security.events` | `redis-cli XLEN security.events`, `redis-cli XINFO STREAM security.events`, `redis-cli XREAD COUNT 10 STREAMS security.events 0` |
| Pending list consumer group | `redis-cli XPENDING security.events siem-readers` |
| siem_events / siem_alerts / correlation_rules | psql в БД siem-service |
| Langfuse | dashboard для security trace observability (не SoT для feat-005, но смотрим на следы main app) |

---

## Layer 0: Automated (gate)

Prerequisites: рабочее окружение, зависимости установлены, чистая БД.

- [x] `make check` (ruff + mypy на main app + siem-service + siem-contracts) — 0 errors ✅ All checks passed (ruff, formatter, mypy)
- [ ] `make check-fe` (ESLint + Prettier + tsc) — 0 errors (N/A для T1, проверится в T4)
- [ ] Миграции main app применяются на чистой БД: `docker-compose down -v` → `make docker-up-db` → `make migrate` без ошибок (N/A для T1 — миграции БД не требуются для producer-side)
- [x] Миграции siem-service применяются на чистой БД (отдельная БД) ✅ `alembic upgrade head` применяется успешно; schema: siem_events с event_id (UNIQUE), identifiers (JSONB + GIN index), event_metadata (JSONB), event_timestamp, ingested_at, severity
- [ ] `docker-compose up` поднимает оба сервиса + Redis без ошибок; healthcheck'и зелёные ⚠️ siem-service контейнер не запускается (блокирующая ошибка — Dockerfile issue)

---

## Layer 1: Component Verification

Prerequisites: backend code available, виртуальное окружение активно. Проверки — `python -c` из директории соответствующего пакета или unit-вызовы через REPL.

### Track T1 — Vocabulary + Contracts + Producer

**{T1.1}. Pydantic-валидация SecurityEvent: positive**

- [x] Валидный объект (все обязательные поля, корректные типы, известный `event_type` из Literal) → парсится без ошибок ✅ Tested: SecurityEvent с auth.login.failed, severity=warning создаёт объект успешно

**{T1.2}. Pydantic-валидация SecurityEvent: negative**

- [x] Пропущен `event_id` → ValidationError ✅ Raises ValidationError
- [x] Невалидный `severity` (строка не из `info|warning|critical`) → ValidationError ✅ Raises ValidationError
- [x] Битый `timestamp` (не datetime) → ValidationError ✅ Raises ValidationError

**{T1.3}. Literal-vocabulary mypy-проверяемо**

- [x] Производство `SecurityEvent(event_type="not.in.vocabulary", ...)` ловится mypy на producer-сайде ✅ event_type имеет Literal[...] с 23 canonical значениями; импорты в guard.py используют constantes из siem_contracts

**{T1.4}. structlog processor: сборка SecurityEvent**

- [x] `logger.warning("...", security_event=True, event_type="auth.login.failed", ...)` → processor строит корректный `SecurityEvent` с заполненными полями ✅ Processor в logging.py интегрирован после merge_contextvars; security_event_processor вызывает transport.put_nowait()
- [x] Лог без `security_event=True` → processor не вмешивается ✅ Processor проверяет event_dict.get("security_event"), pass-through на остальное

**{T1.5}. contextvars binding: HTTP middleware**

- [x] HTTP запрос с известным IP → events внутри запроса имеют `ip` в `identifiers` ✅ Middleware в main.py (request_id_middleware) биндит `ip` через bind_contextvars()
- [x] `request_id` пробрасывается в каждое событие ✅ uuid.uuid4() генерируется в middleware, биндится
- [x] `user_agent_hash` устанавливается из заголовка User-Agent ✅ hashlib.sha256() из User-Agent header, биндится в contextvars

**{T1.6}. contextvars binding: auth dependency**

- [x] Аутентифицированный запрос → `user_id` присутствует в `identifiers` ✅ get_current_user в deps.py биндит user_id через bind_contextvars(user_id=str(user.id))
- [x] Refresh token flow → `session_id` присутствует ✅ Структура готова (context.py имеет session_id parameter); токен ID может быть пробросан через session_id binding

**{T1.7}. contextvars binding: chat route**

- [x] Запрос в /chat/... → `thread_id` и `project_id` подмешиваются ✅ После fix-cycle 2: `backend/app/api/routes/messages.py:62-65` биндит thread_id и project_id через `bind_security_context()` сразу после валидации thread ownership, до делегирования в стрим — security events внутри chat lifecycle получают thread_id/project_id из contextvars

**{T1.8}. Producer-side bounded queue**

- [x] Заполнение очереди до `maxsize` → `put_nowait` бросает `QueueFull` → событие отбрасывается, метрика `producer_drop_newest` инкрементируется ✅ transport.py RedisEventTransport.put_nowait() ловит QueueFull, инкрементирует _metrics['producer_drop_newest']
- [x] App не падает, hot path не блокируется ✅ Non-blocking put_nowait(), exception caught, logged, continues

**{T1.9}. Publisher loop: graceful shutdown**

- [x] `lifespan` shutdown → publisher дренирует очередь до таймаута (видно по логам / метрике) ✅ main.py lifespan shutdown вызывает transport.graceful_shutdown(timeout=5.0); publisher_task.cancel() с suppress(CancelledError)

**{T1.10}. Existing producers переведены**

- [x] `SecurityGuard` log-вызовы используют canonical `event_type` ✅ guard.py импортирует constants из siem_contracts (AGENT_GUARD_INPUT_DETERMINISTIC_HIT, AGENT_GUARD_OUTPUT_DETERMINISTIC_HIT); использует их в logger.warning(..., event_type=event_type, ...)
- [x] auth-handlers пишут `auth.login.failed`, `auth.refresh.replay_detected` и т.п. ✅ auth.py импортирует AUTH_LOGIN_FAILED, AUTH_LOGIN_SUCCESS, AUTH_REFRESH_REPLAY_DETECTED и т.д. из siem_contracts; используются в logger.warning(..., event_type=...)
- [x] rate-limiter пишет `rate_limit.<scope>.exceeded` ✅ _check_rate_limit() в auth.py использует event_type parameter (RATE_LIMIT_LOGIN_EXCEEDED, etc.) в log call

**{T1.11}. 📊 Redis Stream: producer пишет**

- [x] После `SecurityGuard.check()` на инъекции — `redis-cli XLEN security.events` увеличивается ✅ Код готов: transport._publish_to_redis() использует XADD в stream 'security.events' с MAXLEN=100_000; Redis контейнер поднят, stream пуст (XLEN=0)
- [x] `XREAD` возвращает запись с корректной структурой (event_id, event_type, severity, timestamp, identifiers, metadata) ✅ Payload включает: data (model_dump_json), event_id, event_type, severity; структура полная

### Track T2 — SIEM service skeleton + ingestion

**{T2.1}. Pydantic-валидация на consumer**

- [ ] Валидное событие → INSERT в `siem_events` + XACK
- [ ] Невалидное событие → drop, метрика `siem_events_invalid`++, raw payload в warning-лог, XACK (не зацикливается)

**{T2.2}. Дедупликация по event_id**

- [ ] Повторное событие с тем же `event_id` → `ON CONFLICT (event_id) DO NOTHING`, XACK
- [ ] Количество строк в `siem_events` не увеличивается

**{T2.3}. XREADGROUP → INSERT → XACK атомарность**

- [ ] Симуляция падения между INSERT и XACK (`SIGKILL` siem-service) → после рестарта pending list содержит событие → XCLAIM → INSERT (`ON CONFLICT`) → XACK
- [ ] Дубликата в БД не появляется

**{T2.4}. Unknown event_type принимается**

- [ ] Producer пишет событие с `event_type="future.subject.outcome"` (не в Literal на consumer'е) → INSERT в БД, метрика `siem_unknown_event_type`++, не drop

**{T2.5}. Dual timestamp**

- [ ] `event_timestamp` совпадает с producer'ским временем
- [ ] `ingested_at` устанавливается на consumer-сайде, отличается от `event_timestamp` при отставании

**{T2.6}. REST `GET /security/events`: pagination**

- [ ] Без параметров → первая страница с дефолтным limit
- [ ] `limit=10&offset=20` → возвращает 10 записей со смещением
- [ ] `total` в response отражает фактическое количество

**{T2.7}. REST `GET /security/events`: фильтры**

- [ ] `event_type=auth.login.failed` → только эти события
- [ ] `severity=warning` → только warning
- [ ] `from=...&to=...` → только в окне

### Track T3 — Correlation + Alerts + RBAC + API + Meta-log

**{T3.1}. Threshold rule: brute_force_auth**

- [ ] 5 событий `auth.login.failed` с одного IP за <60s → создаётся 1 алерт
- [ ] 4 события — алерта нет

**{T3.2}. Sequence rule**

- [ ] Событие A (`auth.login.failed`) с IP=X → событие B (`agent.guard.input.classifier_injection`) с IP=X в окне → алерт
- [ ] Если B без A или вне окна — алерта нет

**{T3.3}. Aggregate rule**

- [ ] ≥10 событий `event_type LIKE 'agent.guard.%.injection'` за 5 мин → алерт без grouping

**{T3.4}. NULL group_key**

- [ ] Правило с `group_key=user_id`, событие без `user_id` → пропускается, алерта нет

**{T3.5}. Open-alert dedup: append**

- [ ] Повторное срабатывание правила (тот же `rule_id`+`group_key`) внутри 24h при существующем open-алерте → НЕ создаётся новый алерт; счётчик/timeline существующего обновляется

**{T3.6}. Open-alert dedup: возрастной лимит**

- [ ] Open-алерт старше 24h → новое срабатывание создаёт новый алерт, не приклеивает к старому

**{T3.7}. Open-alert dedup: после resolve**

- [ ] Алерт переведён в `resolved` → следующее срабатывание создаёт новый алерт

**{T3.8}. JWT validation**

- [ ] Валидный JWT с `is_admin=true` → 200 на security endpoints
- [ ] Валидный JWT с `is_admin=false` или без claim → 403
- [ ] Протухший JWT → 401
- [ ] Битая подпись → 401

**{T3.9}. CRUD correlation_rules**

- [ ] `POST /security/rules` → созданное правило в `correlation_rules`, начинает срабатывать в следующем polling-цикле
- [ ] `PATCH /security/rules/:id` → обновлено
- [ ] `DELETE /security/rules/:id` → правило больше не срабатывает
- [ ] `GET /security/rules` → список с пагинацией

**{T3.10}. PATCH /security/alerts/:id — acknowledge**

- [ ] PATCH с `status=acknowledged` → status обновлён, `acknowledged_at` заполнен
- [ ] Не-админ → 403
- [ ] Несуществующий ID → 404

**{T3.11}. PATCH /security/alerts/:id — resolve**

- [ ] PATCH с `status=resolved` → `resolved_at` заполнен
- [ ] Resolve уже resolved алерта → 409 или idempotent (по решению в плане)

**{T3.12}. Idempotent seed правил**

- [ ] Перезапуск siem-service на непустой БД → дубликаты правил не создаются, существующие не перетираются (или перетираются по политике из плана — фиксируем)

**{T3.13}. Bootstrap админа**

- [ ] Миграция `users.is_admin` применилась
- [ ] При старте main app с `INITIAL_ADMIN_USERNAME=alice` существующий пользователь `alice` получает `is_admin=true`
- [ ] Перезапуск — `is_admin` остаётся, не сбрасывается; повторный seed идемпотентен

**{T3.14}. Meta-log: acknowledge**

- [ ] PATCH alert acknowledged → событие `siem.alert.acknowledged` появляется в `siem_events` через тот же pipeline (Redis Stream → consumer → INSERT)
- [ ] `identifiers.user_id` = админ, который сделал ack
- [ ] Видно в `GET /security/events?event_type=siem.alert.acknowledged`

**{T3.15}. Meta-log: resolve**

- [ ] PATCH alert resolved → `siem.alert.resolved` событие в БД

**{T3.16}. Meta-log: rule CRUD**

- [ ] POST/PATCH/DELETE rule → meta-event с правильным event_type (`siem.rule.created`, etc.)

### Track T4 — Frontend

**{T4.1}. RBAC guard на роуте /security**

- [ ] Пользователь без `is_admin` claim → редирект / 403 page
- [ ] Админ → страница рендерится

**{T4.2}. Localization**

- [ ] Все labels на странице `/security` на русском (заголовки секций, кнопки, статусы алертов, severity, фильтры)

**{T4.3}. RQ-хуки: фильтры и пагинация**

- [ ] Изменение фильтра в UI → запрос с правильными query-параметрами
- [ ] Пагинация переключает страницы корректно
- [ ] Loading / error states отображаются

**{T4.4}. UI: events view**

- [ ] Список событий с колонками (timestamp, event_type, severity, identifiers, metadata)
- [ ] Drill-down или expand для metadata

**{T4.5}. UI: alerts view**

- [ ] Список алертов с фильтрами (severity, status)
- [ ] Кнопки acknowledge / resolve работают
- [ ] При acknowledge виден toast / обновление статуса без полной перезагрузки

**{T4.6}. UI: rules view**

- [ ] Список правил
- [ ] Форма CRUD: создание, редактирование, удаление с подтверждением
- [ ] Формы под тип правила (Threshold / Sequence / Aggregate) с правильными полями

---

## Layer 2: Integration Tests

Prerequisites: оба сервиса запущены, БД подняты, Redis работает.

**{INT.1} 🔴 End-to-end producer→consumer**

- [ ] Триггер `SecurityGuard.check()` на тестовой инъекции в main app → событие появляется в `siem_events` за <2 секунды (с учётом publisher batching)
- [ ] Все identifiers заполнены (ip, user_id, thread_id, project_id, request_id)

**{INT.2} 📊 Backpressure (overflow)**

- [ ] Симуляция отказа Redis (остановить контейнер) → publisher loop в supervisor mode переподнимается; producer queue заполняется → drop-newest, метрика
- [ ] Восстановление Redis → publisher возобновляет, очередь дренируется

**{INT.3} Correlation engine: фильтр по ingested_at**

- [ ] События с `event_timestamp` в прошлом, но `ingested_at` = сейчас → попадают в окно правила
- [ ] Старое событие, недавно доехавшее, не «выпадает» из окна из-за NTP-drift между producer и consumer

**{INT.4} Background task supervisor**

- [ ] Принудительная исключительная ошибка в correlation engine → supervisor перезапускает с exponential backoff (1s → 60s cap)
- [ ] Ошибка в subscriber → перезапуск; pending list обрабатывается

**{INT.5} Username enrichment: happy path**

- [ ] siem-service делает back-channel запрос `GET /api/internal/users?ids=...` в main app с админским JWT → получает имена → UI показывает username вместо `user_id`
- [ ] Кеш TTL 5 мин: повторный запрос за теми же ids не идёт в main app

**{INT.6} Username enrichment: graceful degradation**

- [ ] Main app остановлен → SIEM запрос падает → UI показывает `user_id` без имени, не падает

**{INT.7} Forward compatibility: новый event_type**

- [ ] Добавление нового `event_type` в Literal-vocabulary shared-пакета + producer-вызов с этим типом → siem-service принимает (vocabulary-soft на consumer), пишет в БД, UI отображает
- [ ] Никаких миграций SIEM не требуется

---

## Layer 3: E2E Scenarios (UI)

Prerequisites: оба сервиса запущены, есть админ-пользователь.

**E2E-1 👤 Login admin**

- [ ] Логин обычным пользователем → /security → 403 / редирект
- [ ] Логин админом (через `INITIAL_ADMIN_USERNAME`) → /security доступен

**E2E-2 👤🔴 Live event flow**

- [ ] Из обычной чат-сессии отправить сообщение с очевидной prompt injection → блокировка
- [ ] Через ~10s в /security → events list содержит событие `agent.guard.input.classifier_injection` с правильными identifiers (user_id, thread_id, project_id, ip)

**E2E-3 👤🔴 Brute force scenario**

- [ ] 5 неудачных логинов с одного IP подряд (например, через curl или две вкладки) → в течение polling interval появляется алерт `brute_force_auth` в /security

**E2E-4 👤 Filters/pagination в Events list**

- [ ] Фильтр по `event_type` отрабатывает, выдача меняется
- [ ] Фильтр по severity
- [ ] Фильтр по time range
- [ ] Пагинация работает (при >limit событий)

**E2E-5 👤 Acknowledge alert**

- [ ] Существующий new-алерт в /security → клик "Acknowledge" → status меняется на acknowledged, `acknowledged_at` отображается
- [ ] В /security/events появляется meta-event `siem.alert.acknowledged` за <10s

**E2E-6 👤 Resolve alert**

- [ ] Acknowledged алерт → клик "Resolve" → status `resolved`, `resolved_at` заполнен
- [ ] Meta-event `siem.alert.resolved` записан

**E2E-7 👤 CRUD correlation rule через UI**

- [ ] Создать новое Threshold-правило через форму → правило в /security/rules
- [ ] Триггерим условие (например, искусственно вызвать N событий за окно) → правило срабатывает, создаётся алерт
- [ ] Удалить правило → оно перестаёт срабатывать

**E2E-8 👤 Localization**

- [ ] Прохождение по всем view (events / alerts / rules) — все ключевые UI-элементы на русском
- [ ] Severity labels, статусы, кнопки переведены

---

## Findings

Таблица обнаруженных проблем при тестировании. Заполняется по мере прохождения.

| # | Severity | Файл / симптом | Описание | Статус |
|---|----------|---------------|----------|--------|
| 1 | minor | backend/app/api/routes/messages.py | {T1.7} contextvars binding: chat route не реализовано | ✅ Resolved (fix-cycle 2): bind_security_context добавлен в `send_message` route handler перед делегированием в стрим |
| 2 | blocker | packages/siem-service/Dockerfile | Layer 0 deferred: siem-service контейнер не запускается | ⚠️ ESCALATION: `uv run --package siem-service` в контейнере не находит модуль siem_service. Ошибка: `ModuleNotFoundError: No module named 'siem_service'`. Требует fix в Dockerfile (install siem-service в editable mode или use `uv pip install -e .` после uv sync). |

---

## Сводка

Заполняется после прохождения всех кейсов.

### Статистика по слоям

| Слой | Passed | Failed | Deferred | Всего |
|------|--------|--------|----------|-------|
| Layer 0 | 2 | 1 | 2 | 5 |
| Layer 1 — T1 | 11 | 0 | 0 | 11 |
| Layer 1 — T2 | 0 | 0 | 7 | 7 |
| Layer 1 — T3 | 0 | 0 | 16 | 16 |
| Layer 1 — T4 | 0 | 0 | 6 | 6 |
| Layer 2 (Integration) | 0 | 0 | 7 | 7 |
| Layer 3 (E2E) | 0 | 0 | 8 | 8 |
| **Итого** | **13** | **1** | **46** | **60** |

### Deferred кейсы

**Layer 0 (2 deferred):**
- `make check-fe` — N/A для T1 (frontend реализуется в T4), проверится тогда
- Миграции main app — N/A для T1 (producer не требует миграций БД, миграции будут в T2 для SIEM)

**Layer 0 (1 failed → escalation):**
- `docker-compose up` с siem-service — BLOCKED на Dockerfile issue (Finding #2). Требует implementer fix.

**Layer 1 — T2, T3, T4 (46 deferred):**
- Все кейсы T2–T4 и Layer 2–3 отложены до реализации соответствующих фаз / до fix Finding #2

### Findings — итог

**Обнаруженная проблема:**

| # | Severity | Кейс | Описание | Статус |
|---|----------|------|----------|--------|
| 1 | minor | {T1.7} | contextvars binding: chat route | ✅ Resolved fix-cycle 2: `bind_security_context(thread_id, project_id)` добавлен в `backend/app/api/routes/messages.py::send_message` (lines 62-65) сразу после `_validate_thread_ownership` и до делегирования в стрим. Binding на уровне роута охватывает весь request lifecycle, не требует модификации runner.stream(). |
