# Tasklist: Dogfooding (Фаза 5b → показ преподавателям)

## Контекст

Фаза 5b: честный догфудинг через продукт и подготовка к показу преподавателям (~середина августа — сдвиг влево с ~сентября: полная занятость на проекте в августе; нулевой пилот Фазы 7). Рама догфудинга — авторский мини-курс «Защита LLM-приложений», первый получатель — реальный преподаватель (детали приватно, `doc/strategy.local.md`); обоснование и полка побочных выходов курса — [roadmap.md](../product/roadmap.md) § Фаза 5b.

Тасклист покрывает путь от текущего состояния (накопленный `develop` не задеплоен в `main`) до показа: закрытие версии и деплой, инструменты догфудинга (вход файлов, PDF, слайды, модели), execution runtime как общий фундамент выходных форматов (feat-011), ГОСТ-скилл (feat-012), OAuth. Кастомные скиллы, web search, voice — за гейтом показа.

**Источник:** [backlog.md](../backlog.md) — триаж при планировании фазы.
**Зависимости:** Post-MVP ([tasklist-post-mvp.md](tasklist-post-mvp.md)) — закрыт; его feat-001 (Chat UX) перенесена сюда (feat-002), feat-007 (SIEM Extensions) заморожена решением по SIEM kill-switch (см. chore-001).

## Легенда

- 📋 Planned
- 🚧 In Progress
- ✅ Done
- ⏸️ Paused
- ❌ Cancelled

## Overview

| Итерация | Алиас | Статус | Scope | Закрывает |
|----------|-------|--------|-------|-----------|
| feat-001 | A | ✅ Done | cross-cutting | Видимость работы агента: карта событий, live-фазы, reasoning-стрим, след tool-вызовов, security_block в UI |
| chore-001 | B | ✅ Done | cross-cutting | Prod-closing: kill-switch LLM-защиты + SIEM kill-switch, X-Forwarded-For, прод-образы без dev-deps; merge develop → main + деплой |
| feat-002 | C | ✅ Done | cross-cutting | Chat UX: первое сообщение вместо title, auto-title отдельным модулем, удаление и переименование чатов |
| feat-003 | D | ✅ Done | agent | Модели: cost-optimal подбор по внешним бенчмаркам, whitelist 5+, pricing seed в Langfuse |
| feat-004 | E | 🔀 Merged → feat-011 | cross-cutting | File attachments: поглощена feat-011 — workspace снял хранение, runtime снял ingestion; контракт в design-brief feat-011 § Вложения пользователя |
| feat-005 | F | 📋 Planned | backend | PDF-экспорт: замена wkhtmltopdf, рендер формул, фирменный стиль |
| feat-006 | G | 📋 Planned | agent | Генерация слайдов: spike → скилл/интеграция (паттерн ADR-026) |
| feat-007 | H | 📋 Planned | cross-cutting | Кастомные скиллы пользователя + страница библиотеки скиллов |
| feat-008 | I | ✅ Done | cross-cutting | OAuth (Яндекс ID для РФ, + Google/GitHub вне РФ — гео-разделение по 149-ФЗ) + функциональный каркас страницы `/login` (брендовый дизайн — feat-013) |
| feat-009 | J | ✅ Done | infra | Web search MCP: замена Firecrawl на Jina AI (hosted) |
| feat-010 | K | 📋 Planned | cross-cutting | Voice input (STT) |
| feat-011 | L | ✅ Done | cross-cutting | Execution runtime: изолированное выполнение кода/CLI + файловый workspace + file attachments (поглотила E) — общий фундамент PDF (F), слайдов (G), ГОСТ-скилла (M) |
| feat-012 | M | 📋 Planned | agent | ГОСТ-скилл: bundle-скилл оформления студенческих работ по ГОСТ 7.32 (.docx) — оффер для студенческой волны |
| feat-013 | N | ✅ Done | frontend | UI/UX polish: пакет мелких правок — сайдбар-баг, скроллбары, loading/error, ModelSelector, empty-states, inline-edit имени проекта, 404-экран, дизайн auth-экранов, токен `--success`, владелец состояния стрима |

## Порядок и приоритеты

```
Авг W1     Финал A/B/C → merge develop → main → ДЕПЛОЙ (прод живой)
Авг W1–W2  feat-011 (L, runtime + workspace + attachments — фундамент F/G/M; поглотила E)
           ► СТАРТ ДОГФУДИНГА (лекция №1 мини-курса) — как только L готова
Авг W2     feat-005 (F, PDF — на runtime) ── feat-006 (G, слайды — на runtime)
Авг W2–W3  feat-012 (M, ГОСТ-скилл — на L) ── feat-008 (I, OAuth)
           → предпоказная полировка (feat-013) + бренд-кит (design-branding feat-005)
           → ПОКАЗ ПРЕПОДАВАТЕЛЯМ (~середина августа)
Далее      студенческая волна (оффер ГОСТ; гейт — потолок затрат, backlog Backend)
           feat-007 (H) ── feat-009 (J) ── feat-010 (K) ── maintenance [dogfood]
```

- **Минимум к показу:** A–G + I + L (runtime) + M (ГОСТ-скилл) — решение архитектора: показ только с полным набором выходных форматов и ГОСТ-скиллом. H (кастомные скиллы), J (web search), K (voice) — за гейтом показа.
- **L перед F/G/M:** PDF, слайды и ГОСТ-сборка строятся на контракте runtime — проектируется один раз, не три костыля. E независима от L, допускает параллель.
- **A → C последовательно:** Chat UX может потребовать SSE-событие `title_updated` — стрим-контракт перерабатывается в A, не трогаем его дважды.
- **Догфудинг стартует после E** (без входа материалов преподавательский сценарий не работает) и дальше идёт параллельно итерациям; находки — в backlog с пометкой `[dogfood]`, разбор в maintenance-режиме.

## Итерации

### feat-001 (A): Видимость работы агента

**Цель:** комплексная переработка трансляции работы агента в чат — не точечные фиксы, а один системный дизайн-заход: что агент делает сейчас, на какой фазе, что уже сделал — видно, красиво и динамично, уровнем дизайн-системы.

**Статус:** ✅ Done
**Scope:** cross-cutting (Frontend + Backend + Agent)

#### Структура итерации

1. **Аудит → карта событий.** Полная инвентаризация пути LangGraph → SSE → фронт: все события, которые порождает граф (token-стрим, tool-вызовы, guard-фазы, субагентные токены, reasoning, запись в сферу, артефакты, ошибки/блокировки), что из этого доезжает до SSE, что до UI, что теряется. Артефакт — таблица «событие → есть сейчас → целевая визуализация → берём/не берём/потом». **Гейт 1: архитектор проходит по карте, решает состав.**
2. **Design-brief + мокапы** на утверждённый состав. Стартовые референсы — `iterations/post-mvp/feat-011-subagents-v1/mockups/live-feedback-variants.html` (V1 доставлен в feat-011, V2/V3 требуют серверной части). **Гейт 2: вкусовой выбор архитектора.**
3. **Реализация:** бэкенд-контракт (`streaming.md` переписывается) + фронт.

#### Из backlog

