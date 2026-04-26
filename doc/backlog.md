# Backlog

Входящий поток задач из опытной эксплуатации и Langfuse. Элементы приоритизируются и тянутся в tasklist при триаже. После переноса в tasklist элемент удаляется из backlog — tasklist становится его новым домом (секция "Из backlog" в записи итерации).

Приоритеты: **P0** (блокер) / **P1** (важно) / **P2** (желательно) / **P3** (когда-нибудь)

Группировка по scope для параллельной работы. Cross-cutting элементы помечаются *(cross: scope)*.

## Frontend / UX

- **P1** Voice input — голосовой ввод сообщений агенту (STT) *(cross: Backend)*
- **P2** Design system — проработка дизайн-системы, визуальная идентичность, референсы
- **P3** Generative UI — агент решает, какой UI-компонент отрисовать. Гибрид: pre-built React-компоненты + конфигурируемые свойства (размер, цвет, расположение) через schema. Ориентир протокола — Google A2UI. Ресерч завершён (`doc/research/generative-ui-research-report.md`) *(cross: Agent, Backend)*
- **P3** Rich Material Export — экспорт интерактивных UI-материалов с сохранением визуального качества (не markdown-дамп). Форматы: static HTML bundle, PDF, или оба. Зависит от Generative UI *(cross: Backend)*

## Agent

- **P2** LangGraph Store deep-dive — изучить Store вдоль и поперёк: все возможности, лимиты, best practices, продвинутые паттерны (semantic search, IndexConfig, cross-namespace стратегии). Цель — максимально использовать Store как unified memory backend
- **P2** Reasoning ChatOpenAI everywhere — convention + migration. Все модели проекта (security guard, summarizer, main agent, future sub-agents) используют `ReasoningChatOpenAI`, не plain `ChatOpenAI`. Reasoning виден в Langfuse — критично для guard verdict debug, summarizer behavior analysis, main agent improvement loop. Pattern уже реализован в коде; нужно: (a) добить остальные модели (summarizer, guard) на `ReasoningChatOpenAI`; (b) зафиксировать convention в `doc/tech/conventions.md` (формулировка примерно: "все модели в проекте используют `ReasoningChatOpenAI` by default; exception только для явно non-reasoning моделей"). Связано с существующим P2 "Guard LLM reasoning" в Security — закрывается частично *(Agent)*
- **P2** Model whitelist expansion — расширить whitelist моделей в `agent.yaml` минимум до 5 основных (текущий: GLM-5, Gemini 1.5 Pro). Добавить минимум GLM-5.1, остальной список основных моделей — на этапе реализации. Включить pricing initialization в Langfuse через lifespan для всех новых моделей (включая текущую guard model — её стоимость сейчас не видна в Langfuse). Связано с существующим P2 "Guard LLM observability" в Security *(Agent)*
- **P3** Proactive KS maintenance — отдельный canvas для обсуждения актуализации Knowledge Sphere с агентом (параллельно с основной работой) *(cross: Frontend)*
- **P3** Message compaction: trim_messages выполняется безусловно, должен — только при превышении порога и неудачной суммаризации

## Backend

- **P2** REST API cleanup — привести API к REST best practices (аудит от 2026-04-04): отсутствует pagination на коллекциях (projects, chats, artifacts), POST create endpoints возвращают 200 вместо 201, DELETE feedback через POST с score=None вместо DELETE endpoint, нет стандартного envelope для list responses ({items, total, limit, offset}). Полный список: 8 пунктов, от notable до minor *(cross: Frontend)*

## Product / Distribution

- **P3** Public Material Sharing — публичные ссылки на материалы (Notion-style share-to-web). Преподаватель публикует → получает URL → студенты видят материал без регистрации. Потенциальный pivot от "инструмент подготовки" к "подготовка + дистрибуция". Зависит от Generative UI + Rich Export *(cross: Frontend, Backend, Infra)*

## Infra

- **P2** Self-hosted web search MCP — найти масштабируемый безлимитный (self-hosted) аналог Tavily/Firecrawl для веб-поиска агентом. Кандидаты: SearxNG + MCP-адаптер, open-webSearch. Текущий Firecrawl free tier ограничен по кредитам *(cross: Agent, Backend)*

## Security

- **P2** Async Guard — параллельная проверка guard с main LLM для снижения latency. Tool execution ждёт вердикта *(Agent)*
- **P2** Multi-turn escalation detection — текущий classifier видит history, отдельный механизм not planned; пересматриваем при появлении подтверждённого FN-класса, который history-aware classifier стабильно пропускает *(Agent)*
- **P3** Trust-tier formalization для internal tools — если выйдет class internal tools, чьи outputs регулярно конфликтуют с защитными слоями (по аналогии с tool result + skills corpus), описать tier-механизм для исключений *(Agent)*
- **P3** User MCP attack probe в eval-наборе — добавить attack probe для пункта «User MCP → единая строгость» при возврате eval-инфраструктуры из parked-режима *(Agent)*
- **P3** Глобальный refactor паттерна `get_db_session` commit — активируется при повторном проявлении 404-симптома в других routes (сейчас покрыт точечным фиксом в ChatService, конвенция — в conventions.md) *(Backend)*
- **P3** Guard observations иерархия в Langfuse UI — guards рендерятся как siblings root span, не вложены в позицию между iter'ами agent node. Не блокирует observability; ремедиация требует синхронизации CallbackHandler vs OTel scope, low value *(Agent)*

