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
| feat-001 | ✅ Done | Agent Graph Skeleton — ReAct loop, AgentRunner, streaming |
| feat-002 | ✅ Done | Knowledge Sphere — Store, progressive disclosure, tools |
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

**Статус:** ✅ Done
**Blocked by:** ~backend-core/feat-001~ (снят, все backend-core итерации Done)
**Закрывает:** Agent Runtime backbone (граф, persistence, streaming)
**Ветка:** `feat/001-agent-graph`

#### Состав работ
- [x] Custom StateGraph: agent node + ToolNode + tools_condition (ADR-006)
- [x] Checkpointer (PostgreSQL) + Store (PostgreSQL) — compile с обоими
- [x] Agent node: минимальный system prompt, LLM call с bind_tools, базовый trim_messages
- [x] AgentRunner: stream() → domain events, get_history(), cancel() interface
- [x] Infra: LLM client init (ChatOpenAI via OpenRouter), Checkpointer/Store factory
- [x] Streaming маппинг: LangGraph stream_mode="messages" → domain event types (TextChunk, Done, Error)

#### Критерии приёмки
- [x] Граф компилируется с checkpointer и store
- [x] AgentRunner.stream() возвращает TextChunk и Done events
- [x] Диалог сохраняется в checkpointer: повторный запрос в тот же thread_id видит историю
- [x] `make check` (ruff check + ruff format + mypy) проходят

#### Артефакты
- [plan.md](iterations/agent/feat-001-agent-graph/plan.md)
- [summary.md](iterations/agent/feat-001-agent-graph/summary.md)
- `doc/tech/langgraph-reference.md` — секция Runtime/context_schema

---

### feat-002: Knowledge Sphere

**Цель:** долгосрочная память проекта через LangGraph Store. Агент видит Index шара при каждом запросе, подгружает полные секции по необходимости, обновляет шар сам.

**Статус:** ✅ Done
**Blocked by:** ~agent/feat-001~ (Done)
**Закрывает:** Knowledge Sphere (ADR-003, ADR-004, ADR-005)
**Ветка:** `feat/002-knowledge-sphere`

#### Состав работ
- [x] Формат KS: structured Markdown, multi-key Store design (один key per section)
- [x] Store namespace design: `("project", project_id, "sphere")`
- [x] Tools: get_section, create_section, update_section (fuzzy patch + overwrite), delete_section
- [x] ToolRuntime для доступа к project_id и Store в tools
- [x] Progressive disclosure: KS Index auto-derived и pre-loaded в system message, full sections — JIT через get_section
- [x] LangGraphSphereService для REST API (GET/PUT sphere через Store)

#### Критерии приёмки
- [x] CRUD tools работают через ToolRuntime + Store
- [x] get_section() возвращает полное содержание секции
- [x] create/update/delete отражаются в Index при следующем вызове agent node
- [x] Agent node инжектит KS Index в system message при каждом вызове
- [x] REST API (GET/PUT sphere) работает через LangGraphSphereService
- [x] `make check` (ruff check + ruff format + mypy) проходят

#### Артефакты
- [plan.md](iterations/agent/feat-002-knowledge-sphere/plan.md)
- [summary.md](iterations/agent/feat-002-knowledge-sphere/summary.md)
- `doc/tech/backend.md` — обновлены секции Tools и Context Engineering

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
