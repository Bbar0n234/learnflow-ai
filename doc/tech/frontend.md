# Frontend

Архитектура верхнего уровня и стек — в [vision.md](../vision.md). Здесь — детальное описание фронтенда: экраны и навигация, компоненты, state management, API-интеграция, SSE-стриминг.

## Экраны и навигация

### Навигационная модель

Chat-first SPA с постоянным sidebar. Паттерн навигации: **Sidebar → Project → Chats/Sphere/Artifacts → Chat**. Референсы: ChatGPT Projects, Claude.ai Projects — знакомый пользователям паттерн.

### Layout

```
┌──────────┐ ┌────────────────────────────────────────────┐
│ Sidebar  │ │                                            │
│ (const)  │ │  Центральная область                       │
│          │ │  (меняется в зависимости от маршрута)       │
│          │ │                                            │
│          │ │                                            │
│          │ │                                            │
└──────────┘ └────────────────────────────────────────────┘
```

**Sidebar (постоянный):**
- New chat (активна только в контексте проекта — project_id из URL) / New project
- Список проектов пользователя
- Recents — недавние чаты (быстрое переключение между чатами разных проектов)

**Центральная область** — контент текущего маршрута.

### Маршруты

| Маршрут | Центральная область |
|---------|---------------------|
| `/` | Welcome (без input — создание чата только из проекта) |
| `/projects/:id` | Проект: табы **Chats** / **Sphere** / **Artifacts**, input для нового чата |
| `/projects/:id/chats/:cid` | Чат: сообщения + SSE-стриминг + input |
| `/projects/:id/sphere` | Knowledge Sphere: просмотр и редактирование (Markdown) |
| `/projects/:id/artifacts` | Список артефактов проекта |
| `/projects/:id/artifacts/:aid` | Просмотр артефакта + скачивание (md/pdf) |

### Экраны

**Главная (`/`):** welcome-экран без input. Создание чата — только из контекста проекта (`/projects/:id`). Проекты доступны через sidebar.

**Проект (`/projects/:id`):** имя проекта, input для нового чата в этом проекте, табы:
- **Chats** (default) — список чатов проекта (название, превью, дата)
- **Sphere** — Knowledge Sphere
- **Artifacts** — артефакты проекта

Табы Sphere и Artifacts — те же экраны, что и по прямым маршрутам, но встроены в контекст проекта через табы.

**Чат (`/projects/:id/chats/:cid`):** полноценный chat view на всю центральную область. Sidebar остаётся для навигации назад.

**Создание проекта:** модалка поверх текущего экрана. Один input (название) + кнопка создания. При необходимости расширяется дополнительными полями.

## Компонентная архитектура

Feature-based: компоненты группируются по фичам, не по типам. Новая фича = новая папка, существующие не затрагиваются.

### Layout

- **AppLayout** — корневой layout: sidebar + центральная область. Рендерится на всех маршрутах.
- **Sidebar** — проекты пользователя, recents, кнопки создания (new chat / new project).
- **ProjectLayout** — обёртка для project-level маршрутов: имя проекта, табы (Chats / Sphere / Artifacts).

### Features

**projects** — CRUD проектов.
- Список проектов (элементы sidebar)
- Модалка создания проекта
- Карточка проекта в sidebar

**chat** — ядро приложения.
- Список сообщений (scroll, auto-scroll при стриминге)
- Сообщение — user и assistant рендерятся по-разному (assistant → Markdown через Streamdown)
- Input с отправкой (Enter / кнопка)
- Индикаторы: стриминг текста, tool use (`tool_start`/`tool_end`)
- Карточка артефакта (инлайн в чате, по событию `artifact_created`)
- Кнопка cancel

**sphere** — Knowledge Sphere.
- Viewer (Markdown render через Streamdown)
- Editor (textarea / Markdown editor, PUT при сохранении)

**artifacts** — артефакты проекта.
- Список артефактов (название, тип, дата)
- Просмотр артефакта (Markdown render + кнопки скачивания md/pdf)

### Shared

