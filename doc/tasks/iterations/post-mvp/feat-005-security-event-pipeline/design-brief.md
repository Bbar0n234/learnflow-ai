# Design Brief: feat-005 — Security Event Pipeline

> **Design phase:** Phase 1 (Context & Scope)
> Секции Decisions, Architecture, Open Questions заполняются на Phase 2–5.

## Context

Security 1.0 (feat-004) реализовал трёхуровневую защиту от prompt injection: Input Guard, Prompt Hardening, Canary Output Check. Все компоненты логируют инциденты через `structlog` и отправляют observability-данные в Langfuse. Однако события безопасности **не сохраняются** в БД, **не коррелируются** между собой и **не отображаются** на админской панели — мониторинг возможен только через Langfuse Cloud.

### Product driver

Backlog P2 "Security Event Pipeline": единая подсистема сбора, хранения и корреляции security-событий из всех источников (auth, rate limiter, security guard). structlog processor как integration point, correlation engine с правилами, PostgreSQL tables, REST API + React monitoring page.

### Academic requirements

Курсовые требования к защищённым информационным системам: SIEM-подсистема + web-клиент управления событиями. Тезисно:

| # | Требование |
|---|-----------|
| R1 | Сбор событий безопасности из нескольких источников (auth, rate limiter, security guard) |
| R2 | Хранение в структурированном виде с нормализованной схемой |
| R3 | Корреляция по правилам с time-window логикой |
| R4 | Формирование инцидентов (алертов) из коррелированных событий |
| R5 | Web-UI мониторинга событий и алертов |
| R6 | CRUD над событиями/алертами с пагинацией и фильтрацией |
| R7 | Ролевая модель доступа (admin-only) к security-панели |
| R8 | Мета-логирование административных действий как security events |
| R9 | Локализация UI (RU) |
| R10 | Расширяемость: добавление новых правил корреляции и типов событий не требует изменения кода SIEM |

### Архитектурный инсайт

SIEM и Security 1.0/2.0 ортогональны. Security layers — **producers** (порождают события через structlog). SIEM — **consumer** (подхватывает, хранит, коррелирует, показывает). Пока контракт событий (event_type, severity, identifiers, metadata) сохраняется, новые security-компоненты автоматически интегрируются в SIEM без изменений его кода.

### Forward compatibility с Security 2.0

Добавление KS Write Guard, Tool Result Guard, Output Classifier и других компонентов Security 2.0 потребует лишь новых `event_type` в log-вызовах. Архитектура SIEM, схема БД, correlation engine и UI не требуют изменений.

## Scope

### MVP (feat-005)

| Компонент | Что делает | Req |
|-----------|------------|-----|
| **Event Collection** | structlog processor перехватывает log-вызовы с маркером `security_event=True`, записывает в `security_events` | R1 |
| **Normalization** | Единая схема: event_type, severity, source, timestamp, identifiers (JSONB), metadata (JSONB) | R2 |
| **Storage** | PostgreSQL: `security_events`, `security_alerts`, `correlation_rules` | R2 |
| **Correlation Engine** | asyncio background task, правила с time window + grouping по произвольному идентификатору (IP, user_id, thread_id) или без группировки | R3 |
| **Alerting** | `security_alerts`: rule_id, severity, matched events, status workflow (new → acknowledged → resolved) | R4 |
| **Monitoring UI** | REST API `/security/` (events, alerts — pagination, filters) + React страница `/security` (список событий + алертов) | R5, R6 |
| **RBAC + meta-logging** | Admin-only доступ к `/security`; CRUD для alerts (acknowledge, resolve); мета-логирование CRUD-операций как security events | R7, R8 |
| **Localization** | UI-labels на странице `/security` на русском | R9 |
| **Rules extensibility** | Добавление новых correlation rules и новых event_type не требует изменения кода SIEM. Конкретный механизм (таблица правил / seed-конфиг / CRUD API) определяется на Phase 2 | R10 |

### Deferred to feat-007 (SIEM Extensions)

Продуктовые улучшения, не требуемые для MVP, реализуются отдельной итерацией:

