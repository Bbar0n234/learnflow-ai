# Индекс Backlog

## Нумерация задач в backlog

Для организации и навигации по задачам в `docs/backlog/` используется **префиксная нумерация**:

### Правила нумерации:
- **Хронологический порядок**: нумерация начинается с `01-` для самой первой реализованной задачи
- **Единая нумерация**: одна и та же задача имеет идентичный номер в `current/` и `archive/`
- **Формат**: `XX-TYPE-FEATURE/` где:
  - `XX` = порядковый номер (01, 02, ...)
  - `TYPE` = тип задачи (FEAT, SEC, BUG, REFACTOR, TEST, DOC, PERF)
  - `FEATURE` = ключевое слово функциональности (1-2 слова, максимально описательное)

### Жизненный цикл задачи:
1. **Планирование**: задача создается в `current/XX-TYPE-FEATURE/` с планами реализации
2. **Реализация**: планы заменяются на Post Implementation Summary в `current/XX-TYPE-FEATURE/impl/`
3. **Архивирование**: планы реализации перемещаются в `archive/XX-TYPE-FEATURE/`

## Текущие (current)

### Активные инициативы (август 2025)
- В настоящее время нет активных основных инициатив

### Завершенные инициативы (✅)
- `02-SEC-guardrails/` - Enhanced Guardrails Integration
- `03-FEAT-HITL/` - HITL Editing Agent
- `04-FEAT-HITL-CONFIG/` - Configurable HITL Service
- `05-FEAT-UI/` - Web UI Improvements
- `06-FEAT-PROMPTS/` - Prompt Configuration Service (MVP завершен)
  - `IP-01-post-implementation-summary.md` - ✅ Backend Core completed (2025-08-25)
  - `IP-02-post-implementation-summary.md` - ✅ LearnFlow Integration completed (2025-08-26)
  - `IP-03-post-implementation-summary.md` - ✅ Telegram UI Integration completed (2025-08-26)
- `07-FEAT-IMAGES/` - Унифицированная обработка изображений
  - `IP-01-post-implementation-summary.md` - ✅ Unified image processing completed (2025-08-26)
- `08-FEAT-LLM/` - Multi-provider LLM support
  - `IP-01-post-implementation-summary.md` - ✅ Multi-provider support completed (2025-08-26)
- `09-FEAT-EXPORT/` - Экспорт в Markdown и PDF
  - `IP-01-post-implementation-summary.md` - ✅ Export functionality completed (2025-08-26)

### Активные инициативы
- `10-FEAT-PROMPTS-GEN/` - Динамическая генерация промптов (планируется)

## Архив (archive)
Планы реализации (Implementation Plans), которые были перемещены из current/ после завершения задач:

- `01-FEAT-SPA.md` - ✅ Completed: Базовый React SPA
- `02-SEC-guardrails/` 
  - `IP-01-enhanced-guardrails-integration.md` - ✅ Completed: Enhanced Guardrails Integration
- `03-FEAT-HITL/`
  - `IP-01-edit-agent-integration.md` - ✅ Completed: Edit Agent Integration
- `04-FEAT-HITL-CONFIG/`
  - `IP-01-simplified-hitl-service.md` - ✅ Completed: Simplified HITL Service Architecture
- `05-FEAT-UI/`
  - `IP-01-simplified-ui-improvements.md` - ✅ Completed: UI улучшения (small fixes)
- `06-FEAT-PROMPTS/`
  - `IP-01-prompt-config-service-backend.md` - ✅ Completed: Prompt Configuration Service Backend (2025-08-25)
  - `IP-02-learnflow-integration.md` - ✅ Completed: LearnFlow Integration с Prompt Configuration Service (2025-08-26)
  - `IP-03-telegram-ui-integration.md` - ✅ Completed: Telegram Bot UI для управления промптами (2025-08-26)
- `07-FEAT-IMAGES/`
  - `IP-01-unified-image-processing.md` - ✅ Completed: Унифицированная обработка изображений в LearnFlow AI (2025-08-26)
- `08-FEAT-LLM/`
  - `IP-01-multi-provider-llm-support.md` - ✅ Completed: Multi-Provider LLM Support через OpenAI-совместимые API (2025-08-26)
- `09-FEAT-EXPORT/`
  - `IP-01-markdown-pdf-export.md` - ✅ Completed: Markdown и PDF экспорт заметок (2025-08-26)
- `misc/`
  - `IP-01-artifacts-manager.md` - ✅ Completed: Local Artifacts Manager implementation

