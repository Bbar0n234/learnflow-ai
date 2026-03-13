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
| feat-002 | 📋 Planned | Shared infrastructure (API, state, components) |
| feat-003 | 📋 Planned | Sidebar + projects |
| feat-004 | 📋 Planned | Chat UI |
| feat-005 | 📋 Planned | SSE streaming |
| feat-006 | 📋 Planned | Sphere + artifacts |

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

**Статус:** 📋 Planned
**Blocked by:** frontend/feat-001
**Закрывает:** shared/api/, stores/, shared/components/ из frontend.md
**Ветка:** `feat/002-shared-infra`

#### Состав работ
- [ ] axios client (base URL из `VITE_API_URL`, header `X-User-Name`, error interceptor)
- [ ] `types.ts` — TypeScript-типы 1:1 с backend schemas (Project, Chat, Message, Sphere, Artifact)
- [ ] API-модули с хардкод-моками (projects.ts, chats.ts, sphere.ts, artifacts.ts) — каждая функция возвращает mock-данные, при подключении бэкенда моки заменяются на реальные вызовы
- [ ] Zustand ui-store (sidebarOpen, toggleSidebar)
- [ ] Zustand stream-store (isStreaming, streamingText, activeTool, streamingChatId + actions)
- [ ] MarkdownRenderer — обёртка над Streamdown для переиспользования в chat, sphere, artifacts
- [ ] Необходимые shadcn/ui примитивы (Dialog, Tabs, ScrollArea, Textarea и т.д.)

#### Критерии приёмки
- [ ] API-модули экспортируют все функции из frontend.md (getProjects, getProject, createProject и т.д.)
- [ ] Моки возвращают типизированные данные, соответствующие backend schemas
- [ ] Zustand stores работают: `useUIStore().toggleSidebar()` переключает state
- [ ] MarkdownRenderer рендерит Markdown-строку с подсветкой синтаксиса
- [ ] Типы покрывают все сущности: Project, Chat, Message, Sphere, Artifact, SSE events
- [ ] Линтер и TypeScript проходят без ошибок

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-003: Sidebar + Projects

**Цель:** реализовать sidebar-навигацию (список проектов, recent chats, кнопки создания) и ProjectLayout с табами. После итерации — полноценная навигация по приложению, создание проектов.

**Статус:** 📋 Planned
**Blocked by:** frontend/feat-002
**Закрывает:** features/projects/, Sidebar, ProjectLayout из frontend.md
**Ветка:** `feat/003-sidebar-projects`

#### Состав работ
- [ ] Sidebar (замена заглушки из feat-001): список проектов, секция recents, кнопка New Project, кнопка New Chat (активна только в контексте проекта — project_id из URL)
- [ ] ProjectList в sidebar (карточки проектов)
- [ ] CreateProjectModal (Dialog + input название + кнопка создания)
- [ ] ProjectLayout — обёртка project-level маршрутов: имя проекта, табы Chats / Sphere / Artifacts
- [ ] TanStack Query хуки: useProjects, useProject, useCreateProject, useUpdateProject, useDeleteProject, useRecentChats
- [ ] Интеграция sidebar toggle с Zustand ui-store

#### Критерии приёмки
- [ ] Sidebar отображает список проектов из mock-данных
- [ ] Клик по проекту в sidebar → навигация на `/projects/:id`
- [ ] CreateProjectModal открывается, создаёт проект (mock), проект появляется в sidebar
- [ ] ProjectLayout рендерит табы, переключение табов работает (Chats / Sphere / Artifacts)
- [ ] Recent chats отображаются в sidebar, клик → навигация в чат
- [ ] Sidebar складывается/разворачивается (toggle)

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-004: Chat UI

**Цель:** реализовать интерфейс чата — список сообщений, рендеринг (user vs assistant), input с отправкой. Работает на mock-данных, без реального стриминга. После итерации — можно открыть чат, увидеть историю, "отправить" сообщение.

**Статус:** 📋 Planned
**Blocked by:** frontend/feat-003
**Закрывает:** features/chat/ (UI-часть) из frontend.md
**Ветка:** `feat/004-chat-ui`

#### Состав работ
- [ ] ChatView — основной контейнер чата (на всю центральную область)
- [ ] MessageList — список сообщений со скроллом
- [ ] MessageItem — рендеринг сообщения (user: plain text, assistant: Markdown через MarkdownRenderer)
- [ ] ChatInput — textarea с отправкой (Enter / кнопка Send)
- [ ] Автоскролл к последнему сообщению
- [ ] TanStack Query хуки: useChats, useChat, useCreateChat
- [ ] Список чатов на табе Chats в ProjectLayout

