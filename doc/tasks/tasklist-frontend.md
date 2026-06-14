# Tasklist: Frontend

## Контекст

React SPA — chat-first интерфейс с sidebar-навигацией. Feature-based архитектура. Разрабатывается параллельно с Backend Core на хардкод-моках в API-модулях.

**Документы:** [frontend.md](../tech/frontend.md) (экраны, компоненты, state, SSE), [ADR-008](../tech/adr/ADR-008-frontend-stack.md), [backend.md](../tech/backend.md) (API-контракт)

**Зависимости:** Infrastructure Setup

## Легенда

- 📋 Planned
- 🚧 In Progress
- ✅ Done
- ⏸️ Paused
- ❌ Cancelled

## Overview

| Итерация | Статус | Закрывает |
|----------|--------|-----------|
| feat-001 | ✅ Done | Scaffold + app shell |
| feat-002 | ✅ Done | Shared infrastructure (API, state, components) |
| feat-003 | ✅ Done | Sidebar + projects |
| feat-004 | ✅ Done | Chat UI |
| feat-005 | ✅ Done | SSE streaming |
| feat-006 | ✅ Done | Sphere + artifacts |
| feat-007 | ✅ Done | Design-branding: визуальная идентичность, иллюстрации, dark-адаптация, прозрачные cutout |

## Быстро меняющиеся инструменты

| Инструмент | Источник |
|-----------|----------|
| Vite | firecrawl → vite.dev/guide |
| Tailwind CSS v4 | firecrawl → tailwindcss.com/docs |
| shadcn/ui | firecrawl → ui.shadcn.com/docs |
| TanStack Query v5 | firecrawl → tanstack.com/query |
| Zustand v5 | firecrawl → docs.pmnd.rs/zustand |
| React Router v7 | firecrawl → reactrouter.com |
| Streamdown | firecrawl → github.com/nichochar/streamdown |
| ESLint | MCP `@eslint/mcp` |

## Итерации

### feat-001: Scaffold + App Shell

**Цель:** поднять React-приложение на полном стеке (Vite + TS + Tailwind v4 + shadcn/ui), настроить роутинг и layout-каркас. После итерации — запускаемое приложение с навигацией между stub-страницами.

**Статус:** ✅ Done
**Blocked by:** infra/chore-001
**Закрывает:** фундамент фронтенда, module structure из frontend.md
**Ветка:** `feat/001-scaffold-app-shell`

#### Состав работ
- [x] Vite + React + TypeScript setup (поверх package.json из infra)
- [x] Tailwind CSS v4 + базовая конфигурация
- [x] shadcn/ui инициализация (components.json, первые примитивы: Button, Input)
- [x] AppLayout (sidebar-заглушка + центральная область)
- [x] React Router v7 — все 6 маршрутов (stub-компоненты)
- [x] QueryClientProvider + прочие providers (app/providers/)
- [x] Welcome page (без input — создание чата только из проекта; welcome-текст / placeholder)

#### Критерии приёмки
- [x] `make dev-fe` запускает dev-сервер, приложение открывается в браузере
- [x] Навигация между всеми 6 маршрутами работает (URL меняется, stub рендерится)
- [x] Tailwind-классы применяются, shadcn/ui Button рендерится корректно
- [x] `make lint-fe` и `make format-fe` проходят без ошибок
- [x] TypeScript strict mode, ошибок компиляции нет

#### Артефакты
- [Plan](iterations/frontend/feat-001-scaffold-app-shell/plan.md)
- [Summary](iterations/frontend/feat-001-scaffold-app-shell/summary.md)

---

### feat-002: Shared Infrastructure

**Цель:** подготовить переиспользуемые модули: HTTP-клиент, TypeScript-типы, API-функции с хардкод-моками, Zustand stores, MarkdownRenderer. После итерации — фичи могут строиться поверх готового shared-слоя.

**Статус:** ✅ Done
**Blocked by:** frontend/feat-001
**Закрывает:** shared/api/, stores/, shared/components/ из frontend.md
**Ветка:** `feat/002-shared-infra`