- **P1** Live-обратная связь в чате — серверный остаток. Heartbeat-контур закрыт: `stream_started` + heartbeat 5с (`HeartbeatPacer`, `app/agent/heartbeat.py`) и клиентский таймаут «3 пропущенных heartbeat» вместо first-byte — контракт в `streaming.md`. Остаётся: (б) фазовые состояния индикатора (guard → рассуждает → инструмент → review); (г) ранний `tool_start` — эмитить из token-level стрима (`tool_call_chunks` в `stream_mode="messages"`), не дожидаясь завершения узла графа *(cross: Backend, Agent)*
- **P3** Стриминг reasoning-токенов в UI — отдельный SSE event type для рассуждений модели + сворачиваемая секция «агент рассуждает» в чате; закрывает основную долю воспринимаемой тишины на reasoning-моделях *(cross: Backend, Agent)*
- **P3** Системная проработка интерактивности вывода агента (зонт) — трансляция работы агента сделана примитивно: единственная плашка с сырым именем инструмента (`run_subagent`) на время выполнения — не видно, что это инструмент, не видно тип субагента, после завершения не остаётся следа в истории. Сюда: персистентный рендер tool-вызовов в истории сообщений, различимость субагентов (`agent_type` в payload + рендер), человекочитаемые названия инструментов *(Frontend, cross: Backend, Agent, Design-branding)*
- **P2** `security_block` SSE — тройной дрейф контракта (вскрыт усилением S5 feat-009): `streaming.md:30,34` документирует payload `{checkpoint, detection_layer}`; прод (`runner.py` + `block_reason`) эмитит `{reason}`; фронт `useAgentStream` не читает ни одного поля `security_block`. Возможный реальный UX/security-пробел: блокировка не доходит до пользователя. Согласовать контракт (док↔прод↔фронт) и довести событие до UI *(Frontend, Agent, cross: docs)*

#### Документация

- [event-map.md](iterations/dogfooding/feat-001-agent-visibility/event-map.md) — аудит пути LangGraph → SSE → UI, карта событий, решения Гейтов 1–2
- [design-brief.md](iterations/dogfooding/feat-001-agent-visibility/design-brief.md) — контракт SSE v2, typed parts, лента активности, партиция треков T1/T2
- [mockups/live-timeline-v3.html](iterations/dogfooding/feat-001-agent-visibility/mockups/live-timeline-v3.html) — утверждённый визуальный язык (лента · точки · метки); v1/v2 рядом — история вариантов
- [tracks/T1/plan.md](iterations/dogfooding/feat-001-agent-visibility/tracks/T1/plan.md) / [tracks/T2/plan.md](iterations/dogfooding/feat-001-agent-visibility/tracks/T2/plan.md) — implementation plans (backend: контракт SSE v2, typed parts, фикстур имён инструментов; frontend: модель ленты, реестр подписей, live-стрим и история одним компонентом)
- [tracks/T1/summary.md](iterations/dogfooding/feat-001-agent-visibility/tracks/T1/summary.md) — post-implementation summary T1: девять фаз контракта, повызовная проверка и отчёт результата инструмента, компенсирующая телеметрия компакции, слияние feat-002 и триггер auto-title
- [tracks/T2/summary.md](iterations/dogfooding/feat-001-agent-visibility/tracks/T2/summary.md) — post-implementation summary T2: словарь v2 на фронте, чистая модель ленты, вложенная лента субагента, живость и терминальные состояния, девять прод-багов набора и прогонов
- [tracks/T1/test-cases.md](iterations/dogfooding/feat-001-agent-visibility/tracks/T1/test-cases.md) / [tracks/T2/test-cases.md](iterations/dogfooding/feat-001-agent-visibility/tracks/T2/test-cases.md) — тестовые кейсы и результаты прогонов
- [review-a.md](iterations/dogfooding/feat-001-agent-visibility/review-a.md) / [review-b.md](iterations/dogfooding/feat-001-agent-visibility/review-b.md) — code review (независимый + соответствие контракту)
- [harvest-proposals.md](iterations/dogfooding/feat-001-agent-visibility/harvest-proposals.md) — кандидаты в backlog/конвенции, собранные по ходу итерации
- Создан: [ADR-030](../tech/adr/ADR-030-per-call-tool-result-guard.md) — проверка и отчёт результата инструмента повызовно, внутри узла `tools`: размен стоимости классификатора на правдивость ленты
- Обновлены по итогам: [streaming.md](../tech/streaming.md) (контракт SSE v2 целиком, typed parts истории, лимиты, вложенность субагента, security-чекпоинты), [agent-runtime.md](../tech/agent-runtime.md) (узел `tools`, три канала стрима, `get_history`, видимость шагов субагента), [frontend.md](../tech/frontend.md) (лента активности, stream store, дерево модулей, Security UX), [conventions/agent.md](../tech/conventions/agent.md) и [conventions/frontend.md](../tech/conventions/frontend.md) (чек-лист «добавляешь инструмент агенту», раскладка состояния стрима, живость строки), [observability.md](../tech/observability.md) (ручной cost-учёт компакции), [security/architecture.md](../security/architecture.md) (место чекпоинта `tool_result`, наблюдаемость деградации), [design-system.md](../tech/design-system.md) (снятая заглушка записи в Сферу)

#### Сознательно вне scope

- Rich-показ *результатов* инструментов (выборочный рендер результатов tool-вызовов) — отдельный дизайн-вопрос, отложен до потребности из догфудинга. Уточнение Гейта 2: raw-разворот результата с усечением — в scope, «rich» = спец-рендер по типам — вне.
- SSE-дисконнект отменяет LangGraph-ран (потеря ответа) — стрим-ядро, но другая проблема (персистентность, не видимость); остаётся в backlog, кандидат на соло-итерацию в августе — для длинных субагентных ранов при догфудинге станет важной.

---

### chore-001 (B): Prod-closing — kill-switches + деплой в main

**Цель:** сделать merge `develop` → `main` нестрашным и задеплоить накопленное (>300 коммитов с последнего релиза): выключить в проде исследовательские подсистемы, закрыть известные прод-дефекты периметра, вычистить прод-образы.

**Статус:** ✅ Done
**Scope:** cross-cutting (Backend + Agent + Infra)
**Параллельно с:** feat-001 (не пересекаются)

#### Из backlog

- **P2** Kill-switch LLM-защиты — per-env флаг полного отключения inline LLM-defense (SecurityGuard / LLM-классификатор, unicode-детектор, Universal I/O Guard, boundary enforcement). Мотив — LLM-защита артефакт исследования, не продуктовая потребность; в проде стоит лишних LLM-вызовов и latency без ценности. Default off в проде, включается под red-team прогон для статьи. Скоуп строго: только inline LLM-defense — НЕ трогает SIEM-пайплайн, auth, rate limiting, RBAC (обычная app-security остаётся 100%). Env-гигиена: `Settings` + `.env.example` + `.env.local.example` + `docker-compose.yml` *(Agent, Backend)*
- **P2** SIEM kill-switch — развилка «kill-switch ИЛИ допил до продакшна» решена архитектором в пользу **варианта A (kill-switch)**: SIEM реализован под учебную цель (дисциплина по ИБ, фундамент диплома) и её закрывает; для продакшна не годится (невалидируемый `config` правил, RBAC-guard пропускает не-админов), допиливать сейчас не будем. Per-env kill-switch по образцу kill-switch LLM-защиты; вариант B (допил: валидация правил, рабочий RBAC, активное реагирование) — вернётся при реальной потребности в живом SIEM (диплом / прод-нагрузка, см. backlog «SIEM → SOC evolution»). Следствие: post-mvp feat-007 (SIEM Extensions) — ⏸️ Paused *(Backend, SIEM, Security)*
- **P2** `X-Forwarded-For` доверяется безусловно — спуфинг IP: `backend/app/main.py` (request_id middleware) и `backend/app/api/routes/auth.py` (`_get_client_ip`) берут первый IP из XFF без проверки доверенного прокси. Следствия: обход per-IP rate-лимитов (подтверждено прогонами feat-002/feat-004), подмена IP в логах и SIEM-событиях. Решение — по факту топологии прода (читается из deploy-конфигов в рамках итерации): trusted-hops (N-й IP справа), `uvicorn --proxy-headers --forwarded-allow-ips`, конфиг-флаг `TRUST_PROXY_HEADERS` *(Backend, Auth, Security, Infra)*
- **P3** Прод-образы тащат dev-зависимости — `uv sync --all-packages` в `backend/Dockerfile` и `services/siem-service/Dockerfile` ставит dev-группу, включая test-harness (`learnflow-testing` → `testcontainers`, `pytest`, `factory-boy`). Почистить через `--no-dev`, проверив что entrypoint (alembic + uvicorn) не нуждается в dev-deps *(Infra)*

