# Backend

Архитектура верхнего уровня и стек — в [vision.md](../vision.md). Здесь — детальное описание бэкенда: API, Agent Runtime, Persistence.

## API Layer

### Auth

Multi-user с простым разделением по пользователям. На MVP — идентификация по имени/нику, без паролей и сложной авторизации. Достаточно для разграничения данных между пользователями.

### Endpoints

#### Projects

| Метод | Путь | Назначение |
|-------|------|-----------|
| POST | `/projects` | Создать проект |
| GET | `/projects` | Список проектов пользователя |
| GET | `/projects/{id}` | Получить проект |
| PUT | `/projects/{id}` | Обновить (название и т.д.) |
| DELETE | `/projects/{id}` | Удалить проект |

#### Chats

| Метод | Путь | Назначение |
|-------|------|-----------|
| POST | `/projects/{id}/chats` | Создать чат в проекте |
| GET | `/projects/{id}/chats` | Список чатов проекта |
| GET | `/projects/{id}/chats/{cid}` | История чата (сообщения) |

#### Messages (ядро)

| Метод | Путь | Назначение |
|-------|------|-----------|
| POST | `/projects/{id}/chats/{cid}/messages` | Отправить сообщение → SSE stream с ответом агента |
| POST | `/projects/{id}/chats/{cid}/cancel` | Отменить генерацию |

Стриминг через SSE (Server-Sent Events) — индустриальный стандарт для LLM-проектов. LangGraph нативно поддерживает SSE через `stream_events`.

