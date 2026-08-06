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
| feat-001 | A | 🚧 In Progress | cross-cutting | Видимость работы агента: карта событий, live-фазы, reasoning-стрим, след tool-вызовов, security_block в UI |
| chore-001 | B | 🚧 In Progress | cross-cutting | Prod-closing: kill-switch LLM-защиты + SIEM kill-switch, X-Forwarded-For, прод-образы без dev-deps; merge develop → main + деплой |
| feat-002 | C | 🚧 In Progress | cross-cutting | Chat UX: первое сообщение вместо title, auto-title отдельным модулем, удаление и переименование чатов |
| feat-003 | D | ✅ Done | agent | Модели: cost-optimal подбор по внешним бенчмаркам, whitelist 5+, pricing seed в Langfuse |
| feat-004 | E | 📋 Planned | cross-cutting | File attachments: вход файлов агенту (критический путь догфудинга) |
| feat-005 | F | 📋 Planned | backend | PDF-экспорт: замена wkhtmltopdf, рендер формул, фирменный стиль |
| feat-006 | G | 📋 Planned | agent | Генерация слайдов: spike → скилл/интеграция (паттерн ADR-026) |
| feat-007 | H | 📋 Planned | cross-cutting | Кастомные скиллы пользователя + страница библиотеки скиллов |
| feat-008 | I | 📋 Planned | cross-cutting | OAuth (Google/GitHub) + дизайн auth-экранов + 404-экран |
| feat-009 | J | 📋 Planned | infra | Self-hosted web search MCP |
| feat-010 | K | 📋 Planned | cross-cutting | Voice input (STT) |
| feat-011 | L | 📋 Planned | cross-cutting | Execution runtime: изолированное выполнение кода/CLI — общий фундамент PDF (F), слайдов (G), ГОСТ-скилла (M) |
| feat-012 | M | 📋 Planned | agent | ГОСТ-скилл: bundle-скилл оформления студенческих работ по ГОСТ 7.32 (.docx) — оффер для студенческой волны |

## Порядок и приоритеты