#### Документация

- [design-brief.md](iterations/dogfooding/chore-001-prod-closing/design-brief.md) — контекст решений, партиция треков
- Ревью: [review-a.md](iterations/dogfooding/chore-001-prod-closing/review-a.md), [review-b.md](iterations/dogfooding/chore-001-prod-closing/review-b.md)
- **T1 клиентский IP:** [plan](iterations/dogfooding/chore-001-prod-closing/tracks/T1/plan.md), [summary](iterations/dogfooding/chore-001-prod-closing/tracks/T1/summary.md), [test-cases](iterations/dogfooding/chore-001-prod-closing/tracks/T1/test-cases.md)
- **T2 прод-образы:** [plan](iterations/dogfooding/chore-001-prod-closing/tracks/T2/plan.md), [summary](iterations/dogfooding/chore-001-prod-closing/tracks/T2/summary.md), [test-cases](iterations/dogfooding/chore-001-prod-closing/tracks/T2/test-cases.md)
- **T3 kill-switch LLM-защиты:** [plan](iterations/dogfooding/chore-001-prod-closing/tracks/T3/plan.md), [summary](iterations/dogfooding/chore-001-prod-closing/tracks/T3/summary.md), [test-cases](iterations/dogfooding/chore-001-prod-closing/tracks/T3/test-cases.md)
- **T4 SIEM kill-switch:** [plan](iterations/dogfooding/chore-001-prod-closing/tracks/T4/plan.md), [summary](iterations/dogfooding/chore-001-prod-closing/tracks/T4/summary.md), [test-cases](iterations/dogfooding/chore-001-prod-closing/tracks/T4/test-cases.md)
- Новый: [tech/setup/production.md](../tech/setup/production.md) — nginx-периметр, runbook; [tech/adr/ADR-029](../tech/adr/ADR-029-operational-kill-switches.md) — принцип операционных kill-switch'ей
- Актуализированы: [security/architecture.md](../security/architecture.md), [tech/siem-service.md](../tech/siem-service.md), [tech/agent-runtime.md](../tech/agent-runtime.md), [tech/streaming.md](../tech/streaming.md), [tech/observability.md](../tech/observability.md), [tech/backend.md](../tech/backend.md), [tech/auth.md](../tech/auth.md), [tech/conventions.md](../tech/conventions.md), [tech/conventions/agent.md](../tech/conventions/agent.md), [tech/adr/ADR-017](../tech/adr/ADR-017-prompt-injection-defense.md)

#### Завершение итерации

Смоук полного стека с выключенными тумблерами → merge `develop` → `main` (PR) → автодеплой → проверка на проде.

---

### feat-002 (C): Chat UX

**Цель:** переработка входа в чат: поле ввода — для первого сообщения, а не title; title генерирует модель; чаты можно удалять и переименовывать.

**Статус:** ✅ Done
**Scope:** cross-cutting (Frontend + Backend)
**After:** feat-001 (наследует переработанный стрим-контракт)

#### Из backlog (через post-mvp feat-001, перенесена сюда с расширением)

- **P1** Chat input: поле ввода для первого сообщения, не для title; title auto-generated моделью *(cross: Backend)*
- **P2** Удаление чатов — в API чатов только create/list/get; удалять можно только проекты *(cross: Frontend, Backend)*
- Переименование чатов — отсутствует по той же причине (нет PATCH); добавлено архитектором при переносе
- ~~Индикатор «модель рассуждает»~~ — перерабатывается в feat-001 (A), из этой итерации исключён

#### Открытые вопросы (решаются в design-brief, решения пока не приняты)

- **Title-модуль:** генерация title — не основной агент, а отдельный лёгкий модуль в сервисном слое (fire-and-forget после первого сообщения, дешёвая модель); кандидат на конфиг — секция в `agent.yaml` по образцу секции `image` (feat-010 post-mvp). Точная архитектура — на design-brief.
- **Доставка title на фронт:** рефетч списка чатов после `done` vs отдельное SSE-событие `title_updated` (второе — аргумент делать итерацию после feat-001, контракт уже будет переработан).

#### Документация

- [design-brief.md](iterations/dogfooding/feat-002-chat-ux/design-brief.md) — целевой UX (два пути входа), архитектура auto-title модуля, доставка `title_updated` (+ отвергнутые альтернативы), каскад удаления чата, партиция треков T1/T2
- [mockups/chat-ux.html](iterations/dogfooding/feat-002-chat-ux/mockups/chat-ux.html) — интерактивный мокап, утверждён архитектором как референс реализации фронта
- [tracks/T1/plan.md](iterations/dogfooding/feat-002-chat-ux/tracks/T1/plan.md) / [tracks/T2/plan.md](iterations/dogfooding/feat-002-chat-ux/tracks/T2/plan.md) — implementation plans (backend: контракты чатов + auto-title; frontend: вход через первое сообщение + `title_updated` + ChatActions)
- [tracks/T1/summary.md](iterations/dogfooding/feat-002-chat-ux/tracks/T1/summary.md) — post-implementation summary T1: bodyless `POST /chats`, rename/delete с каскадом, `ChatTitleGenerator`, фиксы находок F1 (row-lock) и CODE_REVIEW (teardown, atomic-write guard и др.)
- [tracks/T2/summary.md](iterations/dogfooding/feat-002-chat-ux/tracks/T2/summary.md) — post-implementation summary T2: оба пути входа, `title_updated` → `setQueryData`-патч, `TypedTitle`, `features/chat-actions`, фиксы прод-багов ручного прогона (F2, F3)
- [tracks/T1/test-cases.md](iterations/dogfooding/feat-002-chat-ux/tracks/T1/test-cases.md) / [tracks/T2/test-cases.md](iterations/dogfooding/feat-002-chat-ux/tracks/T2/test-cases.md) — тестовые кейсы
- [review-a.md](iterations/dogfooding/feat-002-chat-ux/review-a.md) / [review-b.md](iterations/dogfooding/feat-002-chat-ux/review-b.md) — code review (независимый + соответствие контракту)
- [harvest-proposals.md](iterations/dogfooding/feat-002-chat-ux/harvest-proposals.md) — кандидаты в backlog/конвенции, собранные по ходу итерации
- [sofa-proposals.md](iterations/dogfooding/feat-002-chat-ux/sofa-proposals.md) — SOFA-кандидаты (3 TIL + 1 Blueprint, доведены до финала, не опубликованы)
- Обновлены по итогам: [streaming.md](../tech/streaming.md) (`title_updated`), [backend.md](../tech/backend.md) (эндпоинты чатов, `ChatService`, `ChatTitleGenerator`), [frontend.md](../tech/frontend.md) (экраны, mutations-таблица, дерево модулей), [agent-runtime.md](../tech/agent-runtime.md) (секция `title` в `agent.yaml`), [prompt-management.md](../tech/prompt-management.md) (реестр промптов)