#### Knowledge Sphere

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/projects/{id}/sphere` | Текущий шар (полный) |
| PUT | `/projects/{id}/sphere` | Перезаписать шар |

Для разработки, отладки и будущего UI. PATCH (частичное обновление секций) — при необходимости.

#### Artifacts

| Метод | Путь | Назначение |
|-------|------|-----------|
| GET | `/projects/{id}/artifacts` | Список артефактов проекта |
| GET | `/projects/{id}/artifacts/{aid}` | Получить артефакт (метаданные + content) |
| GET | `/projects/{id}/artifacts/{aid}/download?format=md\|pdf` | Скачать в формате |

PDF — конвертация из Markdown на бэкенде (pandoc / weasyprint).

### Schemas

Pydantic request/response модели. Проектируются отдельно, до начала реализации.

## Agent Runtime

### General Agent

General Agent с ReAct loop — подробнее в [ADR-001](adr/ADR-001-general-agent.md).

```
General Agent = Based Prompt + ReAct Loop + Context Engineering + Memory + Tool Use
```

- **Based Prompt** — правила поведения агента (см. ниже)
- **ReAct Loop** — Reason → Action → Observe → Adjust, цикл до достижения цели
- **Context Engineering** — управление тем, что попадает в контекст и когда
- **Memory** — short-term (диалог) + long-term (Knowledge Sphere)
- **Tool Use** — вызов инструментов через единый интерфейс

Реализация на LangGraph. Checkpointer и Store — PostgreSQL с первого дня.

### Based Prompt

Текст промпта проектируется при реализации (Phase D). Здесь фиксируем, что Based Prompt должен покрывать:

- **Мышление и планирование** — как агент рассуждает, декомпозирует задачу
- **Реакция на ошибки** — что делать при сбое tool, неожиданном результате
- **Взаимодействие с пользователем** — тон, формат ответов, когда уточнять
- **Границы поведения** — что агент не делает, когда отказывает
- **Работа с контекстом** — когда подгружать skills, когда обращаться к шару

### Memory

#### Short-term

История сообщений в пределах чата. LangGraph Checkpointer.

Compaction при приближении к лимиту контекста: суммаризация истории с сохранением ключевых решений, нерешённых вопросов и текущего фокуса. Подробнее — [ADR-004](adr/ADR-004-progressive-disclosure.md).

#### Long-term (Knowledge Sphere)

Связанная картина проекта, а не набор атомарных фактов. Подробнее — [ADR-003](adr/ADR-003-knowledge-sphere.md).

**Управление (MVP):** Main Agent сам решает, когда обновить шар, и вызывает tool `update_sphere`. Полный контекст диалога → качественное решение. Отдельный Classifier / KS Agent — при реальных проблемах (перегрузка контекста, cost). Подробнее: [ADR-005](adr/ADR-005-ks-update-mechanism.md).

**Два режима:**
1. Автономный — работает тихо, не грузит пользователя
2. Проактивный — пользователь видит шар, может править

**Хранение:** LangGraph Store + PostgreSQL. MVP-формат — структурированный Markdown. Миграция на Knowledge Graph с embeddings — при реальных failure modes (шар > 50k токенов).

### Skills

Skills в формате Claude Code — подгружаемые модули знаний, расширяющие поведение агента. Общепринятый стандарт, набирающий обороты в индустрии (Claude Code, Cursor и др.). Подробнее — [ADR-002](adr/ADR-002-skills-system.md).

**MVP:** файловая система + API-обёртка для подгрузки.

**Структура skill'а:** описание + паттерны (триггеры) + знания (prompts, docs).

**Планируемые skills:** structure, research.

**Lifecycle:** задача пользователя → агент подгружает skill (just-in-time) → использует → skill выгружается.

### Tools

#### Internal (работа с системой)

```
get_sphere_index() → SphereIndex
```
Получить Index шара знаний. Pre-loaded в контексте при старте чата, доступен как tool для повторного запроса.

```
get_section(section_id: str) → SectionContent
```
Получить Full секцию шара. Just-in-time подгрузка по решению агента.

```
load_skill(skill_name: str) → SkillContent
```
Подгрузить skill в контекст. Just-in-time.

```
update_sphere(facts: str) → UpdateResult
```
Обновить Knowledge Sphere новыми фактами из диалога. Main Agent вызывает когда считает нужным (см. [ADR-005](adr/ADR-005-ks-update-mechanism.md)).

#### External

```
web_search(query: str) → SearchResults
```
Web search через Tavily. Для research-сценариев (UC-2). Возвращает найденные источники (URL, title, сниппеты).

```
read_url(url: str) → PageContent
```
Полное чтение контента по URL. Используется после web_search для углублённого изучения найденного источника.

#### Artifacts

```
create_artifact(title: str, content: str, type: str) → ArtifactRef
```
Сохранить результат работы агента как артефакт проекта. Возвращает artifact_id. Фронтенд рендерит карточку файла вместо инлайн-текста.

### Context Engineering

Управление контекстом агента. Подробнее — [ADR-004](adr/ADR-004-progressive-disclosure.md).

| Что | Стратегия |
|-----|-----------|
| Knowledge Sphere Index | Pre-loaded (всегда в контексте) |
| Full sections шара | Just-in-time (через tool) |
| История диалога | В контексте + compaction при приближении к лимиту |
| Skills | Just-in-time (подгружаются когда нужны) |

## Persistence

### Сущности

```
User
├── id, name, created_at

Project
├── id, user_id, name, created_at, updated_at

Chat
├── id, project_id, title, created_at

Message
├── id, chat_id, role (user | assistant | tool), content, created_at

KnowledgeSphere
├── id, project_id, content (Markdown), updated_at

Artifact
├── id, project_id, chat_id, title, type (markdown | ...), content, created_at

Checkpoint (LangGraph)
├── managed by LangGraph Checkpointer
```

### Связи

```
User 1 → N Project
Project 1 → N Chat
Project 1 → 1 KnowledgeSphere
Project 1 → N Artifact
Chat 1 → N Message
Chat N → 1 Artifact (артефакт создаётся в контексте чата)
```

### Хранение

- **PostgreSQL** — основное хранилище для всех сущностей
- **LangGraph Checkpointer** → PostgreSQL — состояние агента (history, intermediate steps)
- **LangGraph Store** → PostgreSQL — Knowledge Sphere