## Cross-cutting

- **P1** Text feedback — текстовые комментарии к трейсам (расширение like/dislike), видимые в Langfuse *(Frontend + Backend + Langfuse)*
- **P2** File attachments — загрузка файлов агенту: документы, презентации, картинки. Продуманная и надёжная работа с файлами *(Frontend + Backend + Agent)*
- **P2** Per-user MCP management — UI для добавления/отключения MCP-серверов per user *(Frontend + Backend)*
- **P1** OAuth authentication (Google, GitHub) — сейчас только логин/пароль. Перед публичным запуском — must-have: требование хранить отдельный пароль для сервиса сильно снижает конверсию. Полноценная OAuth-интеграция через Google и GitHub (не email confirmation code, а именно OAuth). Затрагивает backend (провайдерская интеграция, token exchange, user linking), frontend (социальные кнопки логина, OAuth callback flow), `tech/auth.md` (актуализация). Может потребовать ADR по user identity model при нескольких OAuth-провайдерах для одного пользователя *(Frontend + Backend)*

## Meta (Backlog & Workflow Infrastructure)

_Мета-работа над процессом и инструментами разработки, не фичи продукта._

- **P1** AIDD skill actualization (initial) — разовое обновление `aidd-methodology` skill: зафиксировать continuous improvement паттерн в двух режимах. **Режим 1 — explicit initialization:** ручной проход 1-2 примеров → черновик правил/промпта → свежий агент с пустым контекстом применяет черновик → сравниваем с ожиданиями → правим формулировку (не примеры) → итерация, пока свежий агент не воспроизводит ожидаемое. **Режим 2 — continuous root-cause maintenance:** при промахе компонента workflow (агент затупил, ревьюер пропустил, чек-лист не покрыл) — фиксим первопричину в источнике (промпт, документ, чек-лист, инструкция), не только симптом. После initial-актуализации skill становится постоянным аккумулятором методологических находок по мере применения паттерна (как писать документацию, как формулировать чек-листы, как составлять промпты ревьюерам)
- **P1** `.harness/prompts/` directory + workflow.md linking — создать директорию `.harness/prompts/` в корне репо как контейнер для промптов workflow-агентов (инструмент dev workflow, не часть доменной документации проекта). В `workflow.md` — отдельная таблица "роль агента → путь к промпту → короткое описание", чтобы новый агент при чтении `workflow.md` видел весь harness сразу. На этом этапе директория создаётся пустой; наполнение — в рамках Workflow-agent prompts formalization
- **P3** GitHub PRs migration research — изучить возможность и стоимость миграции `backlog.md` в GitHub Issues/Projects с сохранением agent-friendly интерфейса (через `gh` CLI). Сейчас Markdown работает нормально, миграция — вопрос "более взрослого формата", не текущей боли. Исследовательская задача: как агент будет создавать/читать/обновлять issues в рамках iteration workflow, не перегружая контекст. Решение о миграции — после результатов

## Agent Harness & Workflow

_Формализация multi-agent dev workflow, промпты workflow-агентов, детерминированные проверки, systematic fixes инфраструктуры разработки._

- **P1** Multi-agent workflow diagram & description — дополнить `workflow.md` полным описанием multi-agent dev workflow как он реально работает. Сейчас `workflow.md` описывает процесс линейно (план → реализация → верификация); нужно добавить срез по ролям агентов: 8 ролей (planner, plan reviewer, implementer, implementation reviewer, code reviewer, evaluator, doc actualizer, doc reviewer), кто кого ревьюит, где handoff points, где нужен чистый контекст, какой промпт применяется на каждом шаге. Диаграмма — Mermaid. Становится source of truth для того, как архитектор делегирует работу
- **P1** Workflow-agent prompts formalization — вытащить промпты для всех 8 workflow-агентов из заметок/Телеграма в `.harness/prompts/` как версионируемые файлы. Частично формализуем существующие (planner, plan reviewer, implementation reviewer, code reviewer — сейчас уже используются, но живут вне репо), частично формулируем заново (evaluator и doc actualizer сейчас запускаются "произвольным промптом", doc reviewer как отдельный агент ещё не существует). Каждый промпт формулируется через continuous improvement: ручной проход на 1-2 реальных кейсах → черновик промпта → свежий агент с пустым контекстом применяет промпт → сравниваем с ожиданиями → правим формулировку → итерация. Связанная работа, не разносим по отдельным пунктам; дробление на итерации — на этапе tasklist
- **P2** Arch-checker (deterministic layer rules) — детерминированные проверки архитектурных инвариантов: направление зависимостей между слоями (handlers → services → repositories, не в обратную), отсутствие синглтонов там, где запрещено, запрет cross-slice imports, запрет прямого DB-доступа из handlers. Интегрируется в pre-commit hook или CI. Предпосылка — Layers & abstractions diagram. Tentative инструменты: `import-linter`, свои AST-чекеры, либо комбинация *(cross: Documentation Quality)*
- **P2** Error return types conventions — сформулировать и встроить в code reviewer конвенцию на error return types. Сейчас непоследовательно: где-то exceptions, где-то Result/Either, где-то Optional + None. Определить границы применимости каждого подхода (например: exceptions — неожидаемые ошибки и границы системы; Result/Either — ожидаемые бизнес-ошибки; Optional — отсутствие значения без ошибки). Калибруется через continuous improvement на реальных местах кода
- **P2** Logging conventions enforcement in code reviewer — сами logging conventions уже есть в `conventions.md` (structlog, keyword-args, level semantics). Нужно встроить проверку соответствия этим конвенциям в промпт code reviewer как отдельный чек-лист. Сами conventions не меняем — меняем только reviewer
- **P2** Kill-process bug systematic fix — разобраться, почему Claude Code регулярно не убивает процессы с первого раза при работе с `make`-таргетами (повторяющаяся проблема: агент думает, что убил процесс, потом видит занятый порт). Гипотезы: нюансы среды Claude Code, особенности process trees в Docker/host setup, сигналы SIGTERM vs SIGKILL, race conditions в `make`-wrappers. Ресёрч + systematic fix в sandbox settings / wrapper-скриптах / CLAUDE.md — не точечный workaround