---

### feat-003 (D): Модели — cost-optimal + whitelist expansion

**Цель:** подобрать cost-efficient модели по внешним бенчмаркам (собственного eval-контура нет и до конца 5b не будет — сознательно), расширить whitelist, завести pricing в Langfuse. Валидация — сам догфудинг: реальный материал + runtime model switching (post-mvp feat-003).

**Статус:** ✅ Done
**Scope:** agent

#### Из backlog

- **P1** Cost-optimal модель для массового использования — текущий прод гоняет на фронтир-моделях: отличное качество, но дорого по токенам и не масштабируется. Нужен оптимум качество/стоимость (~70% фронтир-качества при ~10× дешевле). Кандидаты: китайские opensource-модели, usage-based планы. Fireworks Firepass проверен — single-user, не подходит. Перспективно на будущее — бартер доступа с хостерами железа за пиар. Предусловие Фазы 6 *(Agent, cross: Infra)*
- **P2** Model whitelist expansion — расширить whitelist в `agent.yaml` минимум до 5 основных моделей. Pricing initialization в Langfuse через lifespan для всех новых моделей, включая текущую guard model (её стоимость сейчас не видна в Langfuse) *(Agent)*

#### Процесс

Ресёрч-часть делает агент: срез по внешним источникам (LMArena text/creative writing, Artificial Analysis intelligence-vs-price, OpenRouter rankings по реальному usage) → таблица кандидатов с ценами и оценками → отбор архитектором → whitelist + pricing seed.

#### Документация

- [design-brief.md](iterations/dogfooding/feat-003-model-selection/design-brief.md) — утверждённый состав моделей, единая reasoning-форма, наследование `extra_body` в резолвере, коллизии pricing-паттернов, состав тестов
- [research-candidates.md](iterations/dogfooding/feat-003-model-selection/research-candidates.md) — срез кандидатов по методике `model-selection.md`, обоснование отбора по классам
- [tracks/T1/plan.md](iterations/dogfooding/feat-003-model-selection/tracks/T1/plan.md) — implementation plan
- [tracks/T1/summary.md](iterations/dogfooding/feat-003-model-selection/tracks/T1/summary.md) — post-implementation summary: фазы, фикс-циклы (гео-блок Muse Spark → Grok 4.5, code review)
- [tracks/T1/test-cases.md](iterations/dogfooding/feat-003-model-selection/tracks/T1/test-cases.md) — тестовые кейсы
- [smoke-run-results.md](iterations/dogfooding/feat-003-model-selection/smoke-run-results.md) — результаты боевых прогонов смоук-скрипта по финальному составу
- [review-a.md](iterations/dogfooding/feat-003-model-selection/review-a.md) — code review трека T1
- [reference/model-selection.md](../reference/model-selection.md) — методика выбора моделей и карта ролей/альтернатив, обновлена по итогам итерации

---

### feat-004 (E): File attachments — 🔀 Merged → feat-011

**Поглощена feat-011 (execution runtime).** Файловый workspace снял вопрос хранения (вложение = файл в `uploads/` проекта), runtime снял вопрос ingestion (извлечение текста из PDF/DOCX агент делает сам через executor — конвертации при загрузке нет). Оставшийся тонкий контракт (двухфазная загрузка «чип клиентский → upload при отправке», пометка в user-сообщении + metadata для UI-чипа, мокап) зафиксирован в design-brief feat-011 § Вложения пользователя. Отдельная итерация не проводится.

---

### feat-005 (F): PDF-экспорт

**Цель:** рабочий PDF-экспорт артефактов с рендером формул и фирменным стилем — преподавательский материал должен выходить файлом.

**Статус:** 📋 Planned
**Scope:** backend (cross: Design-branding)

#### Из backlog

- **P2** PDF-экспорт артефактов неработоспособен — `backend/app/api/export.py` использует pdfkit/wkhtmltopdf; wkhtmltopdf archived/deprecated и сегфолтится на MathJax-скрипте (воспроизведено на Fedora 43, wkhtmltopdf 0.12.6: `GET .../artifacts/{id}/download?format=pdf` → 500). Для образовательной платформы рендер формул критичен → замена с поддержкой математики: headless-Chromium/Playwright (исполняет MathJax, тяжёлый), KaTeX server-side pre-render → HTML → weasyprint, или pandoc+LaTeX (лучшее качество, тяжёлый tex-стек). Заодно — один добротный фирменный стиль PDF: шрифт и оформление консистентны с дизайн-системой LearnFlow AI. Управляемую агентом вариативность стилей не вводим, пока не вылезет из dogfooding *(Backend, cross: Design-branding)*

---

### feat-006 (G): Генерация слайдов

**Цель:** превращение подготовленного материала в слайды/презентацию — ключевой выходной формат преподавательского контента.

**Статус:** 📋 Planned
**Scope:** agent (cross: Backend)

#### Из backlog

- **P3** Генерация слайдов — скилл или MCP, превращающий материал в слайды. Кандидат в обязательный bundle скиллов. Подход — markdown-first (Slidev / Marp / reveal-класс, не сырой PowerPoint); конкретный инструмент выбирается во время spike по качеству/удобству работы с агентом ([ADR-026](../tech/adr/ADR-026-tool-introduction-pattern.md): spike → validate → integrate), там же проектируется интеграция с продуктовым агентом *(Agent)*

Приоритет поднят с P3 архитектором: плановая итерация уровня file attachments, а не «по сигналу».

---

### feat-007 (H): Кастомные скиллы пользователя

**Цель:** пользователь может подключать собственные скиллы — любые, не только из бандла проекта. Включает страницу библиотеки скиллов.

**Статус:** 📋 Planned
**Scope:** cross-cutting (Agent + Backend + Frontend + Security)

#### Из backlog

- **P3** Страница библиотеки скиллов — просмотр списка и содержимого скиллов в UI (сейчас скиллы видны только агенту); per-user включение/отключение скиллов; просмотр содержимого скилла из секции «Контекст скиллов» (вынесено из post-mvp feat-012) *(Frontend, cross: Backend)*

#### Новые элементы (вне existing backlog)

- Механизм подключения пользовательских скиллов (модель хранения per-user — по образцу user MCP-серверов, post-mvp feat-003 Track C).
- **Security:** пользовательский скилл ломает текущую границу доверия — сейчас контент `skills/` репозиторный и доверенный, checkpoint'ы Sec 2.0 его не покрывают. Пользовательский скилл — чужой текст, инжектируемый в контекст агента (indirect-injection вектор) → add-time checkpoint на загрузку (по образцу `skill_context_write`, post-mvp feat-012) + ADR.

