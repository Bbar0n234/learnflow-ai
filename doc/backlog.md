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
- **P3** Proactive KS maintenance — отдельный canvas для обсуждения актуализации Knowledge Sphere с агентом (параллельно с основной работой) *(cross: Frontend)*
- **P3** Message compaction: trim_messages выполняется безусловно, должен — только при превышении порога и неудачной суммаризации

## Backend

- **P2** REST API cleanup — привести API к REST best practices (аудит от 2026-04-04): отсутствует pagination на коллекциях (projects, chats, artifacts), POST create endpoints возвращают 200 вместо 201, DELETE feedback через POST с score=None вместо DELETE endpoint, нет стандартного envelope для list responses ({items, total, limit, offset}). Полный список: 8 пунктов, от notable до minor *(cross: Frontend)*

## Product / Distribution

- **P3** Public Material Sharing — публичные ссылки на материалы (Notion-style share-to-web). Преподаватель публикует → получает URL → студенты видят материал без регистрации. Потенциальный pivot от "инструмент подготовки" к "подготовка + дистрибуция". Зависит от Generative UI + Rich Export *(cross: Frontend, Backend, Infra)*

## Infra

- **P2** Self-hosted web search MCP — найти масштабируемый безлимитный (self-hosted) аналог Tavily/Firecrawl для веб-поиска агентом. Кандидаты: SearxNG + MCP-адаптер, open-webSearch. Текущий Firecrawl free tier ограничен по кредитам *(cross: Agent, Backend)*

## Security

- **P1** KS Write Guard — guard при записи в Knowledge Sphere (защита от memory poisoning). Тот же LLM classifier с контекстным промптом. При наличии фундамента feat-004 — минимальный effort *(Agent)*
- **P1** LLM Output Classifier — семантическая проверка ответа агента на утечку system prompt и internal data. Тот же BaseGuard, другой промпт *(Agent)*
- **P1** SUSPICIOUS → конкретные ограничения — определить и реализовать действия при SUSPICIOUS verdict (ограничение tools, алерт админу и т.д.) *(Agent, Backend)*
- **P2** SecurityObserver extraction — вынос Langfuse observability кода (~90 строк) из runner.py в отдельный SecurityObserver. Runner содержит business logic (вызов guard, verdict → action), observer инкапсулирует guardrail observations, score_trace, metadata. SRP: runner не должен знать о Langfuse internals *(Agent)*
- **P2** Tool Result Guard — проверка результатов MCP/tools на indirect prompt injection. Покрывает и безопасность user-added MCP серверов *(Agent)*
- **P2** Semantic Similarity output check — embedding-based проверка ответа на близость к system prompt *(Agent)*
- **P2** Async Guard — параллельная проверка guard с main LLM для снижения latency. Tool execution ждёт вердикта *(Agent)*
- **P2** Multi-turn escalation detection — обнаружение постепенных атак через серию сообщений *(Agent)*

## Cross-cutting

- **P1** Text feedback — текстовые комментарии к трейсам (расширение like/dislike), видимые в Langfuse *(Frontend + Backend + Langfuse)*
- **P2** File attachments — загрузка файлов агенту: документы, презентации, картинки. Продуманная и надёжная работа с файлами *(Frontend + Backend + Agent)*
- **P2** Per-user MCP management — UI для добавления/отключения MCP-серверов per user *(Frontend + Backend)*