```
Авг W1     Финал A/B/C → merge develop → main → ДЕПЛОЙ (прод живой)
Авг W1–W2  feat-011 (L, runtime — фундамент F/G/M) ── feat-004 (E, attachments)
           ► СТАРТ ДОГФУДИНГА (лекция №1 мини-курса) — как только E готова
Авг W2     feat-005 (F, PDF — на runtime) ── feat-006 (G, слайды — на runtime)
Авг W2–W3  feat-012 (M, ГОСТ-скилл — на L+E) ── feat-008 (I, OAuth)
           → предпоказная полировка + бренд-кит (design-branding feat-005)
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

**Статус:** 🚧 In Progress
**Scope:** cross-cutting (Frontend + Backend + Agent)

#### Структура итерации

1. **Аудит → карта событий.** Полная инвентаризация пути LangGraph → SSE → фронт: все события, которые порождает граф (token-стрим, tool-вызовы, guard-фазы, субагентные токены, reasoning, запись в сферу, артефакты, ошибки/блокировки), что из этого доезжает до SSE, что до UI, что теряется. Артефакт — таблица «событие → есть сейчас → целевая визуализация → берём/не берём/потом». **Гейт 1: архитектор проходит по карте, решает состав.**
2. **Design-brief + мокапы** на утверждённый состав. Стартовые референсы — `iterations/post-mvp/feat-011-subagents-v1/mockups/live-feedback-variants.html` (V1 доставлен в feat-011, V2/V3 требуют серверной части). **Гейт 2: вкусовой выбор архитектора.**
3. **Реализация:** бэкенд-контракт (`streaming.md` переписывается) + фронт.

#### Из backlog

- **P1** Live-обратная связь в чате — серверный остаток. SSE-стрим не шлёт ни байта до первого события LangGraph: замерено 13–15 с тишины до первого `text_chunk` на тривиальном ответе (reasoning-модель + guard) и 47 с до первого события при tool-first ходе. Клиентский минимум закрыт в post-mvp feat-011 (`ThinkingIndicator` — черновой, перерабатывается здесь; first-byte-таймаут 30с→300с). Остаётся: (а) ack-событие при открытии стрима + периодический heartbeat в тишине — новый контракт в `streaming.md`; (б) фазовые состояния индикатора (guard → рассуждает → инструмент → review); (в) пересмотр таймаута — считать от heartbeat, не от первого байта; (г) ранний `tool_start` — эмитить из token-level стрима (`tool_call_chunks` в `stream_mode="messages"`), не дожидаясь завершения узла графа *(cross: Backend, Agent)*
- **P3** Стриминг reasoning-токенов в UI — отдельный SSE event type для рассуждений модели + сворачиваемая секция «агент рассуждает» в чате; закрывает основную долю воспринимаемой тишины на reasoning-моделях *(cross: Backend, Agent)*
- **P3** Системная проработка интерактивности вывода агента (зонт) — трансляция работы агента сделана примитивно: единственная плашка с сырым именем инструмента (`run_subagent`) на время выполнения — не видно, что это инструмент, не видно тип субагента, после завершения не остаётся следа в истории. Сюда: персистентный рендер tool-вызовов в истории сообщений, различимость субагентов (`agent_type` в payload + рендер), человекочитаемые названия инструментов *(Frontend, cross: Backend, Agent, Design-branding)*
- **P2** `security_block` SSE — тройной дрейф контракта (вскрыт усилением S5 feat-009): `streaming.md:30,34` документирует payload `{checkpoint, detection_layer}`; прод (`runner.py` + `block_reason`) эмитит `{reason}`; фронт `useAgentStream` не читает ни одного поля `security_block`. Возможный реальный UX/security-пробел: блокировка не доходит до пользователя. Согласовать контракт (док↔прод↔фронт) и довести событие до UI *(Frontend, Agent, cross: docs)*

#### Сознательно вне scope

- Rich-показ *результатов* инструментов (выборочный рендер результатов tool-вызовов) — отдельный дизайн-вопрос, отложен до потребности из догфудинга.
- SSE-дисконнект отменяет LangGraph-ран (потеря ответа) — стрим-ядро, но другая проблема (персистентность, не видимость); остаётся в backlog, кандидат на соло-итерацию в августе — для длинных субагентных ранов при догфудинге станет важной.

---

### chore-001 (B): Prod-closing — kill-switches + деплой в main

**Цель:** сделать merge `develop` → `main` нестрашным и задеплоить накопленное (>300 коммитов с последнего релиза): выключить в проде исследовательские подсистемы, закрыть известные прод-дефекты периметра, вычистить прод-образы.

**Статус:** 🚧 In Progress
**Scope:** cross-cutting (Backend + Agent + Infra)
**Параллельно с:** feat-001 (не пересекаются)

#### Из backlog

- **P2** Kill-switch LLM-защиты — per-env флаг полного отключения inline LLM-defense (SecurityGuard / LLM-классификатор, unicode-детектор, Universal I/O Guard, boundary enforcement). Мотив — LLM-защита артефакт исследования, не продуктовая потребность; в проде стоит лишних LLM-вызовов и latency без ценности. Default off в проде, включается под red-team прогон для статьи. Скоуп строго: только inline LLM-defense — НЕ трогает SIEM-пайплайн, auth, rate limiting, RBAC (обычная app-security остаётся 100%). Env-гигиена: `Settings` + `.env.example` + `.env.local.example` + `docker-compose.yml` *(Agent, Backend)*
- **P2** SIEM kill-switch — развилка «kill-switch ИЛИ допил до продакшна» решена архитектором в пользу **варианта A (kill-switch)**: SIEM реализован под учебную цель (дисциплина по ИБ, фундамент диплома) и её закрывает; для продакшна не годится (невалидируемый `config` правил, RBAC-guard пропускает не-админов), допиливать сейчас не будем. Per-env kill-switch по образцу kill-switch LLM-защиты; вариант B (допил: валидация правил, рабочий RBAC, активное реагирование) — вернётся при реальной потребности в живом SIEM (диплом / прод-нагрузка, см. backlog «SIEM → SOC evolution»). Следствие: post-mvp feat-007 (SIEM Extensions) — ⏸️ Paused *(Backend, SIEM, Security)*
- **P2** `X-Forwarded-For` доверяется безусловно — спуфинг IP: `backend/app/main.py` (request_id middleware) и `backend/app/api/routes/auth.py` (`_get_client_ip`) берут первый IP из XFF без проверки доверенного прокси. Следствия: обход per-IP rate-лимитов (подтверждено прогонами feat-002/feat-004), подмена IP в логах и SIEM-событиях. Решение — по факту топологии прода (читается из deploy-конфигов в рамках итерации): trusted-hops (N-й IP справа), `uvicorn --proxy-headers --forwarded-allow-ips`, конфиг-флаг `TRUST_PROXY_HEADERS` *(Backend, Auth, Security, Infra)*
- **P3** Прод-образы тащат dev-зависимости — `uv sync --all-packages` в `backend/Dockerfile` и `services/siem-service/Dockerfile` ставит dev-группу, включая test-harness (`learnflow-testing` → `testcontainers`, `pytest`, `factory-boy`). Почистить через `--no-dev`, проверив что entrypoint (alembic + uvicorn) не нуждается в dev-deps *(Infra)*

#### Завершение итерации

Смоук полного стека с выключенными тумблерами → merge `develop` → `main` (PR) → автодеплой → проверка на проде.

---

### feat-002 (C): Chat UX

**Цель:** переработка входа в чат: поле ввода — для первого сообщения, а не title; title генерирует модель; чаты можно удалять и переименовывать.

**Статус:** 🚧 In Progress
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

### feat-004 (E): File attachments

**Цель:** загрузка файлов агенту — документы, презентации, картинки; продуманная и надёжная работа с файлами. Критический путь догфудинга: агент изучает заметки/лекции/материалы пользователя — без ingestion на вход подготовка контента не работает, а выходные инструменты (слайды/PDF/картинки) без входа половинчаты.

**Статус:** 📋 Planned
**Scope:** cross-cutting (Frontend + Backend + Agent)

#### Из backlog

- **P1** File attachments (вход агента) — must-have baseline для dogfooding *(Frontend + Backend + Agent)*

#### Примечания к проектированию

Самая крупная фича тасклиста, требует полноценного design-brief: форматы (PDF/DOCX/MD/изображения?), ingestion-путь, размещение в контексте агента, хранение (смежно с `artifact_blobs` / `BlobStorage` из post-mvp feat-010), security (файл — untrusted вход: место в модели checkpoint'ов Sec 2.0).

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

### feat-008 (I): OAuth + auth-экраны + 404

**Цель:** авторизация через Google/GitHub + брендовые auth-экраны (одна связка — тот же экран, не красим дважды) + 404-экран. До показа преподавателям: вход без заведения отдельного пароля.

**Статус:** 📋 Planned
**Scope:** cross-cutting (Frontend + Backend + Design-branding)

#### Из backlog

- **P1** OAuth authentication (Google, GitHub) — сейчас только логин/пароль; требование хранить отдельный пароль сильно снижает конверсию. Именно OAuth, не email confirmation code. Затрагивает backend (провайдерская интеграция, token exchange, user linking), frontend (социальные кнопки, OAuth callback flow), `tech/auth.md`. Может потребовать ADR по user identity model при нескольких провайдерах на одного пользователя *(Frontend + Backend)*
- **P2** Дизайн экранов авторизации (login/register) — `app/components/AuthGate.tsx` сейчас generic shadcn-модалка с англоязычным копирайтом («Sign In»/«Create Account») в полностью русском UI, без wordmark/иллюстрации/бренда «Электрик». Первый экран каждого пользователя *(Frontend, cross: Design-branding)*
- **P2** 404 / Not-Found экран — отсутствует физически (нет catch-all `path="*"` в `router.tsx`): битый URL рендерит каркас с пустым `<Outlet/>`. Catch-all маршрут + брендовый экран. Дёшево, видимый прод-дефект *(Frontend, cross: Design-branding)*

---

### feat-009 (J): Self-hosted web search MCP

**Цель:** масштабируемый безлимитный веб-поиск для агента вместо ограниченного Firecrawl free tier.

**Статус:** 📋 Planned
**Scope:** infra (cross: Agent, Backend)

#### Из backlog

- **P2** Self-hosted web search MCP — найти self-hosted аналог Tavily/Firecrawl для веб-поиска агентом. Кандидаты: SearxNG + MCP-адаптер, open-webSearch. Текущий Firecrawl free tier ограничен по кредитам *(cross: Agent, Backend)*

Триггер может сработать раньше плана: активный догфудинг способен выесть кредиты Firecrawl — тогда итерация сдвигается вперёд.

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

**Статус:** 📋 Planned
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