#### Открытые вопросы (на design-brief)

- Формат подключения: upload файлов / git-ссылка / редактор в UI.
- Многофайловость: механика feat-009 (post-mvp) готова, но path-traversal-поверхность на пользовательском контенте перепроверить.

---

### feat-008 (I): OAuth + auth-экраны

**Цель:** авторизация через внешних провайдеров — вход без заведения отдельного пароля — + функциональный каркас страницы `/login`. Состав провайдеров пересмотрен архитектором при взятии в работу: Яндекс ID для пользователей из РФ, все активные провайдеры (+ Google, GitHub) для остальных — гео-разделение по ч. 10 ст. 8 149-ФЗ (запрет иностранной авторизации для РФ-пользователей; штрафы по ст. 13.55 КоАП действуют с 07.07.2026). VK ID исключён на этапе design-brief: регистрация приложения физлицу без бизнес-верификации недоступна, dev-флоу требовал бы отдельной https-топологии; кандидат на возврат при появлении верифицированного профиля. 404-экран и брендовый дизайн auth-экранов перенесены в feat-013 (решение архитектора: весь UI-дизайн консолидируется в полировочном пакете, включая мокапы).

**Статус:** ✅ Done
**Ветка:** `dogf/feat-008-oauth-auth-screens`
**Scope:** cross-cutting (Frontend + Backend + Design-branding)

#### Из backlog

- **P1** OAuth authentication (Google, GitHub — состав провайдеров пересмотрен, см. Цель) — сейчас только логин/пароль; требование хранить отдельный пароль сильно снижает конверсию. Именно OAuth, не email confirmation code. Затрагивает backend (провайдерская интеграция, token exchange, user linking), frontend (социальные кнопки, OAuth callback flow), `tech/auth.md`. Может потребовать ADR по user identity model при нескольких провайдерах на одного пользователя *(Frontend + Backend)*

#### Решения архитектора (взятие в работу; детализация и контракты — design-brief)

- **Провайдеры и порядок:** вертикаль целиком на Яндекс ID первым (самый простой для dev: обычный code flow, localhost без модерации) → затем конвейером Google → GitHub на готовой абстракции. VK ID исключён (см. Цель); его нестандартности задокументированы в research-provider-libs на случай возврата.
- **Гео-enforcement серверный:** страна по IP оффлайн-базой (IPinfo Lite MMDB + `geoip2`-reader, регулярное обновление, атрибуция CC BY-SA); для РФ-IP отклоняются и инициация, и callback Google/GitHub — скрытие кнопок только в UI юридически недостаточно. Парольный вход остаётся для всех (иностранный email как логин не запрещён — осознанное допущение, зафиксировано в ресёрче). Пользователь за VPN выглядит как не-РФ — добросовестная best-effort позиция, методики регулятора не существует.
- **Модель данных:** отдельная таблица `oauth_accounts` (`unique(provider, provider_account_id)`, `email` nullable — GitHub может скрывать, timestamps, CHECK по списку провайдеров), `users.password_hash` → nullable; `users.email` в v1 не вводится; токены провайдера не хранятся (используются одноразово на входе). `refresh_tokens` и сессионная механика не меняются — OAuth заканчивается на выдаче обычной пары access/refresh.
- **Идентичность и линковка:** пользователь = `(provider, provider_account_id)`; авто-линковка по email запрещена (pre-account-takeover при неверифицированном email); ручная линковка нескольких провайдеров — вне scope v1, схема таблицы ей не мешает.
- **Провайдер-слой:** собственная тонкая абстракция на httpx, без authlib — Яндекс не OIDC (главная ценность authlib — discovery/JWKS — сыграла бы для одного Google), SessionMiddleware authlib чужд JWT-бэкенду. State + PKCE S256 во всех флоу.
- **Вход страницей:** блокирующая модалка `AuthGate` над роутером перестраивается на страницу `/login` под роутером (OAuth-флоу требует маршрутов; заодно auth-экран становится обычной страницей).
- **Dev-окружение:** отдельные dev-приложения у провайдеров (пары client_id/secret dev/prod — ручные шаги архитектора по инструкции из брифа); dev-флоу целиком через Vite-proxy на одном host `localhost:5173`. Dev-регистрации всех трёх провайдеров выполнены, гео-база скачана (статус — в брифе).
- **Граница с feat-013 («каркас здесь, краска там»):** feat-008 строит функциональную страницу `/login` на существующих shadcn-примитивах — сразу с русским копирайтом и целевой FSD-структурой (`pages/login`, при росте — `features/auth`), без визуальной полировки. Брендовый дизайн auth-экранов — в feat-013 (мокап в её общем пакете, стилизация после merge feat-008). Контракт стыка — два общих файла: `router.tsx` (feat-008 владеет структурной перестройкой входа — AuthGate → `/login` под роутером; feat-013 добавляет только catch-all `path="*"`; конфликт merge тривиален, разруливает мержащийся вторым) и `shared/api/client.ts` (feat-013 меняет правило исключений интерцептора на семантическое «анонимные эндпоинты — вне refresh-retry»; feat-008 файл не правит, но классифицирует свои эндпоинты по этому правилу — детали в брифах обеих итераций). Структурный референс каркаса `/login` — утверждённый мокап feat-013; файловую структуру каркаса feat-013 не переносит.

#### Артефакты

- [design-brief.md](iterations/dogfooding/feat-008-oauth-auth-screens/design-brief.md) — финализирован: флоу, state-cookie, провайдер-слой, гео-gate, реестры ошибок и SIEM-событий, контракты, рамка порядка реализации (партиция треков — за фазой PARTITION оркестратора); открытые вопросы взятия в работу (state-хранение, shape callback-пути, контракт providers) закрыты в нём; ревью свежими агентами пройдено двумя прогонами (15 + 12 находок, включая кросс-сверку с брифом feat-013; вправлены)
- Ресёрч-выжимки взятия в работу: [research-legal-geo.md](iterations/dogfooding/feat-008-oauth-auth-screens/research-legal-geo.md) (149-ФЗ, ст. 13.55 КоАП, геодетекция), [research-data-model.md](iterations/dogfooding/feat-008-oauth-auth-screens/research-data-model.md) (эталонные схемы, DDL-эскиз, postgresql-ревью), [research-provider-libs.md](iterations/dogfooding/feat-008-oauth-auth-screens/research-provider-libs.md) (authlib vs httpx, политики провайдеров, dev/prod-окружения)

#### Документация