#### Состав работ
- [x] axios client (base URL из `VITE_API_URL`, header `X-User-Name`, error interceptor)
- [x] `types.ts` — TypeScript-типы 1:1 с backend schemas (Project, Chat, Message, Sphere, Artifact)
- [x] API-модули с хардкод-моками (projects.ts, chats.ts, sphere.ts, artifacts.ts) — каждая функция возвращает mock-данные, при подключении бэкенда моки заменяются на реальные вызовы
- [x] Zustand ui-store (sidebarOpen, toggleSidebar)
- [x] Zustand stream-store (isStreaming, streamingText, activeTool, streamingChatId + actions)
- [x] MarkdownRenderer — обёртка над Streamdown для переиспользования в chat, sphere, artifacts
- [x] Необходимые shadcn/ui примитивы (Dialog, Tabs, ScrollArea, Textarea и т.д.)

#### Критерии приёмки
- [x] API-модули экспортируют все функции из frontend.md (getProjects, getProject, createProject и т.д.)
- [x] Моки возвращают типизированные данные, соответствующие backend schemas
- [x] Zustand stores работают: `useUIStore().toggleSidebar()` переключает state
- [x] MarkdownRenderer рендерит Markdown-строку с подсветкой синтаксиса
- [x] Типы покрывают все сущности: Project, Chat, Message, Sphere, Artifact, SSE events
- [x] Линтер и TypeScript проходят без ошибок

#### Артефакты
- [Plan](iterations/frontend/feat-002-shared-infra/plan.md)
- [Summary](iterations/frontend/feat-002-shared-infra/summary.md)

---

### feat-003: Sidebar + Projects

**Цель:** реализовать sidebar-навигацию (список проектов, recent chats, кнопки создания) и ProjectLayout с табами. После итерации — полноценная навигация по приложению, создание проектов.

**Статус:** ✅ Done
**Blocked by:** frontend/feat-002
**Закрывает:** features/projects/, Sidebar, ProjectLayout из frontend.md
**Ветка:** `feat/003-sidebar-projects`

#### Состав работ
- [x] Sidebar (замена заглушки из feat-001): список проектов, секция recents, кнопка New Project, кнопка New Chat (активна только в контексте проекта — project_id из URL)
- [x] ProjectList в sidebar (карточки проектов)
- [x] CreateProjectModal (Dialog + input название + кнопка создания)
- [x] ProjectLayout — обёртка project-level маршрутов: имя проекта, табы Chats / Sphere / Artifacts
- [x] TanStack Query хуки: useProjects, useProject, useCreateProject, useUpdateProject, useDeleteProject, useRecentChats
- [x] Интеграция sidebar toggle с Zustand ui-store

#### Критерии приёмки
- [x] Sidebar отображает список проектов из mock-данных
- [x] Клик по проекту в sidebar → навигация на `/projects/:id`
- [x] CreateProjectModal открывается, создаёт проект (mock), проект появляется в sidebar
- [x] ProjectLayout рендерит табы, переключение табов работает (Chats / Sphere / Artifacts)
- [x] Recent chats отображаются в sidebar, клик → навигация в чат
- [x] Sidebar складывается/разворачивается (toggle)

#### Артефакты
- [Plan](iterations/frontend/feat-003-sidebar-projects/plan.md)
- [Summary](iterations/frontend/feat-003-sidebar-projects/summary.md)

---

### feat-004: Chat UI

**Цель:** реализовать интерфейс чата — список сообщений, рендеринг (user vs assistant), input с отправкой. Работает на mock-данных, без реального стриминга. После итерации — можно открыть чат, увидеть историю, "отправить" сообщение.

**Статус:** ✅ Done
**Blocked by:** frontend/feat-003
**Закрывает:** features/chat/ (UI-часть) из frontend.md
**Ветка:** `feat/004-chat-ui`