- Dashboard & Metrics — агрегатные endpoint'ы + графики (events/hour, severity distribution, trends)
- Basic response actions — manual-trigger блокировка (ban IP / user) из алерта админом
- Расширенный Search — полнотекстовый поиск, timeline-view, drill-down
- Notifications — in-app уведомления при новых алертах
- Export & Reporting — CSV/PDF экспорт

### Out of scope (not planned)

Threat Intelligence, UEBA, SOAR automation, Log Forwarding, Compliance Framework mapping, Agent-based Collection — overkill для текущего масштаба, не планируются.

### Сознательно заложено для расширения

Архитектура MVP проектируется так, чтобы feat-007 функции добавлялись без перелопачивания:

| Что | Как закладывается |
|-----|-------------------|
| Dashboard | JSONB `identifiers` + `metadata` → любые SQL-агрегаты; REST API с pagination + filters → агрегатный эндпоинт поверх тех же таблиц |
| Response actions | `security_alerts.status` workflow расширяется экшеном; manual trigger из UI создаёт запись в отдельной таблице блокировок, auth middleware читает её — SIEM остаётся точкой наблюдения, не исполнения |
| Search | `metadata` JSONB → GIN index; detail-эндпоинт = `GET /security/events/:id` |

## Функциональная карта SIEM

### Phase 1 — MVP (feat-005)

| # | Функция | Суть |
|---|---------|------|
| 1 | Event Collection | structlog processor — единственная точка входа; нулевая инвазивность в бизнес-код |
| 2 | Normalization | Единая схема: event_type (str), severity (enum), source (str), timestamp, identifiers (JSONB), metadata (JSONB) |
| 3 | Storage | PostgreSQL: `security_events`, `security_alerts`, `correlation_rules` |
| 4 | Correlation Engine | asyncio background task, SQL time-window queries. Типы правил: Threshold, Sequence, Aggregate |
| 5 | Alerting | `security_alerts` status workflow (new → acknowledged → resolved) |
| 6 | Monitoring UI | REST API `/security/` (pagination, filters) + React `/security` (events list + alerts list) |
| 7 | RBAC + meta-logging | Admin-only доступ; CRUD для alerts; мета-логирование |
| 8 | Localization | RU labels в UI |
| 9 | Rules extensibility | Новые правила/event_type — без изменения кода SIEM |

### Phase 2 — feat-007 (SIEM Extensions)

Dashboard & Metrics, Basic response actions (ban IP/user), расширенный Search, Notifications, Export. Реализуются отдельной итерацией после MVP.

### Not planned

Threat Intelligence, UEBA, SOAR automation, Log Forwarding, Compliance Frameworks, Agent-based Collection — overkill для масштаба.

### Границы ответственности

В MVP (Phase 1) SIEM — чистый observer:

```
SIEM НЕ:                              SIEM:
- Блокирует запросы                   - Наблюдает за security-компонентами
- Валидирует ввод                     - Запоминает события
- Проверяет вывод LLM                 - Находит паттерны (корреляция)
- Управляет MCP/skills                - Сигнализирует админу
- Харденит промпты                    - Показывает картину в UI
```

В Phase 2 (feat-007) добавятся manual response actions (ban из UI). Это сознательное расширение ответственности под продуктовую необходимость, не нарушение жёсткого принципа — индустриальные SIEM (Splunk, Sentinel, Elastic) штатно включают SOAR-функции. Сепарация observer/responder важна как дисциплина MVP, не как догма.

## Контракт событий

Схема события — единственный stability point между producers (Security 1.0/2.0) и consumer (SIEM). Пока эта схема соблюдается, SIEM работает с любым количеством security-компонентов.

### Security Event Schema

```python
class SecurityEvent:
    event_type: str          # "auth_failure", "injection_blocked", "canary_leak",
                             # Security 2.0: "ks_write_blocked", "tool_injection", ...
    severity: str            # "info" | "warning" | "critical"
    source: str              # "auth" | "security_guard" | "rate_limiter" | "ks_guard" | ...
    timestamp: datetime      # auto (UTC)
    identifiers: dict        # JSONB — расширяемый набор:
                             #   {"ip": str | null,
                             #    "user_id": str | null,
                             #    "thread_id": str | null,
                             #    "session_id": str | null}
    metadata: dict           # JSONB — произвольные детали:
                             #   {"reason": str, "verdict": str, "model": str, ...}
```

