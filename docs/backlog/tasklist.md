# Task List

## О системе управления задачами

Единый иерархический список всех работ проекта LearnFlow AI.

### Принципы организации:
- **Единый список** - все задачи в одном месте без перемещений между секциями
- **Статусы** - каждый элемент имеет свой статус: 💡 Идея | 📋 Запланировано | 🚀 В работе | ✅ Завершено | ⏸️ Приостановлено
- **Иерархия** - Milestone > Initiative > Task > Subtask
- **Нумерация** - XX-TYPE-NAME для задач, M1-M4 для milestones

### Правила нумерации задач:
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

## Список задач

### M1: Open Source Release [✅ Завершено: Август 2025]
Публичный релиз с базовым функционалом

#### 01-FEAT-SPA - React SPA [✅]
- Базовая реализация React приложения
- Завершено: 2025-08-20
- Документация: `archive/01-FEAT-SPA.md`

#### 02-SEC-guardrails - Enhanced Guardrails Integration [✅]
- IP-01: Enhanced guardrails integration
- Завершено: 2025-08-22
- Документация: `current/02-SEC-guardrails/`

#### 03-FEAT-HITL - HITL Editing Agent [✅]
- IP-01: Edit Agent Integration
- Завершено: 2025-08-23
- Документация: `current/03-FEAT-HITL/`

#### 04-FEAT-HITL-CONFIG - Configurable HITL Service [✅]
- IP-01: Simplified HITL Service Architecture
- Завершено: 2025-08-24
- Документация: `current/04-FEAT-HITL-CONFIG/`

#### 05-FEAT-UI - Web UI Improvements [✅]
- IP-01: UI улучшения (small fixes)
- Завершено: 2025-08-24
- Документация: `current/05-FEAT-UI/`

#### 06-FEAT-PROMPTS - Prompt Configuration Service [✅]
- IP-01: Backend Core - Завершено: 2025-08-25
- IP-02: LearnFlow Integration - Завершено: 2025-08-26
- IP-03: Telegram UI Integration - Завершено: 2025-08-26
- Документация: `current/06-FEAT-PROMPTS/`

#### 07-FEAT-IMAGES - Унифицированная обработка изображений [✅]
- IP-01: Unified image processing
- Завершено: 2025-08-26
- Документация: `current/07-FEAT-IMAGES/`

#### 08-FEAT-LLM - Multi-provider LLM support [✅]
- IP-01: Multi-provider support через OpenAI-совместимые API
- Завершено: 2025-08-26
- Документация: `current/08-FEAT-LLM/`

#### 09-FEAT-EXPORT - Экспорт в Markdown и PDF [✅]
- IP-01: Export functionality
- Завершено: 2025-08-26
- Документация: `current/09-FEAT-EXPORT/`

#### 10-REFACTOR-graph-manager - Рефакторинг GraphManager [✅]
- POST-IMPL-01: Artifact saving refactoring
- Завершено: 2025-08-28
- Документация: `current/10-REFACTOR-graph-manager/`

#### 11-FEAT-deep-linking - React Router Deep Linking Integration [✅]
- Deep linking functionality
- Завершено: 2025-08-29
- Документация: `current/11-FEAT-deep-linking/`

#### 12-FEAT-multi-tenancy - Multi-Tenancy Security Implementation [✅]
- IP-01: Phase 1 - Security infrastructure - Завершено: 2025-08-29
- IP-02: Phase 2 - Web UI authentication - Завершено: 2025-08-29
- Документация: `current/12-FEAT-multi-tenancy/`

#### 13-FEAT-web-ui-urls - Replace Local Paths with Web UI URLs [✅]
- IP-01: Web UI URLs implementation
- Завершено: 2025-08-31
- Документация: `current/13-FEAT-web-ui-urls/`

#### 14-FEAT-web-ui-export - Full Export Functionality for Web UI [✅]
- PS-01: Export functionality
- Завершено: 2025-09-01
- Документация: `current/14-FEAT-web-ui-export/`

### M2: AI-Enhanced Generation [🚀 В разработке: Декабрь 2025]
Улучшение ML-части системы для повышения качества генерации через планирование, внешние источники и декомпозицию

#### Document Structure Planning & Decomposed Generation [📋]
Система генерирует иерархическую структуру документа (разделы → пункты → подпункты) перед генерацией контента, с возможностью HITL-редактирования структуры и параллельной генерацией по разделам.

- Узел планирования генерирует иерархическую структуру документа на основе входного запроса и доступных источников
- HITL checkpoint для редактирования структуры: добавление/удаление разделов, изменение формулировок, перегруппировка пунктов
- Параллельная генерация каждого раздела независимо, используя утвержденную структуру
- Сборка разделов в финальный документ согласно иерархии

#### External Sources Integration [📋]
Интеграция внешних источников информации для обогащения генерируемых материалов.

- Интеграция web search провайдеров (Tavily, Perplexity) для поиска актуальной информации
- RAG-based поиск по Telegram: выгрузка и индексация основных LLM-тематических чатов в векторную БД (Qdrant/Chroma) как отдельный микросервис
- Proof of concept подход для Telegram RAG - базовая индексация и semantic search
- Модель генерирует материал из своих весов, внешние источники обрабатываются отдельно
- Унифицированный интерфейс для всех источников

#### Content Quality Enhancements [📋]
Улучшение качества финального документа через систему references и post-processing.

- Маппинг источников на разделы структуры: references на конспекты, сгенерированный материал, внешние источники
- Post-processing для дедупликации контента между разделами
- Создание плавных и консистентных переходов между разделами
- Финальная полировка документа

### M3: Production Platform [📋 Планируется: Март 2026]
Переход от локального инструмента к полноценному multi-tenant SaaS продукту

#### Testing & Quality [📋]
- Покрытие тестами
- CI/CD pipeline
- API documentation

#### Multi-tenancy & Auth [📋]
- Авторизация
- Изоляция данных
- Управление сессиями

#### Telegram Mini App [📋]
- Интеграция веб-интерфейса
- SSO через Telegram

#### Billing & Subscriptions [📋]
- Тарифные планы
- Лимиты
- Платежные системы

#### Production Infrastructure [📋]
- Cloud deployment
- Monitoring
- Backup

#### Flexible Multi-agent Architecture [📋]
- Вызов узлов из других узлов
- Навигация между узлами

### M4: Advanced Capabilities [📋 Планируется: Июнь 2026]
Расширение функционала для более сложных и разнообразных образовательных сценариев

#### Dynamic Prompt Generation [📋]
- LLM-based система для генерации промптов на основе контекста задачи

#### Batch Processing [📋]
- Обработка материалов целого семестра
- Декомпозиция на темы и вопросы

#### Multi-document Context [📋]
- Работа с множественными источниками одновременно

#### Advanced Analytics [📋]
- Аналитика эффективности обучения

## Детали инициатив M2

### Архитектурный подход M2
Milestone M2 фокусируется на улучшении ML-части системы через добавление интеллектуального слоя планирования между сбором информации и финальным синтезом. Ключевая идея - сохранить приоритет генерации из весов модели, при этом обогащая контент внешними источниками без ухудшения качества.

### Ожидаемые результаты M2:
- Улучшение полноты и структурированности материалов
- Сохранение качества генерации из весов модели при обогащении внешними источниками
- Возможность работы с большими документами без потери связности
- Уникальная возможность поиска по Telegram каналам для доступа к узкоспециализированной информации