- **ui/** — shadcn/ui примитивы (Button, Input, Dialog, Tabs, ScrollArea и т.д.)
- **MarkdownRenderer** — обёртка над Streamdown. Переиспользуется в chat (ответы агента), sphere (просмотр), artifacts (просмотр)

## State Management

Серверные данные не дублируются в клиентский store. Активный таб, текущий проект/чат — derived from URL (React Router `useParams`), store не нужен.

### TanStack Query — серверный state

Кеширование, рефетч, loading/error — автоматически. Query keys иерархические, для точечной инвалидации.

**Queries:**

| Query Key | Endpoint |
|-----------|----------|
| `["projects"]` | `GET /projects` |
| `["projects", id]` | `GET /projects/:id` |
| `["projects", id, "chats"]` | `GET /projects/:id/chats` |
| `["projects", id, "chats", cid]` | `GET /projects/:id/chats/:cid` |
| `["projects", id, "sphere"]` | `GET /projects/:id/sphere` |
| `["projects", id, "artifacts"]` | `GET /projects/:id/artifacts` |
| `["projects", id, "artifacts", aid]` | `GET /projects/:id/artifacts/:aid` |
| `["chats", "recent"]` | `GET /chats/recent` |

**Mutations → инвалидация:**

| Действие | Инвалидирует |
|----------|-------------|
| Создать/обновить/удалить проект | `["projects"]` |
| Создать чат | `["projects", id, "chats"]`, `["chats", "recent"]` |
| Обновить sphere | `["projects", id, "sphere"]` |
| Стрим завершён (`done`) | `["projects", id, "chats", cid]`, `["chats", "recent"]` |
| Событие `artifact_created` | `["projects", id, "artifacts"]` |

### Zustand — клиентский state

Два store с разным lifecycle.

**UI Store** — живёт всю сессию:

```
uiStore
├── sidebarOpen: boolean
└── toggleSidebar()
```

**Stream Store** — эфемерный, существует только во время SSE-стрима:

```
streamStore
├── isStreaming: boolean
├── streamingText: string
├── activeTool: string | null
├── streamingChatId: string | null
├── startStream(chatId)
├── appendText(chunk)
├── setTool(name | null)
└── endStream()
```

После `endStream()` — сброс в initial state. Полное сообщение приходит с сервера через инвалидацию chat query.

## API-интеграция

Два транспорта: **axios** для REST (14 endpoints), **fetch** для SSE-стриминга (1 endpoint). SSE требует чтения `ReadableStream` по мере поступления — axios спроектирован под "запрос → полный ответ" и для этого не подходит.

### HTTP-клиент

Единый axios instance: base URL из `VITE_API_URL`, default header `X-User-Name` (MVP auth), response interceptor для обработки ошибок.

### TypeScript типы

Ручные, 1:1 со schemas из [backend.md](backend.md). Единый файл `types.ts`. Генерация из OpenAPI — при росте API.

### API-модули

По модулю на ресурс, по функции на endpoint:

```
shared/api/
├── client.ts       — axios instance
├── types.ts        — TS-типы
├── projects.ts     — getProjects, getProject, createProject, updateProject, deleteProject
├── chats.ts        — getChats, getChat, createChat, getRecentChats
├── sphere.ts       — getSphere, updateSphere
└── artifacts.ts    — getArtifacts, getArtifact, downloadArtifact
```

Без `messages.ts` — отправка сообщений через SSE (см. ниже).

### TanStack Query хуки

По хуку на query/mutation, живут в features:

```
features/projects/   → useProjects, useProject, useCreateProject, useUpdateProject, useDeleteProject
features/chat/       → useChats, useChat, useCreateChat, useRecentChats
features/sphere/     → useSphere, useUpdateSphere
features/artifacts/  → useArtifacts, useArtifact
```

Компоненты вызывают хуки, не API-функции напрямую.

**downloadArtifact** — прямой download (`window.open` / `<a href>`), не через axios и не через TanStack Query.

## SSE-стриминг

Кастомный хук `useAgentStream` поверх native `fetch`. Формат событий — в [backend.md](backend.md) (SSE Streaming Protocol).

### Lifecycle

```
1. Пользователь нажал Send
2. fetch POST /projects/:id/chats/:cid/messages
3. Сервер: 200 OK, Content-Type: text/event-stream
4. Клиент читает ReadableStream, парсит SSE-события:

   text_chunk       → streamStore.appendText(chunk)
   tool_start       → streamStore.setTool(name)
   tool_end         → streamStore.setTool(null)
   artifact_created → invalidate ["projects", id, "artifacts"]
   done             → streamStore.endStream(), invalidate chat query + recents
   error            → показать ошибку, закрыть стрим

5. Cancel: POST /cancel (axios) → сервер шлёт error event → стрим закрыт
```

### Связь с state

- **Zustand stream store** — обновляется на каждое событие (appendText, setTool, endStream)
- **TanStack Query** — инвалидация после `done` и `artifact_created` (таблица в секции State Management)

## Стек и инструменты

Обоснование выбора, альтернативы и риски — в [ADR-008](adr/ADR-008-frontend-stack.md).

| Категория | Технология |
|-----------|-----------|
| Сборка | Vite |
| Язык | TypeScript (strict mode) |
| UI-компоненты | shadcn/ui |
| Стилизация | Tailwind CSS v4 |
| HTTP-клиент (REST) | axios |
| HTTP-клиент (SSE) | native fetch |
| Серверный state | TanStack Query v5 |
| UI state | Zustand v5 |
| Роутинг | React Router v7 (library mode) |
| Markdown/стриминг | Streamdown |
| Иконки | Lucide React |
| Линтер | ESLint |
| Форматер | Prettier |

## Module Structure

```
frontend/
├── index.html
├── vite.config.ts
├── tsconfig.json
├── tailwind.css
├── components.json                — shadcn/ui конфиг
│
├── src/
│   ├── main.tsx                   — entry point: React root, providers
│   ├── App.tsx                    — роутер, маршруты
│   │
│   ├── app/                       — application shell
│   │   ├── layouts/
│   │   │   ├── AppLayout.tsx      — sidebar + центральная область
│   │   │   └── ProjectLayout.tsx  — имя проекта, табы (Chats/Sphere/Artifacts)
│   │   ├── providers/             — QueryClientProvider, прочие провайдеры
│   │   └── router.tsx             — конфигурация маршрутов
│   │
│   ├── features/                  — feature-based модули
│   │   ├── projects/
│   │   │   ├── components/        — ProjectCard, CreateProjectModal, ProjectList
│   │   │   └── hooks/             — useProjects, useProject, useCreateProject, useUpdateProject, useDeleteProject
│   │   ├── chat/
│   │   │   ├── components/        — ChatView, MessageList, MessageItem, ChatInput, ToolIndicator, ArtifactCard
│   │   │   └── hooks/             — useChats, useChat, useCreateChat, useRecentChats, useAgentStream
│   │   ├── sphere/
│   │   │   ├── components/        — SphereViewer, SphereEditor
│   │   │   └── hooks/             — useSphere, useUpdateSphere
│   │   └── artifacts/
│   │       ├── components/        — ArtifactList, ArtifactView
│   │       └── hooks/             — useArtifacts, useArtifact
│   │
│   ├── shared/
│   │   ├── api/                   — HTTP-слой
│   │   │   ├── client.ts          — axios instance
│   │   │   ├── types.ts           — TS-типы (1:1 с backend schemas)
│   │   │   ├── projects.ts
│   │   │   ├── chats.ts
│   │   │   ├── sphere.ts
│   │   │   └── artifacts.ts
│   │   ├── ui/                    — shadcn/ui компоненты
│   │   └── components/            — MarkdownRenderer и другие shared-компоненты
│   │
│   └── stores/                    — Zustand stores
│       ├── ui-store.ts
│       └── stream-store.ts
```

**Принципы:** features/ изолированы друг от друга. shared/ — то, что нужно нескольким фичам. app/ — shell (layouts, providers, router), не бизнес-логика. stores/ отдельно от features, т.к. stream store используется cross-feature. Pages не выделены — при 6 маршрутах роутер рендерит layout + feature-компонент напрямую.
