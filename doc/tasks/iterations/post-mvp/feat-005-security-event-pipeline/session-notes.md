# Session Notes: feat-005 — Security Event Pipeline

> Временный документ. Контекст и решения из архитектурной сессии.
> После заполнения design-brief Phase 2–5 — удалить, перенеся актуальное в бриф.

## 1. Приоритеты и мотивация

- Security Event Pipeline — приоритетнее Security 2.0 по срокам. Security 2.0 планируется позже, в ближайшие недели.
- SIEM — не «работа в стол». Закрывает реальную нишу, которую Langfuse не покрывает:
  - Локальная агрегация security-событий (не зависящая от cloud-сервиса)
  - Корреляция между источниками (auth + security guard + rate limiter) — Langfuse не коррелирует
  - Админский UI без необходимости доступа к Langfuse
  - Автоматическое обнаружение паттернов атак (time-window rules)
- Langfuse остаётся source of truth для LLM traces, prompts, generations. SIEM — complementary слой на другом уровне абстракции.

## 2. Архитектурная модель: Producer / Consumer

- Security layers (1.0/2.0/3.0) — **producers**: порождают события через structured logging. Не знают о SIEM.
- Security Event Pipeline — **consumer**: подхватывает события, хранит, коррелирует, показывает. Не знает о конкретных security-компонентах.
- structlog — единая шина (integration point). Processor перехватывает log-вызовы с маркером, пишет в БД. Бизнес-код не меняется.
- Контракт событий — единственный stability point между producers и consumer. Пока схема (event_type, severity, identifiers, metadata) соблюдается — всё работает.

## 3. Функциональные границы SIEM

**SIEM делает:**
- Наблюдает за security-компонентами
- Запоминает события в PostgreSQL
- Находит паттерны (корреляция по time window + identifiers)
- Сигнализирует админу (алерты, мониторинг-страница)

**SIEM НЕ делает:**
- Блокирует запросы (это SecurityGuard)
- Валидирует ввод (это Input Guard)
- Проверяет вывод LLM (это Output Classifier)
- Управляет MCP/skills (это Tool Result Guard)
- Харденит промпты (это Prompt Hardening)

Это другой слой ответственности — observability & monitoring, не protection.

## 4. Корреляция: принцип работы

- Группировка по произвольному идентификатору — не только IP. Конкретный ключ определяется правилом:
  - По IP → brute force detection
  - По user_id → targeted user attack
  - По thread_id → multi-turn attack в рамках сессии
  - Глобальная (без GROUP BY) → массовая аномалия (много warning-событий)
- Типы правил:
  - **Threshold**: N событий типа X за T секунд по ключу K (>=5 auth_failure за 60 сек с одного IP)
  - **Sequence**: событие A, затем событие B за T секунд по ключу K (auth_failure + injection за 10 мин)
  - **Aggregate**: N событий любой категории за T секунд глобально (>=10 warning за 5 мин)
- Правила гибкие: одни привязаны к идентификатору, другие агрегируют без группировки. Настраивается per rule.
- SIEM связывает события по любому идентификатору, по которому можно сгруппировать scope событий — здесь вариативность.

## 5. Scope: что делаем, что закладываем, что не делаем

### feat-005 — MVP (закрывает academic R1–R10 + backlog P2)

| Компонент | Суть | Req |
|-----------|------|-----|
| Event Collection | structlog processor — единственная точка входа, нулевая инвазивность | R1 |
| Normalization | Единая схема: event_type, severity, source, timestamp, identifiers (JSONB), metadata (JSONB) | R2 |
| Storage | PostgreSQL: security_events, security_alerts, correlation_rules | R2 |
| Correlation Engine | asyncio background task, SQL time-window queries, 3 типа правил | R3 |
| Alerting | security_alerts с status workflow: new → acknowledged → resolved | R4 |
| Monitoring UI | REST API `/security/` (pagination, filters) + React `/security` | R5, R6 |
| RBAC + meta-logging | Admin-only доступ; CRUD для alerts; мета-логирование CRUD-операций | R7, R8 |
| Localization | RU labels в UI | R9 |
| Rules extensibility | Новые правила/event_type — без изменения кода SIEM (механизм — Phase 2) | R10 |

### feat-007 — SIEM Extensions (отдельная итерация)

Dashboard & Metrics, Basic response actions (manual ban IP/user из UI), расширенный Search, Notifications, Export.

### Not planned

UEBA, SOAR automation, Threat Intelligence, Log Forwarding, Compliance Frameworks, Agent-based Collection — overkill для масштаба проекта.

## 6. Расширяемость при добавлении Security 2.0

**Что НЕ нужно менять при Security 2.0:**
- Схему security_events (metadata = JSONB, принимает любые данные)
- Схему security_alerts (ссылается на events, не зависит от типа)
- structlog processor (универсален, работает с любым event_type)
- Корреляционный движок (правила = данные в таблице)
- REST API (параметр event_type для фильтрации — работает для новых типов)
- React-страницу (тип — просто колонка в списке)

