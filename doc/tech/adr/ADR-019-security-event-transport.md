# ADR-019: Security Event Transport

## Статус

Принято

## Контекст

SIEM — отдельный сервис (ADR-018). Producer (main app) и consumer (SIEM) работают в разных процессах. Нужен механизм доставки security-событий от producer к consumer.

Ключевые требования к транспорту:
- Процессы разные — in-process queue невозможна
- События не должны теряться при рестарте consumer'а
- Producer не должен блокироваться на сетевом I/O (hot path — обработка запросов)
- Delivery semantics — детерминированные, с контролем дубликатов

## Решения

### 1. Redis Streams + Consumer Group (D5)

**Транспорт — Redis Stream `security.events` + Consumer Group `siem-readers`.**

Producer пушит события через `XADD`. Consumer читает через `XREADGROUP` — это не просто «подписка на стрим», а кооперативная очередь с подтверждениями: пока consumer не подтвердил событие через `XACK`, оно числится в pending list группы.

**Рассмотренные альтернативы:**

**In-process queue** — невозможна после процессного разделения (ADR-018). Producer и consumer в разных процессах, in-proc queue не пересекает границу процесса.

**File tail** (structured log → file → SIEM tail'ит файл). Работает при локальном деплое (Docker bind mount). В распределённой системе — непонятно, как consumer на другом хосте читает файл producer'а. Хрупок при log rotation (consumer может потерять позицию), concurrent writers (несколько процессов пишут в один файл), и нет встроенных ack-семантик — consumer прочитал и упал, сообщение потеряно.

**RabbitMQ** — полноценный message broker с routing, exchanges, dead-letter queues. Функционал, который Rabbit даёт (complex routing, fanout, priority queues, message-level TTL), SIEM не нужен: один producer → один stream → один consumer group. Отдельная инфраструктура ради этого — overkill.

**Kafka** — distributed commit log с partitioning, replay, consumer groups. Оправдан при high throughput (millions events/sec), multiple consumer groups с разными интересами, distributed deployment. Для текущего масштаба (один host, один consumer, низкий throughput) — несоразмерный overhead: отдельный кластер (или минимум broker), ZooKeeper/KRaft, monitoring, ops.

**Выбор: Redis Streams.** Redis уже в стеке (sessions, cache). Streams предоставляют нужный функционал — durable append-only log, consumer groups с ack-семантикой, pending list, XCLAIM — без добавления новой инфраструктуры.

### 2. Delivery semantics — at-least-once с idempotent consumer (D6)

**Порядок:** `XREADGROUP` → validate → `INSERT ... ON CONFLICT(event_id) DO NOTHING` → `XACK`.

XACK стоит **после** успешной записи в БД, не до. Это даёт at-least-once: если consumer записал в БД и упал до XACK — сообщение остаётся в pending list, при рестарте передоставляется через XCLAIM. Повторная обработка — no-op: UNIQUE constraint на `event_id` предотвращает дубликат.

**Альтернатива: at-most-once** (`XACK` до обработки)

Если consumer ACK'нул сообщение и упал до записи в БД — сообщение потеряно навсегда (покинуло pending list). Для security-событий потеря недопустима.

**Альтернатива: exactly-once** — нативно не поддерживается Redis Streams (и большинством брокеров). Достигается как at-least-once + idempotent consumer — именно наш паттерн.

**Producer-side: best-effort до XADD.** Буфер producer'а (bounded queue, D17) — in-memory, при crash main app события в очереди теряются. Это осознанный trade-off: security-события — observability-данные, не транзакции. Потеря нескольких секунд буфера при crash основного app допустима. После XADD — durable в Redis (переживает crash consumer'а).

### 3. Producer-side mechanics (D17, D18)

structlog processor — sync-функция, вызывается из любого контекста (async route, sync stdlib log, фоновая корутина). Не может делать `await redis.xadd` — async-вызов из sync-контекста невозможен.

Мост sync→async через bounded `asyncio.Queue` (maxsize ~1000):

```
logger.warning(security_event=True, ...)
  → processor: build SecurityEvent (Pydantic), put_nowait (sync, non-blocking)
  → publisher_loop (async, supervised): await get() → await redis.xadd()
```

**Почему `put_nowait`, не `put` (awaitable):** processor — sync-функция, не может await. `put_nowait` либо успешен, либо моментально бросает `QueueFull`.

**Overflow-policy: drop-newest + метрика.** На overflow буфера downstream уже перегружен (Redis не успевает, или queue полна). Drop-newest консистентен с `MAXLEN ~` на Redis Stream (тоже drop-newest при переполнении). Drop-oldest потребовал бы ручного rotate буфера и не даёт преимуществ: старые события уже «в полёте», а новые (drop-newest) — те, что уже не влезут.

Publisher — background task в lifespan основного app, обёрнут в supervisor. На graceful shutdown — drain очереди с таймаутом.

### 4. Stream retention (D7)

`MAXLEN ~ 100 000` — approximate trimming при XADD. При typical load покрывает простой SIEM на часы. Параметр конфигурируется через env.

Approximate trimming (`~`) — Redis удаляет примерно 100k+1 записей, не точно. Это дешевле (не сканирует весь stream), приемлемо для нашей задачи.

## Последствия

**Положительные:**

- Нулевое добавление инфраструктуры — Redis уже в стеке
- Durable delivery — pending list + XCLAIM переживает рестарт SIEM
- Idempotent consumer — effectively exactly-once processing через `event_id` UNIQUE
- Hot path не блокируется — producer-side мост sync→async через bounded queue

**Отрицательные:**

- Best-effort на участке producer → Redis: crash main app теряет буфер (mitigated: security events — observability, не транзакции)
- Redis — единая точка отказа для транспорта (mitigated: Redis persistent, RDB/AOF; при недоступности — события теряются, SIEM показывает то, что успело дойти)

**Риски:**

- QueueFull при sustained load — если Redis не справляется, bounded queue переполняется, drop-newest теряет события. Наблюдаемость через метрику overflow count.
- Pending list growth при длительном простое SIEM — XCLAIM обработает backlog при старте, но если backlog > MAXLEN, старые события уже trimmed. Для MVP — допустимо (SIEM не должен быть offline часами).

## Связанные документы

- [ADR-018](ADR-018-siem-service-topology.md) — SIEM как отдельный сервис (motivation для кросс-процессного транспорта)
- [design-brief.md](../../tasks/iterations/post-mvp/feat-005-security-event-pipeline/design-brief.md) — секция Transport, Producer-side mechanics