- [design-brief.md](iterations/dogfooding/feat-008-oauth-auth-screens/design-brief.md) — OAuth-флоу (Яндекс ID/Google/GitHub), гео-разделение по 149-ФЗ, cookie `oauth_flow`, модель данных, каркас `/login` по мокапу feat-013, партиция треков T1/T2
- [research-legal-geo.md](iterations/dogfooding/feat-008-oauth-auth-screens/research-legal-geo.md) / [research-data-model.md](iterations/dogfooding/feat-008-oauth-auth-screens/research-data-model.md) / [research-provider-libs.md](iterations/dogfooding/feat-008-oauth-auth-screens/research-provider-libs.md) — юридическая рамка гео-ограничения, ресёрч модели данных (эталоны Auth.js/allauth/better-auth/omniauth, база ADR-031), сравнение провайдерских библиотек
- [tracks/T1/plan.md](iterations/dogfooding/feat-008-oauth-auth-screens/tracks/T1/plan.md) / [tracks/T2/plan.md](iterations/dogfooding/feat-008-oauth-auth-screens/tracks/T2/plan.md) — implementation plans (backend: модель + миграция, провайдер-абстракция, гео-gate, эндпоинты, SIEM-словарь; frontend: каркас `/login`, guard, бутстрап)
- [tracks/T1/summary.md](iterations/dogfooding/feat-008-oauth-auth-screens/tracks/T1/summary.md) / [tracks/T2/summary.md](iterations/dogfooding/feat-008-oauth-auth-screens/tracks/T2/summary.md) — post-implementation summary: девять фаз бэкенд-вертикали (T1), каркас входа + фиксы доступности (T2)
- [tracks/T1/test-cases.md](iterations/dogfooding/feat-008-oauth-auth-screens/tracks/T1/test-cases.md) / [tracks/T2/test-cases.md](iterations/dogfooding/feat-008-oauth-auth-screens/tracks/T2/test-cases.md) — тестовые кейсы и результаты прогонов
- [review-a.md](iterations/dogfooding/feat-008-oauth-auth-screens/review-a.md) / [review-b.md](iterations/dogfooding/feat-008-oauth-auth-screens/review-b.md) — code review (независимый + соответствие контракту)
- [harvest-proposals.md](iterations/dogfooding/feat-008-oauth-auth-screens/harvest-proposals.md) — кандидаты в backlog/конвенции, собранные по ходу итерации
- Создан: [ADR-033](../tech/adr/ADR-033-oauth-identity-model.md) — отдельная таблица `oauth_accounts`, запрет авто-линковки по email, nullable `password_hash`
- Обновлены по итогам: [auth.md](../tech/auth.md) (OAuth-вход целиком: флоу, cookie `oauth_flow`, гео-gate, реестр кодов ошибок, поверхность атаки, вход страницей `/login`), [backend.md](../tech/backend.md) (`infra/oauth`, `infra/geoip.py`, `AuthService`/`OAuthService`, `api/cookies.py`, таблица `OAuthAccount`, `show_locals=False`), [frontend.md](../tech/frontend.md) (маршрут `/login`, guard `RequireAuth`, `useAuthBootstrap`, дерево модулей), [security-events.md](../tech/security-events.md) (`auth.oauth.success`/`failed`, `rate_limit.oauth.exceeded`), [conventions/api.md](../tech/conventions/api.md) (исключение `/auth/providers` из list-envelope)

---

### feat-009 (J): Web search MCP — замена Firecrawl на Jina AI

**Цель:** рабочий веб-поиск и чтение URL для агента вместо исчерпанного Firecrawl free tier. Решение архитектора по итогам ресёрча: hosted Jina AI MCP (`search_web` + `read_url`) — минимальная цена при достаточном качестве; self-hosted стек (SearXNG + Crawl4AI) отложен до масштаба реального продакшна. Ресёрч и trade-offs зафиксированы в design-brief итерации.

**Статус:** ✅ Done
**Scope:** infra (cross: Agent, Backend)

**Ветка:** `dogf/feat-009-web-search-mcp`

#### Из backlog

- **P2** Self-hosted web search MCP — найти self-hosted аналог Tavily/Firecrawl для веб-поиска агентом. Кандидаты: SearxNG + MCP-адаптер, open-webSearch. Текущий Firecrawl free tier ограничен по кредитам *(cross: Agent, Backend)*

Триггер «активный догфудинг выест кредиты Firecrawl» сработал — итерация сдвинута вперёд относительно плана.

#### Артефакты

- [design-brief.md](iterations/dogfooding/feat-009-web-search-mcp/design-brief.md)
- [summary.md](iterations/dogfooding/feat-009-web-search-mcp/summary.md)

---

### feat-010 (K): Voice input

**Цель:** голосовой ввод сообщений агенту (STT). Stretch к показу — делается в последнюю очередь, после OAuth и web search.

**Статус:** 📋 Planned
**Scope:** cross-cutting (Frontend + Backend)

#### Из backlog

- **P1** Voice input — голосовой ввод (STT). Фича тривиальна; нетривиальное — UX: склоняемся к «транскрипт → редактируемое поле чата» (пользователь правит ошибки STT по терминам/именам), а не «сразу агенту»; финальный UX — на этапе реализации *(cross: Backend)*

---

### feat-011 (L): Execution runtime — изолированное выполнение кода и рендер-пайплайнов

**Цель:** выполнение кода/CLI из графа агента в изолированном окружении — общий фундамент выходных форматов: PDF-экспорт (F), слайды (G), ГОСТ-скилл (M) и будущие скиллы, которым нужен shell. Проектируется один раз как переиспользуемый контракт, не точечное решение под фичу.

**Статус:** ✅ Done
**Ветка:** `dogf/feat-011-execution-runtime`
**Scope:** cross-cutting (Agent + Backend + Infra + Security)
**Before:** feat-005 (F), feat-006 (G), feat-012 (M) — строятся на контракте runtime

#### Новые элементы (вне existing backlog, добавлено архитектором)

- Контракт верхнеуровнево: агент кладёт входные файлы (markdown + ассеты) → runtime выполняет фиксированный тулчейн в изолированном окружении → файлы-артефакты возвращаются в blob-хранилище (`artifact_blobs` / `BlobStorage`, post-mvp feat-010).
- В LangGraph готового ShellTool-middleware нет (в отличие от LangChain) — реализация: tool-обёртка над контейнерным исполнением. Ввод по [ADR-026](../tech/adr/ADR-026-tool-introduction-pattern.md): spike → validate → integrate.
- **Security:** исполнение кода — новая поверхность атаки. Границы v1: фиксированный образ тулчейна (pandoc, marp/slidev-класс, python-docx, шрифты), без сети, лимиты CPU/RAM/время, изоляция от основного стека. ADR обязателен.

#### Открытые вопросы (на design-brief)

- Механика изоляции: контейнер per-request vs warm pool; docker-in-docker vs соседний сервис-executor.
- Состав образа v1 — минимум под F/G/M, расширение по потребности.
- Граница API: только «файлы → тулчейн-рецепт → файлы» или произвольный shell для агента (склоняемся к рецептам — уже поверхность, проще ревьюить).

#### Документация (дизайн финализирован 2026-08-11)

- [design-brief.md](iterations/dogfooding/feat-011-execution-runtime/design-brief.md) — полная картина: executor-сервис под gVisor + bwrap per job, файловый workspace и переезд артефактов, вложения (поглощённая E), контракты инструментов, безопасность; два прогона независимого ревью решены и вписаны
- [acceptance.md](iterations/dogfooding/feat-011-execution-runtime/acceptance.md) — сквозные сценарии приёмки архитектора (способности, границы изоляции, регрессии)
- [mockups/attachments-artifacts.html](iterations/dogfooding/feat-011-execution-runtime/mockups/attachments-artifacts.html) — интерактивный мокап (вложения, «артефакт обновлён», дерево артефактов), утверждён архитектором
- [spikes/spike-bwrap-gvisor.md](iterations/dogfooding/feat-011-execution-runtime/spikes/spike-bwrap-gvisor.md) — спайк bwrap под gVisor (зелёный): рабочий префикс, два следствия в контракт реализации
- ADR: [ADR-031](../tech/adr/ADR-031-execution-runtime-isolation.md) — изоляция execution runtime (дополнен принятыми в реализации решениями: `security_opt`, `tini`, `EXECUTOR_RUNTIME`-override, единый uid + запечённый `chown` volume); [ADR-032](../tech/adr/ADR-032-project-workspace-file-model.md) — workspace и файловая модель артефактов