**Что нужно будет добавить (минимум):**
- Новые значения event_type в log-вызовах нового security-компонента
- (Опционально) Новые correlation rules — INSERT в таблицу, без деплоя

**Новый компонент Security 2.0 = 3 шага для SIEM-интеграции:**
1. Добавить log-вызов с `security_event=True` и новым event_type
2. (Опционально) Добавить correlation rule для нового event_type
3. Всё.

## 7. Интеграционные точки для forward compatibility

5 точек, заложенных под расширение уже на этапе проектирования:

| Точка | Что закладываем | Что это даст потом |
|-------|----------------|--------------------|
| Схема security_events | JSONB identifiers + metadata | Dashboard, Search — новые SQL-запросы |
| Correlation rules | Таблица в БД, не хардкод | Новые правила — INSERT, без деплоя |
| Alert workflow | status enum (new/acknowledged/resolved) | Notifications — триггер на status=new |
| REST API | Роутер `/security/` с pagination + filters | Dashboard = агрегатный эндпоинт |
| structlog processor | Универсальный, не привязан к event_type | Любой новый source проходит автоматически |

## 8. Batch 1 — Фундаментальные решения (рекомендации, не утверждены)

### D1: Где живёт код?

**Рекомендация:** модуль внутри backend (`app/security_pipeline/`)

Аргументы:
- Нулевой операционный overhead (нет отдельного сервиса)
- Shared PostgreSQL connection pool
- Простой деплой (один контейнер)
- Shared auth middleware (RBAC бесплатно)

Альтернатива: отдельный сервис (overkill для MVP, нужен свой Dockerfile, compose, CI, connection pool, auth middleware).

Архитектор обозначил вопрос: нужно прикинуть на этапе проектирования.

### D2: Как хранятся правила корреляции?

**Рекомендация:** таблица `correlation_rules` в PostgreSQL

Аргументы:
- Runtime-добавление правил без деплоя
- CRUD API естественно ложится (требуется для RBAC-части)
- Seed initial rules при старте

Альтернативы:
- YAML config — нужен рестарт для изменений, нет CRUD API
- Хардкод — негибко, violates purpose SIEM

### D3: Насколько строга схема событий?

**Рекомендация:** открытая схема — event_type = VARCHAR без CHECK, identifiers/metadata = JSONB без schema валидации

Аргументы:
- Security 2.0 добавляет типы без миграций
- Processor универсален

Risk: опечатка в event_type → мусорная запись.
Mitigation: logging convention + documented known types.

Альтернатива: ENUM/whitelist — каждый новый тип = миграция. Anti-pattern для расширяемой системы.

## 9. Открытые вопросы (предстоит решить)

### Batch 2 — Runtime

- **D4:** structlog processor — sync write в БД сразу, или async buffer/batch?
- **D5:** Correlation engine — polling с интервалом, или event-driven (trigger при каждой записи)?
- **D6:** Alert deduplication — повторное срабатывание того же правила по тому же ключу → новый алерт или обновление существующего?

### Batch 3 — Data lifecycle

- **D7:** Retention / TTL — автоочистка старых событий? Какой период?
- **D8:** Партиционирование security_events по времени, или одна таблица?

### Batch 4 — Code structure

- **D9:** Package structure — директории, модули, naming
- **D10:** Frontend — конкретные компоненты и layout на /security

## 10. Разбиение на две итерации: feat-005 + feat-007

Мотивация разбивать SIEM на две фичи:

- **feat-005 (Core)** закрывает academic-требования R1–R10 + backlog P2. Скоуп минимальный, но полностью функциональный: pipeline работает end-to-end, события собираются, коррелируются, алерты отображаются, admin управляет через CRUD. Цель — быстро дойти до merge.
- **feat-007 (SIEM Extensions)** — продуктовые улучшения поверх core: Dashboard & Metrics, manual response actions (ban IP/user из UI), расширенный Search, Notifications, Export. Не блокируют закрытие academic-требований, но нужны для полноценного UX.

### Observer-only принцип — не догма

Строгая сепарация producer/consumer в MVP — полезная дисциплина (forward compat с Security 2.0, нулевая инвазивность в бизнес-код). Но жёстко настаивать на observer-only для всех фаз нет оснований: индустриальные SIEM (Splunk, Sentinel, Elastic) включают SOAR-функции штатно. В feat-007 добавление manual response actions — сознательное расширение под продуктовую необходимость, не нарушение архитектурного инварианта.

Архитектурный шов: блокировка — отдельная таблица `security_blocks` + auth middleware. SIEM-модуль пишет в неё через action из UI, middleware читает. SIEM остаётся точкой наблюдения, executor — auth middleware. Модель producer/consumer сохраняется на другом уровне.

## 11. Документная дисциплина при разбиении

- feat-007 не получает отдельный design-brief-заглушку на этом этапе — только пункт в `tasklist-post-mvp.md` как planned iteration
- При переносе P2 Security Event Pipeline из backlog в tasklist — удаляем из `backlog.md` (tasklist становится новым домом)
- design-brief и session-notes feat-005 ссылаются на feat-007 только как на «deferred» — без содержательной разработки