## Documentation Quality & Architecture

_Работа над качеством существующей арх-документации и создание сводных архитектурных документов._

- **P2** Tech/ full documentation audit — пройтись по всем документам в `tech/` через doc reviewer по принципам, зафиксированным в `conventions.md` (раздел Documentation) и скилле `aidd-methodology`. Выявить проблемные точки, завести точечные итерации на рефакторинг. Зависит от существования doc reviewer как формализованного агента (Workflow-agent prompts formalization)
- **P2** Layers & abstractions diagram — сводная диаграмма слоёв и направлений зависимостей между ними (backend: handlers / services / repositories; agent runtime; frontend: features / shared). Mermaid. Два назначения: (1) артефакт для обсуждения архитектуры в проекте на высоком уровне, (2) база для Arch-checker правил (они ссылаются на слои, описанные в диаграмме). Точное место в `doc/` — при реализации
- **P2** REST API contracts summary — сводный документ с REST API контрактами со всех сервисов. **Не дубль** `tech/backend.md` (там живут детали реализации) — обзорная страница "где какой endpoint живёт, какой контракт, какие коды ответа, какая аутентификация". Полезна при cross-service обсуждениях и при планировании работ, затрагивающих несколько API. Роль документа явно обозначена как "summary / overview", не как "source of truth", чтобы избежать дрейфа дубликации
- **P2** DB architecture summary — аналогично REST summary, но для базы: таблицы по сервисам, связи, ключевые invariants, соглашения по миграциям. Не дубль Alembic-миграций и не дубль SQLAlchemy models — обзорный документ
- **P3** Move `langgraph-store-deepdive.md` to research/ — сейчас `tech/langgraph-store-deepdive.md` лежит в технической документации, но по содержанию это deep-dive ресёрч, не архитектурный документ проекта. Перенести в `research/`, обновить ссылки в `doc/index.md` и CLAUDE.md. Отдельно от существующего P2 "LangGraph Store deep-dive" в Agent-секции (это другой пункт — планируемый research-проект, не перенос файла)

## Tech Debt & Competency

_Плановый техдолг и развитие компетенций архитектора по техническому стеку проекта._

- **P2** REST API audit + refactor via api-design-principles skill — пройтись по API-endpoints через skill, выявить несоответствия REST best practices. **Пересекается** с существующим P2 "REST API cleanup" в Backend-секции (аудит от 2026-04-04 с конкретным списком из 8 пунктов). При реализации возможно объединить в одну итерацию. Результат: обновлённый код + REST-конвенции в `conventions.md` (через continuous improvement на примерах)
- **P2** DB architecture audit via postgresql skill — пройтись по схеме БД и запросам через skill, выявить потенциальные проблемы (индексы, constraints, типы, плохо спроектированные связи). Результат: обновлённая схема (если нужно), миграции, tentative DB-конвенции
- **P2** LangGraph / LangChain audit via langchain-architecture skill — пройтись по agent runtime через skill, выявить устаревшие паттерны. Проект использует raw LangGraph (не LangChain wrappers), но scope для улучшений всё равно может быть. Связано с существующим P2 "LangGraph Store deep-dive" в Agent-секции — возможно проводится вместе
- **P3** Frontend stack deep-read — целенаправленное погружение архитектора в фронтенд-код проекта (React/TypeScript) для прокачки компетенции. **Не задача по коду и не рефакторинг** — задача по компетенции архитектора, без которой невозможно выстраивать серьёзную архитектуру фронтенда
- **P3** Linter/formatter stack deep-read — целенаправленное изучение конфигов и правил `ruff` / `mypy` / `eslint` / `prettier` для прокачки компетенции. Аналогично frontend: цель — экспертиза, а не рефакторинг