Предпроектные открытые вопросы решены брифом: изоляция — соседний сервис-executor (не DinD, не per-request контейнеры) + bwrap per job; образ — толстый, состав финализируют спайки feat-005/006, смоук-набор — ворота релиза; граница API — общие инструменты (`execute_code`/`run_command`), не рецепты (рамка «одна способность, не три режима»); артефакты — файлы workspace, не blob-хранилище (пересмотр раннего наброска, ADR-032).

#### Реализация

- Ревью: [review-a.md](iterations/dogfooding/feat-011-execution-runtime/review-a.md), [review-b.md](iterations/dogfooding/feat-011-execution-runtime/review-b.md)
- **T1 backend (workspace, инструменты, вложения):** [plan](iterations/dogfooding/feat-011-execution-runtime/tracks/T1/plan.md), [summary](iterations/dogfooding/feat-011-execution-runtime/tracks/T1/summary.md), [test-cases](iterations/dogfooding/feat-011-execution-runtime/tracks/T1/test-cases.md)
- **T2 frontend (артефакты по путям, композер вложений):** [plan](iterations/dogfooding/feat-011-execution-runtime/tracks/T2/plan.md), [summary](iterations/dogfooding/feat-011-execution-runtime/tracks/T2/summary.md), [test-cases](iterations/dogfooding/feat-011-execution-runtime/tracks/T2/test-cases.md)
- **T3 executor (сервис, gVisor + bwrap, kill-контракт):** [plan](iterations/dogfooding/feat-011-execution-runtime/tracks/T3/plan.md), [summary](iterations/dogfooding/feat-011-execution-runtime/tracks/T3/summary.md), [test-cases](iterations/dogfooding/feat-011-execution-runtime/tracks/T3/test-cases.md)
- Приёмка [acceptance.md](iterations/dogfooding/feat-011-execution-runtime/acceptance.md) закрыта целиком: 14 сценариев способностей агента, 9 проверок изоляции, 3 регрессионных. Блок изоляции прогнан на топологии с настоящим gVisor (ядро джобы `4.19.0-gvisor`): чужой workspace в mount-ns джобы не существует, сеть недостижима на уровне netns, дедлайн не оставляет ни потомков, ни зомби, секретов приложения в env executor'а нет.
- Ручной E2E-прогон архитектора дал два дефекта фронта, закрытых в этой же ветке: лишний скролл страницы поверх скролла ленты (скрытый MathML-дубликат KaTeX без позиционированного предка + `scrollIntoView` без `block: "nearest"`) и позиция карточки артефакта в ходе (артефакты собираются в конец `parts`, по одной карточке на путь). Наблюдения без контракта — в [backlog](../backlog.md).
- Прод-развёртывание описано в [tech/setup/production.md](../tech/setup/production.md): установка `runsc`, отдельная точка монтирования для тома workspace, проверка bwrap первым шагом деплоя, бэкапы.

**Актуализация документации после реализации (DOC_UPDATE):** новый [tech/executor.md](../tech/executor.md) — контракт `POST /jobs`, слои изоляции, sandbox, конфигурация; правлены [backend.md](../tech/backend.md) (файловый слой, снос PG-цепочки артефактов, ER-диаграмма, `executor`-инфра, конфигурация), [streaming.md](../tech/streaming.md) (`artifact_updated`, `ArtifactPart`, invalidation, вложения), [agent-runtime.md](../tech/agent-runtime.md) (пять новых инструментов, снос `create_artifact`, `input_artifact_paths`, деградация execution runtime), [frontend.md](../tech/frontend.md) (рендер `ArtifactPart`, дерево артефактов, композер вложений), [conventions.md](../tech/conventions.md) + `conventions/api.md`/`agent.md`/`frontend.md` (живые примеры вместо снесённого кода), [security-events.md](../tech/security-events.md) (каталог пополнен `agent.runtime.path_denied`), [security/architecture.md](../security/architecture.md) (новые границы доверия executor/workspace), [design-system.md](../tech/design-system.md), [arch-checker.md](../tech/arch-checker.md), [vision.md](../vision.md) и [index.md](../index.md) (executor как четвёртый standalone-сервис), [product/roadmap.md](../product/roadmap.md). ADR-027 помечен Superseded by ADR-032; ADR-007/ADR-028 актуализированы под `write_file`/`input_artifact_paths`.

---

### feat-012 (M): ГОСТ-скилл — оформление студенческих работ

**Цель:** bundle-скилл оформления студенческих работ по ГОСТ 7.32 (лабораторные, курсовые, отчёты по практике): LLM генерирует Markdown → runtime собирает .docx (pandoc + python-docx + docxcompose, подключаемые титульники «вуз × тип работы»). Первый готовый оффер для студенческой аудитории и дистрибуционный крючок.

**Статус:** 📋 Planned
**Scope:** agent (cross: Backend, Product)
**After:** feat-011 (runtime — сборка .docx), feat-004 (вход файлов: методичка, скриншоты, вариант задания)

#### Новые элементы (вне existing backlog, добавлено архитектором)

- Скилл существует и обкатан вне продукта (личный скилл владельца: профили типов работ, wizard титульников, review-чеклист) — задача переноса и адаптации под bundle-механику, не разработка с нуля.
- Репозиторный (доверенный) скилл — НЕ требует feat-007 (кастомные скиллы пользователей) и её security-границы.
- Опциональный слой авто-СОДЕРЖАНИЯ (LibreOffice + python-uno) — решить при переносе: включать в образ runtime или отрезать в v1 (обновление поля в Word руками — приемлемый fallback).
- Дистрибуция: оффер «отчёт по ГОСТу» для студенческой волны (одногруппники, ~30 чел) после показа преподавателям; C1-статья про ГОСТ-скилл ([roadmap](../product/roadmap.md) § Доклады, talks.md) усиливается CTA «попробовать в продукте». Волновая модель и гейт затрат — backlog § Product / Distribution.

---

### feat-013 (N): UI/UX polish — пакет мелких правок

**Цель:** закрыть одним заходом накопленные мелкие UI/UX-правки из backlog § Frontend / UX — предпоказная полировка продукта. Процесс: design-brief + полный интерактивный HTML-мокап всех затрагиваемых экранов (ревью архитектора до реализации, конвенция § UI-мокапы); воспроизведение плавающего бага сайдбара — субагентами на развёрнутом стеке до/во время брифа.

**Статус:** ✅ Done
**Ветка:** `dogf/feat-013-ui-polish`
**Scope:** frontend (cross: Design-branding)
**Параллельно с:** feat-008 (граница согласована архитектором: 404-экран и брендовый дизайн auth-экранов целиком здесь; feat-008 строит функциональный каркас `/login` по утверждённому здесь мокапу. Контракт стыка — два общих файла: `router.tsx` (feat-008 владеет структурной перестройкой входа, здесь добавляется только catch-all `path="*"`) и `shared/api/client.ts` (здесь — семантическое правило исключений интерцептора, feat-008 классифицирует свои эндпоинты по нему, файл не правя); стилизация auth-экранов — после merge feat-008, мокап — раньше, в общем пакете мокапов), feat-011 (не пересекаются)

