# ADR-021: SIEM Correlation Engine

## Статус

Принято

## Контекст

События собраны, нормализованы и сохранены в `siem_events`. Следующий шаг — обнаружение паттернов атак: brute force (много failed logins с одного IP), targeted attack (login failure → injection от того же user), массовые аномалии (волна injection-ов).

Correlation engine — фоновая задача SIEM-сервиса, которая периодически анализирует поток событий и порождает алерты при совпадении правил. Правила хранятся в БД как данные, не как код — runtime-добавление без деплоя (R10).

## Решения

### 1. Polling SQL queries, не event-driven (D11)

Engine — asyncio background task, polling-цикл каждые ~10 секунд (configurable). На каждой итерации загружает активные правила из `correlation_rules` и выполняет SQL time-window queries по `siem_events`.

**Альтернатива: event-driven** (LISTEN/NOTIFY или trigger при каждой записи)

Каждая INSERT в `siem_events` триггерит проверку затронутых правил. Преимущество — нулевая latency: алерт возникает сразу при совпадении. Недостатки:

- **Сложность:** event-driven correlation требует state machine для time-window логики. Правило «≥5 событий за 60 сек» — нужно хранить промежуточный счётчик per (rule, group_key), обновлять при каждом событии, сбрасывать по таймауту. При polling — один SQL-запрос, БД делает агрегацию сама.
- **Determinism:** polling фильтрует окно по `ingested_at` (consumer-side timestamp) — детерминированно, не зависит от задержек транспорта. Event-driven считает события по мере поступления — при задержке транспорта окно может «размазаться».
- **LISTEN/NOTIFY** — PostgreSQL-специфичный механизм, требует отдельного connection для прослушивания, не работает через пул соединений (нужен dedicated listener). Добавляет coupling на конкретную БД.

Latency ~10 сек приемлема: SIEM — observability-слой, не real-time protection. Между атакой и алертом проходит до 10 сек — это нормально для мониторинга, недопустимо для blocking (но blocking — не задача SIEM).

### 2. Три типа правил — Threshold, Sequence, Aggregate (D12)

**Threshold:** `COUNT(event_type) >= N` за `T` секунд по ключу `K`. Группировка по identifier (ip, user_id, thread_id).

```sql
SELECT identifiers->>'ip' AS group_key, COUNT(*) AS cnt
FROM siem_events
WHERE event_type = 'auth.login.failed'
  AND ingested_at > now() - interval '60 seconds'
GROUP BY identifiers->>'ip'
HAVING COUNT(*) >= 5
```

Пример: ≥5 `auth.login.failed` за 60 сек с одного IP → brute force alert.

**Sequence:** событие A, затем событие B за `T` секунд по ключу `K`. Stateless self-join:

```sql
SELECT a.identifiers->>'ip' AS group_key, ...
FROM siem_events a
JOIN siem_events b ON a.identifiers->>'ip' = b.identifiers->>'ip'
  AND b.ingested_at > a.ingested_at
  AND b.ingested_at < a.ingested_at + interval '600 seconds'
WHERE a.event_type = 'auth.login.failed'
  AND b.event_type = 'agent.guard.input.classifier_injection'
  AND a.ingested_at > now() - interval '600 seconds'
```

Пример: `auth.login.failed` → `agent.guard.input.classifier_injection` за 10 мин с одного IP → targeted attack alert.

**Aggregate:** `COUNT(*) >= N` за `T` секунд по фильтру, без GROUP BY. Массовая аномалия без привязки к конкретной сущности.

```sql
SELECT COUNT(*) AS cnt
FROM siem_events
WHERE event_type LIKE 'agent.guard.%.injection'
  AND ingested_at > now() - interval '300 seconds'
HAVING COUNT(*) >= 10
```

Пример: ≥10 injection-событий за 5 мин глобально → injection spike alert.

**Aggregate = Threshold с `group_key=NULL`.** В engine — единая стратегия с опциональным `GROUP BY`. Различение Threshold / Aggregate сохраняется в UX и документации (Aggregate естественнее описывает «массовая аномалия»), но кодово — один path.

Sequence использует self-join. Повторные срабатывания на одну пару (A, B), пока окно не сдвинется, дедуплицируются через open-alert policy (D13) — не через SQL DISTINCT (который может убрать легитимные повторы).

