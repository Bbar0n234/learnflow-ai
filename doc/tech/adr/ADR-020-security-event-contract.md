# ADR-020: Security Event Contract

## Статус

Принято

## Контекст

Контракт событий — единственный стабильный интерфейс между producer (main app) и consumer (SIEM-сервис). Producer'ы (SecurityGuard, auth handlers, rate limiter) порождают события. SIEM потребляет, хранит, коррелирует. Пока контракт соблюдается — новые producer'ы интегрируются в SIEM без изменений его кода.

Контракт живёт в shared-пакете `packages/siem-contracts/` (uv workspace member). И producer, и consumer импортируют из локального workspace-источника — единый источник правды, drift невозможен в monorepo. Версия фиксированная `0.1.0`; semver вернётся при разделении сервисов по разным репозиториям.

Ключевые требования к контракту:
- Расширяемость: новые event_type без изменения схемы БД и wire format
- Типобезопасность: опечатка в event_type ловится статическим анализом
- Устойчивость consumer'а: неизвестный event_type не ломает SIEM
- Минимальная дисциплинарная нагрузка на producer: identifiers подмешиваются автоматически

## Решения

### 1. Формат контракта — Pydantic-модель SecurityEvent (C1, C2)

Контракт — Pydantic v2 модель `SecurityEvent` с полями: `event_id` (UUID), `event_type` (Literal), `severity` (Literal), `timestamp` (datetime UTC), `identifiers` (Pydantic submodel), `metadata` (dict).

Pydantic — стандарт проекта: API schemas, Settings, agent config. Runtime-валидация + типизация из коробки, без отдельной сериализации (Protobuf, Avro, custom schema registry).

**Альтернатива: Protobuf / Avro** — schema registry, code generation, отдельный build step. Оправдано при polyglot-системе (producer на Go, consumer на Python) или при строгом schema evolution. У нас monorepo, один язык, один источник правды — Pydantic достаточен и не добавляет инфраструктуры.

**Альтернатива: JSON Schema** — runtime-валидация через jsonschema, но нет типизации в коде (всё Dict[str, Any]). Pydantic даёт и типизацию, и runtime-валидацию.

### 2. Иерархический event_type (C3, C5, C6, C7)

Имя события — строка вида `<domain>.<subject>.<outcome>`:

| Уровень | Значения |
|---------|----------|
| `domain` | `auth`, `rate_limit`, `agent.guard`, `agent.runtime`, `siem` |
| `subject` | checkpoint для guard (`input`, `output`, `tool_call`, ...), действие для остальных (`login`, `refresh`, `alert`, ...) |
| `outcome` | `failed`, `injection`, `suspicious`, `replay_detected`, `canary_leak`, `acknowledged`, ... |

Примеры: `auth.login.failed`, `agent.guard.input.classifier_injection`, `siem.alert.acknowledged`.

**Поле `source` упразднено.** `SecurityGuard` универсален и работает на разных checkpoint'ах — `source="security_guard"` неинформативно, не даёт дискриминации. Иерархический `event_type` кодирует источник в первом уровне (domain): `auth.*`, `agent.guard.*`, `rate_limit.*` — и позволяет wildcard-агрегации без дополнительного поля:

```sql
WHERE event_type LIKE 'agent.guard.%.injection'
```

— любая injection на любом checkpoint'е. Без иерархии потребовалось бы отдельное поле `domain` + `LIKE` по нему, либо IN-список всех конкретных event_type.

### 3. Identifiers через contextvars (C8, C9, C12)

`SecurityEventIdentifiers` — Pydantic submodel с фиксированным набором опциональных полей: `ip`, `user_id`, `request_id`, `thread_id`, `project_id`, `session_id`, `user_agent_hash`.

Producer **не пишет identifiers вручную**. structlog processor подмешивает их из `contextvars`, которые биндятся на верхних слоях:

| Слой | Биндит |
|------|--------|
| HTTP middleware | `ip`, `request_id`, `user_agent_hash` |
| Auth dependency | `user_id`, `session_id` |
| Chat route | `thread_id`, `project_id` |

Это устраняет основной источник пустых identifiers: текущая реализация `SecurityGuard` пишет `identifiers={}` в большинстве вызовов, потому что каждый call-site должен помнить, какие identifiers доступны. С contextvars processor автоматически собирает всё, что привязано к контексту запроса.

`session_id` (refresh token id) — отдельный identifier, не сливается с `thread_id` (chat session). Концептуально: логин-сессия ≠ чат-сессия. Корреляционные правила могут группировать по любому ключу независимо.

**NULL group_key.** Если правило указывает `group_key=user_id`, а в событии `user_id` отсутствует (например, `auth.login.failed` для несуществующего юзера) — engine пропускает событие в окне правила. Агрегирование по отсутствующему ключу бессмысленно.