### Integration Point: structlog

```python
# В бизнес-коде (SecurityGuard, auth, rate limiter):
logger.warning(
    "injection_blocked",
    security_event=True,
    event_type="injection_blocked",
    severity="critical",
    source="security_guard",
    identifiers={"ip": client_ip, "user_id": user_id, "thread_id": thread_id},
    metadata={"reason": "llm_classifier", "verdict": "INJECTION"},
)

# structlog processor перехватывает вызовы с security_event=True
# и записывает в security_events. Бизнес-код не знает о SIEM.
```

### Корреляция: группировка

Корреляция связывает события по произвольному идентификатору — не только IP. Конкретный ключ определяется правилом:

| Тип группировки | Ключ | Пример правила |
|----------------|------|----------------|
| По IP | `identifiers->>'ip'` | >=5 auth_failure за 60 сек с одного IP |
| По user_id | `identifiers->>'user_id'` | >=3 injection_attempt за 5 мин от одного user |
| По thread_id | `identifiers->>'thread_id'` | Многоходовая атака в рамках сессии |
| Глобальная | нет GROUP BY | >=10 warning-событий за 5 мин (массовая аномалия) |

### Расширение при добавлении Security 2.0

```
Новый компонент Security 2.0:
1. Добавить log-вызов с security_event=True и новым event_type
2. (Опционально) Добавить correlation rule для нового event_type
3. Всё. SIEM автоматически подхватывает.
```

Схема БД, processor, correlation engine, REST API, UI — **не требуют изменений**.

### Типы правил корреляции

| Тип | Логика | Пример |
|-----|--------|--------|
| **Threshold** | COUNT(event_type) >= N за T сек по ключу K | >=5 auth_failure за 60 сек с одного IP |
| **Sequence** | Событие A, затем событие B за T сек по ключу K | auth_failure + injection за 10 мин с одного IP |
| **Aggregate** | COUNT(*) >= N за T сек (глобально, без группировки) | >=10 warning-событий за 5 мин |

Новые типы правил добавляются расширением correlation engine, но MVP покрывает эти три.

## Decisions

> → заполняется на Phase 2
>
> Ожидаемые темы: отдельный сервис vs модуль бэкенда, polling vs event-driven, механизм расширяемости правил (R10: таблица в БД / YAML-конфиг / CRUD API / комбинация), retention/TTL, партиционирование.

## Architecture

> → заполняется на Phase 3

## Open Questions

> → заполняется на Phase 5

## Scope Boundaries

В feat-005 **явно НЕ входит:**

- Блокировка, валидация или модификация запросов — это SecurityGuard (Security 1.0/2.0)
- Замена Langfuse для LLM observability — Langfuse остаётся source of truth для traces, prompts, generations
- Response actions (ban IP/user, automated mitigation) — отложено в feat-007
- Dashboard, расширенный Search, Notifications, Export — отложены в feat-007
- Внешние интеграции (Syslog, CEF, external SIEM forwarding)
- ML-based anomaly detection (UEBA)
- Threat Intelligence, Compliance Frameworks, SOAR automation
- Изменение существующего security-кода (SecurityGuard, prompt_builder, runner) — только добавление `security_event=True` к существующим log-вызовам

## References

### Research docs

- [architecture.md](../../../../security/architecture.md) — архитектура Security 1.0: три слоя защиты
- [observability.md](../../../../tech/observability.md) — Langfuse observability, tracing, security scores
- [conventions.md](../../../../tech/conventions.md) — logging conventions (structlog)
- [ADR-017](../../../../tech/adr/ADR-017-prompt-injection-defense.md) — Prompt Injection Defense
- [backlog.md](../../../../backlog.md) — P2 Security Event Pipeline

### Iteration artifacts

- [design-brief.md](design-brief.md) — этот документ