#### Из backlog

- **P2** Сайдбар не отображается при первом открытии — при заходе на прод после долгого перерыва (первое открытие / холодная сессия) левый сайдбар с ником пользователя, переключателем темы и настройками не рендерится; после обновления страницы появляется. Плавающий баг — воспроизвести (кандидаты: гонка auth-гидрации / initial state ui-store), замечено на проде при догфудинге *(Frontend)*
- **P3** Кастомизация скроллбаров под дизайн-систему — во всех overflow-контейнерах (Markdown-превью «Контекста скиллов», чат, сайдбар, таблицы) рендерится стандартный системный скроллбар, выбивающийся из проработанного визуала. Единый стиль на уровне дизайн-системы (`::-webkit-scrollbar` + `scrollbar-width`/`scrollbar-color`, токены обеих тем), тонкий и ненавязчивый *(Frontend, cross: Design-branding)*
- **P3** Loading + per-query error-состояния (остаток error-UI) — (1) единый брендовый паттерн загрузки (скелетоны/спиннер вместо плоского «Загрузка…» в `router.tsx`/`SecurityRouteGuard`/`ChatList`/`ArtifactList`/`SecurityEvents`); (2) дизайн per-query/list error-состояний (сейчас сырые инлайн-строки `text-destructive` в `ProjectList`/`ChatView`/`ChatList`/`ArtifactList`). Тост-канал и глобальный `ErrorBoundary` уже доставлены в design-branding feat-004 *(Frontend)*
- **P3** ModelSelector: сырое «inherit» в свёрнутом состоянии — свёрнутый селект показывает англоязычное «inherit», при раскрытии список локализован; локализовать отображение выбранного значения *(Frontend)*
- **P3** ModelSelector (project scope) не показывает resolved/наследуемую модель — после feat-004 (`ModelSelector.tsx:72-75`) для `scope="project"` вместо «Активная модель: …» рендерится статичная подсказка про override. Проверить намеренность дизайн-решения; если регрессия — вернуть отображение resolved-модели. Чинится вместе с пунктом выше (тот же компонент) *(Frontend, из feat-009 follow-ups)*
- **P3** Empty-state Сферы знаний: иллюстрация мелкая — на пустой сфере брендовая иллюстрация занимает малую часть отведённой области и теряется; увеличить/растянуть под композицию экрана *(Frontend, cross: Design-branding)*
- **P3** Empty-state артефактов без выбранного артефакта — надпись «выберите артефакт из списка» не отцентрирована и стоит без иллюстрации; отцентрировать и догенерить сцену в стиле «Электрик» (pipeline: manifest/промпты design-branding feat-001 + cutout-рецепт feat-002) *(Frontend, cross: Design-branding)*
- **P3** UX сохранения имени проекта в настройках — редактирование через поле + отдельную кнопку «Сохранить» ощущается сыро; спроектировать паттерн (inline-edit с автосохранением/подтверждением по blur/Enter) *(Frontend)*
- **P3** Catch-all 404-экран — любой нелегитимный URL (включая `/security` при выключенном SIEM-флаге) рендерит пустой DOM: в `router.tsx` нет catch-all. Решение архитектора (гейт chore-001): всё, что не попадает в легитимные роуты, — общий экран «страница не найдена» (`path="*"` внутри layout-роута), не редирект. Решение архитектора (эта итерация): делается сразу полноценным — брендовый экран с иллюстрацией «Электрик», из feat-008 пункт изъят *(Frontend, cross: Design-branding, harvest chore-001)*
- **P2** Дизайн экранов авторизации (login/register) — перенесён из feat-008 (решение архитектора: весь UI-дизайн в одном полировочном пакете). Сейчас вход — generic shadcn-модалка с англоязычным копирайтом, без wordmark/иллюстрации/бренда «Электрик»; первый экран каждого пользователя. feat-008 перестраивает вход на функциональный каркас страницы `/login` (русский копирайт, FSD-структура `pages/login`, кнопки провайдеров по гео) — здесь поверх каркаса накатывается брендовая стилизация. Мокап auth-экранов — в общий интерактивный пакет мокапов итерации (состав по гео: пароль + Яндекс ID для РФ; Яндекс ID, Google, GitHub вне РФ — VK ID исключён, см. запись feat-008); реализация стилизации — после merge feat-008 *(Frontend, cross: Design-branding)*
- **P3** Дизайн-токен `--success` — решение архитектора (эта итерация): токен успеха вводится в дизайн-систему (обе темы), галочка успеха в ленте активности становится зелёной, как в мокапе live-timeline-v3 *(Frontend, cross: Design-branding, feat-001)*
- **P3** Владелец состояния экрана чата проставляется в момент колбэка, а не старта хода — `ChatThread.tsx` штампует `chatId` внутри колбэков `useAgentStream`: если пользователь переключил чат посреди хода и ход завершился после переключения, причина завершения / плашка ошибки припишется новому чату. Осталось узкое окно «терминальное событие ровно между переключением и следующей отправкой» (класс закрыт П6/П7 feat-001). Честный фикс — передавать идентификатор чата-владельца через колбэки хука, т.е. менять публичный контракт `useAgentStream`; вариант со ссылкой на «чат идущего потока» рассмотрен и отвергнут *(Frontend, выявлено feat-001 agent-visibility)*

#### Итог

Реализовано шестью непересекающимися треками в две волны в одной ветке; артефакты — `doc/tasks/iterations/dogfooding/feat-013-ui-polish/` (design-brief, мокапы, `tracks/T1..T6/{plan,summary,test-cases}.md`, два code review, кандидаты harvest и SOFA).

Дизайн-система получила токен `--success`, глобальные скроллбары с паритетом нативной и библиотечной полосы и единый шаблон состояний (`StateScreen` / `LoadingState` / `ErrorCard` / `Skeleton`) — на него переведены все списки и панели, включая новый экран 404. Баг сайдбара закрыт в корне: `/auth/me` выпадал из refresh-retry из-за префиксного правила исключений в интерцепторе. Владелец потока стал частью контракта колбэков `useAgentStream` с проверкой в сторе, чем закрыт класс «исход хода приезжает в чужой чат». Имя проекта редактируется на месте. Брендовый auth-дизайн изготовлен презентационным слоем (`features/auth/ui/LoginScreenView` + примитивы `AuthLayout`/`ProviderButton`) — без потребителя до merge feat-008, стыкуется через контракт props.

Автотесты: 593 кейса, каждый закрывающий кейс сдан с результатом мутационного прогона. Ручной хвост — 44 кейса пройдено, 41 помечен `👤 deferred` (нужны живой агент, реальные мутации или Firefox) и остаётся на приёмке архитектора; перепрогон блока 8 на живом маршруте `/login` — после merge feat-008.

Отложенное ушло в `backlog.md` (16 пунктов, из них три P2: `ErrorCard` без `role="alert"`, безусловная загрузка `auth-hero` под `lg`, непокрытое удаление проекта); процессные уроки — в конвенции (доказательство отката мутаций, ступень `data-slot` в лестнице запросов, класс флака под параллельной нагрузкой, `make bootstrap` для свежего worktree). На SOFA опубликовано пять TIL и один Question, отправлены два verify и один reply — реестр `doc/content/sofa/`.