#### Критерии приёмки
- [ ] Переход в чат (`/projects/:id/chats/:cid`) рендерит историю mock-сообщений
- [ ] User и assistant сообщения визуально различаются
- [ ] Assistant-сообщения рендерят Markdown (заголовки, код, списки)
- [ ] Input позволяет набрать текст и "отправить" (mock: сообщение добавляется в список)
- [ ] Автоскролл работает при появлении нового сообщения
- [ ] Создание нового чата из ProjectLayout работает (mock)

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-005: SSE Streaming

**Цель:** реализовать real-time стриминг ответов агента через SSE. Хук useAgentStream, парсинг всех 6 event types, интеграция со stream-store, инкрементальный рендеринг, tool-индикаторы, cancel. Самая технически сложная итерация фронтенда.

**Статус:** 📋 Planned
**Blocked by:** frontend/feat-004
**Закрывает:** SSE-стриминг из frontend.md, stream-store интеграция
**Ветка:** `feat/005-sse-streaming`

#### Состав работ
- [ ] useAgentStream — кастомный хук: native fetch + ReadableStream, парсинг SSE-событий
- [ ] Обработка всех event types: `text_chunk`, `tool_start`, `tool_end`, `artifact_created`, `done`, `error`
- [ ] Интеграция со stream-store (appendText, setTool, endStream на каждое событие)
- [ ] Инкрементальный рендеринг текста в ChatView (streamingText из store → MarkdownRenderer)
- [ ] ToolIndicator — компонент индикации вызова tool (название tool, спиннер)
- [ ] ArtifactCard inline в чате (по событию `artifact_created`)
- [ ] Кнопка Cancel (POST /cancel через axios, закрытие стрима)
- [ ] Инвалидация TanStack Query: chat query + recents на `done`, artifacts на `artifact_created`
- [ ] Замена mock-отправки сообщений из feat-004 на реальный SSE-поток (или mock SSE для автономной работы)

#### Критерии приёмки
- [ ] Отправка сообщения инициирует SSE-соединение (или mock SSE stream)
- [ ] Текст появляется инкрементально (чанк за чанком), не целиком
- [ ] При `tool_start` отображается индикатор, при `tool_end` — скрывается
- [ ] При `artifact_created` в чате появляется карточка артефакта
- [ ] Cancel прерывает стрим, UI возвращается в idle-состояние
- [ ] После `done` — chat query инвалидируется, полное сообщение загружается с сервера
- [ ] Ошибки SSE (`error` event) отображаются пользователю

#### Артефакты
<!-- Заполняется по мере работы -->

---

### feat-006: Sphere + Artifacts

**Цель:** реализовать Knowledge Sphere (просмотр и редактирование) и Artifacts (список, просмотр, скачивание). После итерации — все feature-модули из frontend.md реализованы.

**Статус:** 📋 Planned
**Blocked by:** frontend/feat-002
**Закрывает:** features/sphere/, features/artifacts/ из frontend.md
**Ветка:** `feat/006-sphere-artifacts`

#### Состав работ
- [ ] SphereViewer — отображение Knowledge Sphere (Markdown render через MarkdownRenderer)
- [ ] SphereEditor — редактирование (textarea / Markdown editor, кнопка Save → PUT)
- [ ] Переключение Viewer ↔ Editor
- [ ] TanStack Query хуки: useSphere, useUpdateSphere
- [ ] ArtifactList — список артефактов проекта (название, тип, дата)
- [ ] ArtifactView — просмотр артефакта (Markdown render + кнопки скачивания md/pdf)
- [ ] Download-функциональность (window.open / `<a href>` на endpoint download)
- [ ] TanStack Query хуки: useArtifacts, useArtifact

#### Критерии приёмки
- [ ] Таб Sphere в ProjectLayout рендерит Knowledge Sphere из mock-данных
- [ ] Переключение Viewer → Editor → Save → Viewer работает
- [ ] Таб Artifacts показывает список артефактов из mock-данных
- [ ] Клик по артефакту → переход на `/projects/:id/artifacts/:aid`, контент рендерится
- [ ] Кнопки скачивания (md/pdf) формируют корректный URL на download endpoint
- [ ] Все хуки типизированы, линтер и TypeScript проходят

#### Артефакты
<!-- Заполняется по мере работы -->
