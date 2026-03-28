# ADR-007: MCP Client для External Tools

## Статус

Принято

## Контекст

Агенту нужны external tools: веб-поиск и чтение контента по URL. Вопрос: писать свои обёртки над SDK (Tavily, httpx) или подключать готовые MCP-серверы.

MCP (Model Context Protocol) — открытый стандарт для интеграции AI-агентов с инструментами. Экосистема зрелая: все крупные провайдеры (Firecrawl, Tavily, Jina AI, Exa, Brave) выпустили официальные MCP-серверы. LangGraph поддерживает MCP через `langchain-mcp-adapters` — MCP tools конвертируются в стандартные `BaseTool` и работают с prebuilt `ToolNode`.

## Решение

External tools подключаются через MCP Client. Конкретный MCP-сервер — вопрос конфигурации, не кода. Internal tools (KS, skills, artifacts) остаются Python-реализациями с прямым доступом к Store/State.

**Default MVP:** Firecrawl MCP — покрывает search + scrape + crawl + read в одном сервере.

**Adapter:** `langchain-mcp-adapters` (официальный пакет LangChain). `MultiServerMCPClient` для управления подключениями.

## Почему MCP, а не SDK

- **Нулевой код на external tools.** MCP-сервер предоставляет готовые tools — не нужно писать и поддерживать обёртки
- **Замена через конфиг.** Не устраивает Firecrawl → переключаем на Tavily + Jina без изменения кода агента
- **Production-grade качество.** Firecrawl/Jina/Tavily — специализированные сервисы с обработкой JS-heavy сайтов, rate limiting, error handling

## Что через MCP, что нет

| Категория | Через MCP | Почему |
|---|---|---|
| **Web search, URL reading** | Да | Stateless, заменяемые, готовые MCP-серверы |
| **KS tools** (get_sphere, update_sphere) | Нет | Тесно связаны с LangGraph Store/State |
| **Skills** (load_skill) | Нет | Управление контекстом агента, внутренняя механика |
| **Artifacts** (create_artifact) | Нет | Связан с app-managed persistence |

MCP Prompts рассматривались как механизм доставки skills — отклонено. По спеке Prompts user-controlled, агент не может автономно выбирать их. Нет trigger patterns, нет role:system. Zero real-world evidence использования для skills.

## Альтернативные MCP-серверы

| MCP Server | Покрытие | Free tier | Особенность |
|---|---|---|---|
| **Firecrawl** (выбран) | search + scrape + crawl + browser | 500 credits | All-in-one, 83% success rate в бенчмарках |
| **Tavily + Jina** | search (Tavily) + read URL (Jina) | 1k/мес + 10M tokens | Лучший AI-search + лучший URL→markdown |
| **Exa + Jina** | neural search + read URL | $10 + 10M tokens | Уникальный semantic search |
| **Brave** | search (6 типов) | $5/мес | Только поиск, нет crawling |

Firecrawl выбран как default: один сервер, полное покрытие, hosted remote transport. При проблемах — переключение на альтернативу через конфиг.

## Следствия

- External tools не требуют кода — только конфигурация MCP-подключения
- Зависимость: `langchain-mcp-adapters` (тонкий адаптер, не тяжёлый фреймворк)
- MCP tools и internal tools живут в одном `ToolNode` — единый execution path
- Infra: `Tavily client` заменяется на `MCP Client` (`MultiServerMCPClient`)
- `agent/tools/` содержит только internal tools; external приходят из MCP
