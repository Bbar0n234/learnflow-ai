# Backlog

Входящий поток задач из опытной эксплуатации и Langfuse. Элементы приоритизируются и тянутся в tasklist при триаже. После переноса в tasklist элемент удаляется из backlog — tasklist становится его новым домом (секция "Из backlog" в записи итерации).

Приоритеты: **P0** (блокер) / **P1** (важно) / **P2** (желательно) / **P3** (когда-нибудь)

Группировка по scope для параллельной работы. Cross-cutting элементы помечаются *(cross: scope)*.

## Frontend / UX

- **P1** Voice input — голосовой ввод сообщений агенту (STT) *(cross: Backend)*
- **P2** Design system — проработка дизайн-системы, визуальная идентичность, референсы
- **P3** Generative UI — агент адаптирует UI под задачу пользователя (диаграммы, чеклисты, графики). Требует исследования *(cross: Agent)*

## Agent

- **P3** Proactive KS maintenance — отдельный canvas для обсуждения актуализации Knowledge Sphere с агентом (параллельно с основной работой) *(cross: Frontend)*
- **P3** Message compaction: trim_messages выполняется безусловно, должен — только при превышении порога и неудачной суммаризации

## Cross-cutting

- **P1** Text feedback — текстовые комментарии к трейсам (расширение like/dislike), видимые в Langfuse *(Frontend + Backend + Langfuse)*
- **P2** File attachments — загрузка файлов агенту: документы, презентации, картинки. Продуманная и надёжная работа с файлами *(Frontend + Backend + Agent)*
- **P2** Per-user MCP management — UI для добавления/отключения MCP-серверов per user *(Frontend + Backend)*