### 3. Правила как данные (D8)

`correlation_rules` — таблица в PostgreSQL. Поля: `id`, `name`, `rule_type` (threshold/sequence/aggregate), `event_type_filter`, `threshold` (N), `window_seconds` (T), `group_key` (nullable — NULL = Aggregate), `severity`, `is_active`, конфигурация sequence-правил (event_type_a, event_type_b).

CRUD через REST API SIEM-сервиса (admin-only). Idempotent seed при старте — baseline rules (~6 правил: brute_force_auth, password_spray, injection_spike, targeted_user_attack, multi_turn_suspicious, mcp_compromise) гарантированно присутствуют после миграций.

Новое правило = `INSERT INTO correlation_rules`. Без деплоя, без рестарта. Engine подхватывает на следующем polling-цикле (загружает активные правила каждые ~10 сек).

**Альтернатива: YAML config / хардкод** — YAML требует рестарта для применения (или watch-механику), хардкод — негибко, нарушает R10 (расширяемость без изменения кода). Таблица + CRUD — естественное решение для admin-панели.

### 4. Open-alert dedup с возрастным лимитом (D13)

Когда correlation engine находит совпадение правила, он порождает `AlertCandidate` (rule_id, group_key, severity, matched_events). Alert deduper решает: append к существующему open alert или создать новый.

Логика:

1. Найти open (status = `new` или `acknowledged`) alert с тем же `rule_id` + `group_key`
2. Если найден **и** младше 24 часов → **append**: инкремент `trigger_count`, расширить `timeline` (массив timestamp'ов), обновить `last_triggered_at`
3. Если не найден **или** старше 24 часов **или** status = `resolved` → **создать новый** alert

**Зачем возрастной лимит 24h:** без него один brute force, продолжающийся 3 дня, породил бы один гигантский alert со счётчиком 10 000. С лимитом — каждый день новый alert, каждый со своим scope. 24 часа — эмпирический tradeoff между «слишком много мелких алертов» и «один бесконечный мега-алерт».

**Status workflow:** `new` → `acknowledged` → `resolved`. Admin решает через UI (PATCH /alerts/:id). Acknowledged alert продолжает получать append (админ видел, но атака продолжается). Resolved alert — закрыт, следующее срабатывание создаёт новый.

Решает сигнал/шум для одного админа без 24/7 SOC-команды: вместо 50 отдельных алертов на один brute force — один alert со счётчиком «50 срабатываний за 10 минут» и timeline.

## Последствия

**Положительные:**

- Polling — простая, детерминированная модель. Один SQL-запрос per правило per цикл. Нет state machine, нет LISTEN/NOTIFY coupling.
- Правила как данные — runtime-extensibility без деплоя (R10)
- Open-alert dedup — manageable количество алертов для единственного админа
- Три типа правил покрывают практические сценарии MVP; стратегии расширяемы при добавлении новых типов

**Отрицательные:**

- Latency до 10 сек между событием и алертом — приемлемо для observability, недопустимо для real-time protection (SIEM не занимается protection)
- Sequence self-join — потенциально дорогой при большом объёме событий. Mitigated: фильтрация по `ingested_at` ограничивает scan, партиционирование (если добавится) — дополнительно.
- Polling load — N SQL queries каждые 10 сек (N = количество активных правил). При ~6 baseline rules — negligible. При росте — configurable interval + оптимизация queries.

**Риски:**

- Sequence false positives: self-join за широкое окно может связать несвязанные события. Mitigated: группировка по identifier (IP, user_id) сужает scope; админ видит matched events в alert detail и может оценить relevance.
- Age limit 24h — эмпирическое значение. Может потребовать tuning: короткий лимит → больше алертов, длинный → раздутие одного alert. Настраиваемый параметр.

## Связанные документы

- [design-brief.md](../../tasks/iterations/post-mvp/feat-005-security-event-pipeline/design-brief.md) — секции «Типы правил корреляции», «Correlation Engine», decisions D8, D11-D13
- [ADR-020](ADR-020-security-event-contract.md) — контракт событий, по которому engine строит SQL-фильтры
- [ADR-018](ADR-018-siem-service-topology.md) — SIEM как отдельный процесс с выделенным event loop для background tasks