#### Состав работ
- [x] ChatView — основной контейнер чата (на всю центральную область)
- [x] MessageList — список сообщений со скроллом
- [x] MessageItem — рендеринг сообщения (user: plain text, assistant: Markdown через MarkdownRenderer)
- [x] ChatInput — textarea с отправкой (Enter / кнопка Send)
- [x] Автоскролл к последнему сообщению
- [x] TanStack Query хуки: useChats, useChat, useCreateChat
- [x] Список чатов на табе Chats в ProjectLayout

#### Критерии приёмки
- [x] Переход в чат (`/projects/:id/chats/:cid`) рендерит историю mock-сообщений
- [x] User и assistant сообщения визуально различаются
- [x] Assistant-сообщения рендерят Markdown (заголовки, код, списки)
- [x] Input позволяет набрать текст и "отправить" (mock: сообщение добавляется в список)
- [x] Автоскролл работает при появлении нового сообщения
- [x] Создание нового чата из ProjectLayout работает (mock)

#### Артефакты
- [Plan](iterations/frontend/feat-004-chat-ui/plan.md)
- [Summary](iterations/frontend/feat-004-chat-ui/summary.md)

---

### feat-005: SSE Streaming

**Цель:** реализовать real-time стриминг ответов агента через SSE. Хук useAgentStream, парсинг всех 6 event types, интеграция со stream-store, инкрементальный рендеринг, tool-индикаторы, cancel. Самая технически сложная итерация фронтенда.

**Статус:** ✅ Done
**Blocked by:** frontend/feat-004
**Закрывает:** SSE-стриминг из frontend.md, stream-store интеграция
**Ветка:** `feat/005-sse-streaming`

#### Состав работ
- [x] useAgentStream — кастомный хук: native fetch + ReadableStream, парсинг SSE-событий
- [x] Обработка всех event types: `text_chunk`, `tool_start`, `tool_end`, `artifact_created`, `done`, `error`
- [x] Интеграция со stream-store (appendText, setTool, endStream на каждое событие)
- [x] Инкрементальный рендеринг текста в ChatView (streamingText из store → MarkdownRenderer)
- [x] ToolIndicator — компонент индикации вызова tool (название tool, спиннер)
- [x] ArtifactCard inline в чате (по событию `artifact_created`)
- [x] Кнопка Cancel (POST /cancel через axios, закрытие стрима)
- [x] Инвалидация TanStack Query: chat query + recents на `done`, artifacts на `artifact_created`
- [x] Замена mock-отправки сообщений из feat-004 на реальный SSE-поток (или mock SSE для автономной работы)

#### Критерии приёмки
- [x] Отправка сообщения инициирует SSE-соединение (или mock SSE stream)
- [x] Текст появляется инкрементально (чанк за чанком), не целиком
- [x] При `tool_start` отображается индикатор, при `tool_end` — скрывается
- [x] При `artifact_created` в чате появляется карточка артефакта
- [x] Cancel прерывает стрим, UI возвращается в idle-состояние
- [x] После `done` — chat query инвалидируется, полное сообщение загружается с сервера
- [x] Ошибки SSE (`error` event) отображаются пользователю

#### Артефакты
- [Plan](iterations/frontend/feat-005-sse-streaming/plan.md)
- [Summary](iterations/frontend/feat-005-sse-streaming/summary.md)

---

### feat-006: Sphere + Artifacts

**Цель:** реализовать Knowledge Sphere (просмотр и редактирование) и Artifacts (список, просмотр, скачивание). После итерации — все feature-модули из frontend.md реализованы.

**Статус:** ✅ Done
**Blocked by:** frontend/feat-002
**Закрывает:** features/sphere/, features/artifacts/ из frontend.md
**Ветка:** `feat/006-sphere-artifacts`

#### Состав работ
- [x] SphereViewer — отображение Knowledge Sphere (Markdown render через MarkdownRenderer)
- [x] SphereEditor — редактирование (textarea / Markdown editor, кнопка Save → PUT)
- [x] Переключение Viewer ↔ Editor
- [x] TanStack Query хуки: useSphere, useUpdateSphere
- [x] ArtifactList — список артефактов проекта (название, тип, дата)
- [x] ArtifactView — просмотр артефакта (Markdown render + кнопки скачивания md/pdf)
- [x] Download-функциональность (window.open / `<a href>` на endpoint download)
- [x] TanStack Query хуки: useArtifacts, useArtifact

