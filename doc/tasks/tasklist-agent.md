# Tasklist: Agent Runtime

## Контекст

Ядро продукта — агентная система: LangGraph-граф, tools, skills, context engineering, memory, Knowledge Sphere.

**Документы:** [backend.md](../tech/backend.md) (Agent Runtime, AgentRunner, Tools, Graph), [ADR-001](../tech/adr/ADR-001-general-agent.md)–[ADR-007](../tech/adr/ADR-007-mcp-external-tools.md), [langgraph-reference.md](../tech/langgraph-reference.md)

**Зависимости:** Infrastructure Setup, Backend Core (persistence, infra clients)

## Легенда

- 📋 Planned
- 🚧 In Progress
- ✅ Done
- ⏸️ Paused
- ❌ Cancelled

## Overview

| Итерация | Статус | Закрывает |
|----------|--------|-----------|
| feat-001 | 📋 Planned | Agent Graph Skeleton — ReAct loop, AgentRunner, streaming |
| feat-002 | 📋 Planned | Knowledge Sphere — Store, progressive disclosure, tools |
| feat-003 | 📋 Planned | Skills System + Artifacts tool |
| feat-004 | 📋 Planned | MCP External Tools — Firecrawl integration |
| feat-005 | 📋 Planned | Based Prompt & Context Engineering |

## Быстро меняющиеся инструменты

| Инструмент | Источник |
|-----------|----------|
| LangGraph (StateGraph, prebuilt, Store, Checkpointer) | `inspect` пакета, скилл langgraph-patterns, MCP docs-langchain |
| langchain-core (messages, tools, runnables) | `inspect` пакета, MCP docs-langchain |
| langchain-mcp-adapters | firecrawl → PyPI/GitHub |
| langchain-anthropic / langchain-openai | `inspect` пакета, firecrawl → docs |
| langgraph-checkpoint-postgres | `inspect` пакета, firecrawl → PyPI |
| Firecrawl MCP | firecrawl → docs |

## Итерации

### feat-001: Agent Graph Skeleton

**Цель:** минимально работающий агент — LangGraph-граф с ReAct loop, PostgreSQL persistence, AgentRunner со streaming. Можно отправить сообщение и получить стримингом ответ LLM.

**Статус:** 📋 Planned
**Blocked by:** backend-core/feat-001 (infra/db.py — engine для checkpointer/store)
**Закрывает:** Agent Runtime backbone (граф, persistence, streaming)
**Ветка:** `feat/001-agent-graph`

#### Состав работ
- [ ] Custom StateGraph: agent node + ToolNode + tools_condition (ADR-006)
- [ ] Checkpointer (PostgreSQL) + Store (PostgreSQL) — compile с обоими
- [ ] Agent node: минимальный system prompt, LLM call с bind_tools, базовый trim_messages
- [ ] AgentRunner: stream() → domain events, get_history(), cancel() interface
- [ ] Infra: LLM client init (ChatAnthropic/ChatOpenAI), Checkpointer/Store factory
- [ ] Streaming маппинг: LangGraph stream_events → domain event types (TextChunk, Done, Error)

#### Критерии приёмки
- [ ] Граф компилируется с checkpointer и store
- [ ] AgentRunner.stream() возвращает TextChunk и Done events
- [ ] Диалог сохраняется в checkpointer: повторный запрос в тот же thread_id видит историю
- [ ] `make lint && make type-check` проходят

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-002: Knowledge Sphere

**Цель:** долгосрочная память проекта через LangGraph Store. Агент видит Index шара при каждом запросе, подгружает полные секции по необходимости, обновляет шар сам.

**Статус:** 📋 Planned
**Blocked by:** agent/feat-001
**Закрывает:** Knowledge Sphere (ADR-003, ADR-004, ADR-005)
**Ветка:** `feat/002-knowledge-sphere`

#### Состав работ
- [ ] Формат KS: structured Markdown, дизайн секций (Index + Full sections)
- [ ] Store namespace design: `("project", project_id, "sphere")`
- [ ] Tools: get_sphere_index(), get_section(section_id), update_sphere(facts)
- [ ] InjectedStore + RunnableConfig для доступа к project_id в tools
- [ ] Progressive disclosure: KS Index pre-loaded в agent node, full sections — JIT через tool