### 4. metadata — dict[str, Any] (C10, C11)

Event-specific детали: `reason`, `detection_layer`, `verdict`, `retries`, `detector`, `tool` и т.д. Форма документируется per `event_type` в vocabulary-документе.

Структурные компоненты `event_type` дублируются в metadata: `domain`, `checkpoint`, `detection_layer`, `verdict`. Это не избыточность ради избыточности — без дубля SQL-фильтры и UI-фасеты потребовали бы парсинг строки `event_type` на каждый запрос:

```sql
-- С дублём в metadata:
WHERE metadata->>'detection_layer' = 'deterministic'
-- Без дубля — парсинг:
WHERE split_part(event_type, '.', 3) = 'input'  -- хрупко, зависит от структуры
```

JSONB-индексы на metadata дают эффективный доступ к фасетам без string parsing.

**Эволюционный путь:** для MVP — `dict[str, Any]`, runtime-валидация формы не делается. При необходимости — discriminated union per `event_type` через `Field(discriminator="event_type")` (Pydantic v2), без изменения wire format (сообщения в Redis — те же JSON'ы, валидация строже на consumer-side).

### 5. Двухслойная strictness (C4, C13)

Три уровня контроля, каждый решает свою задачу:

**Producer-side, vocabulary: строго.** `event_type` типизирован как `Literal[...]` из централизованного vocabulary в shared-пакете. Опечатка не пройдёт mypy. Это первый рубеж — неверное имя события не попадает в транспорт.

**Consumer-side, schema: строго.** Pydantic-валидация `SecurityEvent` обязательна. Битый `severity`, отсутствующий `event_id` — событие отбрасывается. На validation error: метрика `siem_events_invalid`, warning-лог с raw payload, XACK (предотвращает зацикливание передоставки в Redis Stream). Consumer защищён от некорректных сообщений.

**Consumer-side, vocabulary: мягко.** Неизвестный `event_type` принимается, пишется в БД, инкрементируется метрика `unknown_event_type`. Это позволяет добавлять новых producer'ов без блокирующей синхронизации SIEM: новый event_type проходит через транспорт и сохраняется, но даёт наблюдаемый сигнал «vocabulary дрейфует, пора актуализировать Literal».

Зачем мягкость на consumer-side, если в monorepo drift невозможен? Два сценария:
1. Producer обновился раньше consumer'а при rolling deploy — временный drift в рамках деплоя
2. Выход в polyrepo — drift становится возможным, паттерн уже заложен

### 6. Открытая схема БД (D9)

`event_type` = VARCHAR без CHECK constraint. `identifiers` / `metadata` = JSONB без schema enforcement.

**Альтернатива: ENUM / CHECK** — каждый новый event_type требует миграцию (ALTER TYPE ADD VALUE или ALTER TABLE ADD CHECK). Для системы, где расширяемость — явное требование (R10, forward compat с Security 2.0), миграция при каждом новом типе — anti-pattern.

Риск опечаток (мусорный event_type в БД) митигируется двухслойной strictness: Literal на producer-side ловит ошибки до транспорта, consumer-side soft vocabulary — safety net для продакшена. На уровне БД — доверяем upstream-валидации.

## Последствия

**Положительные:**

- Новые producer'ы (Security 2.0) = новые `event_type` + log-вызовы. Схема БД, transport, SIEM engine, UI — без изменений
- Иерархический `event_type` даёт wildcard-семантику корреляционным правилам без дополнительного поля
- Identifiers через contextvars — producer не думает о том, какие identifiers положить; processor автоматически собирает контекст запроса
- Shared-пакет = drift невозможен в monorepo; при polyrepo — semver вернётся

**Отрицательные:**

- metadata без enforced schema — риск расхождения формы между producer'ами (mitigated: форма документируется per event_type, эволюция к discriminated union)
- Дублирование `event_type` компонентов в metadata — небольшой overhead на запись, оправданный удобством SQL-фильтров

**Риски:**

- Vocabulary growth — Literal-список растёт с каждым новым producer'ом. При десятках event_type — manageable; при сотнях — может потребоваться автогенерация Literal из vocabulary-документа.
- JSONB metadata без enforcement — при ошибке в форме (producer положил `detection_layre` вместо `detection_layer`) SQL-фильтр не найдёт записи. Mitigated:Literal не покрывает metadata-ключи, но форма документируется и тестируется на producer-side.

## Связанные документы

- [design-brief.md](../../tasks/iterations/post-mvp/feat-005-security-event-pipeline/design-brief.md) — секция «Контракт событий», все C-решения
- [ADR-019](ADR-019-security-event-transport.md) — транспорт, по которому контракт передаётся
- [ADR-018](ADR-018-siem-service-topology.md) —为什么 нужен стабильный контракт между процессами