#### Критерии приёмки
- [x] Таб Sphere в ProjectLayout рендерит Knowledge Sphere из mock-данных
- [x] Переключение Viewer → Editor → Save → Viewer работает
- [x] Таб Artifacts показывает список артефактов из mock-данных
- [x] Клик по артефакту → переход на `/projects/:id/artifacts/:aid`, контент рендерится
- [x] Кнопки скачивания (md/pdf) формируют корректный URL на download endpoint
- [x] Все хуки типизированы, линтер и TypeScript проходят

#### Артефакты
- [Plan](iterations/frontend/feat-006-sphere-artifacts/plan.md)
- [Summary](iterations/frontend/feat-006-sphere-artifacts/summary.md)

---

### feat-007: Design-branding

**Цель:** проработать визуальную идентичность продукта и подготовить брендовые ассеты для UI: дизайн-токены и хэндофф, серию брендовых иллюстраций для ключевых экранов (light + dark), а также воспроизводимый pipeline получения прозрачных cutout. Итерация подготовительная — генерация и обработка ассетов, без интеграции в код фронтенда (это отдельная будущая итерация).

**Статус:** ✅ Done
**Закрывает:** визуальную идентичность и брендовые ассеты для экранов из frontend.md
**Ветка:** `feat/feat-007-design-branding`

#### Из backlog
- **P2** Design system — проработка дизайн-системы, визуальной идентичности, референсов.

#### Состав работ
- [x] Бренд-бриф и исследование референсов (`reference-brand-brief.md`, `reference-research-notes.md`)
- [x] Design-хэндофф: токены light/dark, wordmark, экраны (`design-handoff/`)
- [x] Паспорт стиля иллюстраций + базовый промпт-блок (`illustration-style-guide.md`)
- [x] Manifest и промпты для воспроизводимой генерации (`illustration-generation-manifest.md`, `illustration-prompts.md`)
- [x] Финальный пак иллюстраций: 6 сцен light + 6 dark (`refs/illustrations/final/`)
- [x] Генеративная адаптация к тёмной теме, режим B (`dark-theme-adaptation.md`)
- [x] Исследование удаления фона: детерминированные методы, локальный ML, managed-сервисы (`transparent-png-research.md`, `background-removal-services-research.md`)
- [x] Прозрачные cutout: локальные кандидаты soft-* + примеры победившего managed-подхода (`refs/illustrations/candidates/`, `refs/illustrations/managed-service-examples/`)
- [x] Research векторизации в SVG как следующий шаг (`svg-vectorization-research.md`)
- [x] Прореживание экспериментов, упаковка итерации, очистка

#### Критерии приёмки
- [x] Утверждён единый визуальный язык серии и эталон ключевого персонажа
- [x] Получены 6 финальных light- и 6 dark-сцен под экраны (welcome, empty-состояния, error)
- [x] Подтверждён воспроизводимый способ генерации новых сцен (manifest + промпты)
- [x] Выбран и проверен на реальных картинках подход к прозрачным cutout (managed BiRefNet General-HR), зафиксирован локальный fallback
- [x] Все артефакты упакованы как самодостаточная итерация, ссылки в доках валидны

#### Вне scope (будущие итерации)
- Интеграция токенов и cutout в код фронтенда
- SVG-векторизация финального пака (запускается после утверждения прозрачного PNG)
- Отдельные character sheets для человеческих персонажей

#### Артефакты
- [Style guide](iterations/frontend/feat-007-design-branding/illustration-style-guide.md)
- [Dark theme adaptation](iterations/frontend/feat-007-design-branding/dark-theme-adaptation.md)
- [Transparent PNG research](iterations/frontend/feat-007-design-branding/transparent-png-research.md)
- [Background removal services research](iterations/frontend/feat-007-design-branding/background-removal-services-research.md)
- [Summary](iterations/frontend/feat-007-design-branding/summary.md)