#### Критерии приёмки
- [ ] get_sphere_index() возвращает Index из Store для текущего проекта
- [ ] get_section() возвращает полное содержание секции
- [ ] update_sphere() записывает данные в Store, повторный get_sphere_index() отражает изменения
- [ ] Agent node инжектит KS Index в system message при каждом вызове
- [ ] `make lint && make type-check` проходят

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-003: Skills System + Artifacts

**Цель:** подгружаемые модули знаний (skills) через файловую систему и создание артефактов (файлов) в рамках проекта.

**Статус:** 📋 Planned
**Blocked by:** agent/feat-001, backend-core/feat-003 (ArtifactRepository)
**Закрывает:** Skills (ADR-002), Artifacts tool
**Ветка:** `feat/003-skills-artifacts`

#### Состав работ
- [ ] Skills: директория agent/skills/, формат файла (description + patterns + knowledge)
- [ ] Tool: load_skill(skill_name) — read from filesystem, вернуть содержимое
- [ ] Tool: create_artifact(title, content, type) — запись в app DB через repository
- [ ] Streaming events: tool_start/tool_end для всех tools, artifact_created для create_artifact

#### Критерии приёмки
- [ ] load_skill() возвращает содержимое skill-файла по имени
- [ ] create_artifact() создаёт запись в таблице Artifact, возвращает artifact_id
- [ ] Streaming отдаёт tool_start/tool_end при вызове любого tool
- [ ] Streaming отдаёт artifact_created при создании артефакта
- [ ] `make lint && make type-check` проходят

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-004: MCP External Tools

**Цель:** внешние инструменты (web search, URL reading, crawling) через MCP. Default: Firecrawl MCP. Провайдер заменяем через конфигурацию.

**Статус:** 📋 Planned
**Blocked by:** agent/feat-001
**Закрывает:** External Tools (ADR-007)
**Ветка:** `feat/004-mcp-tools`

#### Состав работ
- [ ] Infra: MultiServerMCPClient setup, MCP-конфигурация в Settings (transport, URL, API keys)
- [ ] Firecrawl MCP server connection
- [ ] langchain-mcp-adapters: конвертация MCP tools → BaseTool
- [ ] Unified ToolNode: internal tools + MCP tools в одном ToolNode

#### Критерии приёмки
- [ ] MCP client подключается к Firecrawl серверу при старте
- [ ] MCP tools доступны агенту наравне с internal tools
- [ ] Агент может выполнить web search через MCP tool и вернуть результат
- [ ] Смена MCP-провайдера не требует изменения кода (только config)
- [ ] `make lint && make type-check` проходят

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-005: Based Prompt & Context Engineering

**Цель:** полноценный системный промпт и стратегия управления контекстом. Агент рассуждает осмысленно, эффективно использует tools и память, gracefully обрабатывает ошибки и длинные сессии.

**Статус:** 📋 Planned
**Blocked by:** agent/feat-002, agent/feat-003, agent/feat-004
**Закрывает:** Based Prompt, Context Engineering (ADR-004)
**Ветка:** `feat/005-prompt-context`

#### Состав работ
- [ ] Based Prompt: мышление и планирование, реакция на ошибки, взаимодействие с пользователем, границы поведения, работа с контекстом (KS, skills, tools)
- [ ] KS Index injection в system message (refinement)
- [ ] Message trimming: token counting, strategy, параметры
- [ ] History compaction: суммаризация при приближении к лимиту контекста
- [ ] Тестирование на use-cases из [use-cases.md](../product/use-cases.md)

#### Критерии приёмки
- [ ] Агент корректно использует tools по назначению (не вызывает лишних, не пропускает нужных)
- [ ] При длинном диалоге (>50 сообщений) агент не теряет контекст — compaction срабатывает
- [ ] Агент обновляет KS по ходу работы без явного запроса пользователя
- [ ] Ответы агента соответствуют тону и формату, заданному в Based Prompt
- [ ] `make lint && make type-check` проходят

#### Артефакты
<!-- Заполняется по мере работы -->
