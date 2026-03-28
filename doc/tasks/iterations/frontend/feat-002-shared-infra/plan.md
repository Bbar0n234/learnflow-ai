# Implementation Plan: feat-002 — Shared Infrastructure

## Контекст

Итерация feat-001 (Scaffold + App Shell) завершена: запущено React-приложение с роутингом и stub-страницами. Следующий шаг — подготовить переиспользуемый shared-слой (HTTP-клиент, типы, API-модули с моками, stores, MarkdownRenderer), на котором будут строиться feature-итерации feat-003..feat-006.

## Референсы

- Рабочий процесс: `doc/workflow.md`
- Соглашения: `doc/tech/conventions.md`
- Таск-лист: `doc/tasks/tasklist-frontend.md` (feat-002)
- Архитектура фронтенда: `doc/tech/frontend.md`
- Контракт API: `doc/tech/backend.md` (Schemas, Endpoints, SSE Protocol)
- ADR-008: `doc/tech/adr/ADR-008-frontend-stack.md`
- Саммари feat-001: `doc/tasks/iterations/frontend/feat-001-scaffold-app-shell/summary.md`

## Проверенные версии и синтаксис (firecrawl)

| Инструмент | Версия | Ключевые паттерны |
|-----------|--------|-------------------|
| **Zustand** | v5 | `create<T>()((set) => ({...}))` — curried form для TypeScript |
| **TanStack Query** | v5.90.0 | `useQuery({ queryKey, queryFn })`, `useMutation({ mutationFn, onSuccess })` |
| **Streamdown** | v2.4.0 | `<Streamdown plugins={{ code }}>{md}</Streamdown>`, `@source` в CSS |
| **@streamdown/code** | latest | Shiki syntax highlighting, `@source` для Tailwind v4 |
| **@streamdown/math** | latest | KaTeX rendering, требует `katex` + `import 'katex/dist/katex.min.css'` |
| **@streamdown/mermaid** | latest | Mermaid diagrams, `@source` для Tailwind v4 |
| **shadcn/ui** | v4 (base-nova) | `npx shadcn@latest add <component>`, компоненты в `src/shared/ui/` |
| **axios** | latest | `axios.create({ baseURL, headers })`, interceptors |

## Шаги реализации

### Шаг 0: Git setup

```bash
git fetch origin && git checkout -b feat/002-shared-infra origin/develop
```

### Шаг 1: Установка зависимостей

**npm пакеты:**
```bash
cd frontend
npm install axios zustand streamdown @streamdown/code @streamdown/math @streamdown/mermaid katex
```

**shadcn/ui компоненты:**
```bash
npx shadcn@latest add dialog tabs scroll-area textarea
```

Компоненты установятся в `src/shared/ui/` согласно `components.json` (aliases: `ui → @/shared/ui`).

### Шаг 2: Конфигурация Tailwind для Streamdown

Добавить `@source` директивы в `src/index.css` (после существующих `@import`):

```css
@source "../node_modules/streamdown/dist/*.js";
@source "../node_modules/@streamdown/code/dist/*.js";
@source "../node_modules/@streamdown/math/dist/*.js";
@source "../node_modules/@streamdown/mermaid/dist/*.js";
```

Добавить импорты стилей в `src/main.tsx`:

```ts
import "streamdown/styles.css";
import "katex/dist/katex.min.css";
```

### Шаг 3: TypeScript типы — `src/shared/api/types.ts`

Типы 1:1 с backend schemas из `doc/tech/backend.md`:

```ts
// === Entities (GET list/detail, PUT responses) ===

interface Project {
  id: string           // UUID
  name: string
  created_at: string   // ISO datetime
  updated_at: string
}

interface Chat {
  thread_id: string    // UUID
  title: string
  created_at: string
  updated_at: string
}

interface ChatDetail {
  thread_id: string
  title: string
  messages: Message[]
}

interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  created_at: string
}

interface RecentChat {
  thread_id: string
  title: string
  project_id: string
  project_name: string
  updated_at: string
}

interface Sphere {
  project_id: string
  content: string
  updated_at: string
}

interface Artifact {
  id: string
  title: string
  type: string          // "markdown" | ...
  created_at: string
}

interface ArtifactDetail {
  id: string
  title: string
  type: string
  content: string
  thread_id: string
  created_at: string
}

// === Create responses (POST — без updated_at, 1:1 с backend schemas) ===

interface ProjectCreateResponse {
  id: string
  name: string
  created_at: string
}

interface ChatCreateResponse {
  thread_id: string
  title: string
  created_at: string
}

// === Requests ===

interface CreateProjectRequest { name: string }
interface UpdateProjectRequest { name: string }
interface CreateChatRequest { title?: string }
interface UpdateSphereRequest { content: string }
interface SendMessageRequest { content: string }

// === Responses (list wrappers) ===

interface ListResponse<T> { items: T[] }

// === SSE Events ===

type SSEEvent =
  | { type: "text_chunk"; content: string }
  | { type: "tool_start"; tool: string; call_id: string }
  | { type: "tool_end"; tool: string; call_id: string }
  | { type: "artifact_created"; id: string; title: string; artifact_type: string }
  | { type: "done"; message_id?: string }
  | { type: "error"; detail: string }
```

> **Примечание:** `ProjectCreateResponse` и `ChatCreateResponse` — отдельные типы для POST-ответов, у которых нет `updated_at` (в отличие от GET/PUT). Это обеспечивает точное 1:1 соответствие с backend schemas из `doc/tech/backend.md`.

### Шаг 4: HTTP-клиент — `src/shared/api/client.ts`

```ts
import axios from "axios"

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "http://localhost:8000",
  headers: {
    "X-User-Name": import.meta.env.VITE_USER_NAME ?? "default",
  },
})

// Error interceptor: логирование, прокидывание ошибки дальше
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    console.error("[API Error]", error.response?.status, error.response?.data)
    return Promise.reject(error)
  },
)
```

### Шаг 5: API-модули с хардкод-моками

Каждый модуль экспортирует функции, возвращающие mock-данные. Сигнатура функций совпадает с будущими реальными вызовами (замена — только тело функции).

**`src/shared/api/projects.ts`** — `getProjects`, `getProject`, `createProject`, `updateProject`, `deleteProject`

**`src/shared/api/chats.ts`** — `getChats`, `getChat`, `createChat`, `getRecentChats`

**`src/shared/api/sphere.ts`** — `getSphere`, `updateSphere`

**`src/shared/api/artifacts.ts`** — `getArtifacts`, `getArtifact`, `downloadArtifact`

Паттерн для каждой функции:
```ts
// List — возвращает entity-тип
export async function getProjects(): Promise<ListResponse<Project>> {
  // TODO: return (await apiClient.get("/projects")).data
  return { items: MOCK_PROJECTS }
}

// Create — возвращает CreateResponse (без updated_at)
export async function createProject(data: CreateProjectRequest): Promise<ProjectCreateResponse> {
  // TODO: return (await apiClient.post("/projects", data)).data
  return { id: "new-id", name: data.name, created_at: new Date().toISOString() }
}
```

Mock-данные: 2-3 проекта, по 2-3 чата на проект, по 3-5 сообщений на чат (с Markdown-контентом для assistant), sphere с Markdown, 1-2 артефакта. Достаточно для визуальной верификации в следующих итерациях.

`downloadArtifact` — `window.open()` на URL (mock: no-op или console.log).

### Шаг 6: Zustand stores — `src/stores/`

**`src/stores/ui-store.ts`:**
```ts
import { create } from "zustand"

interface UIState {
  sidebarOpen: boolean
  toggleSidebar: () => void
}

export const useUIStore = create<UIState>()((set) => ({
  sidebarOpen: true,
  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
}))
```

**`src/stores/stream-store.ts`:**
```ts
import { create } from "zustand"

interface StreamState {
  isStreaming: boolean
  streamingText: string
  activeTool: string | null
  streamingChatId: string | null
  startStream: (chatId: string) => void
  appendText: (chunk: string) => void
  setTool: (name: string | null) => void
  endStream: () => void
}

export const useStreamStore = create<StreamState>()((set) => ({
  isStreaming: false,
  streamingText: "",
  activeTool: null,
  streamingChatId: null,
  startStream: (chatId) =>
    set({ isStreaming: true, streamingText: "", activeTool: null, streamingChatId: chatId }),
  appendText: (chunk) =>
    set((s) => ({ streamingText: s.streamingText + chunk })),
  setTool: (name) => set({ activeTool: name }),
  endStream: () =>
    set({ isStreaming: false, streamingText: "", activeTool: null, streamingChatId: null }),
}))
```

### Шаг 7: MarkdownRenderer — `src/shared/components/MarkdownRenderer.tsx`

```tsx
import { Streamdown } from "streamdown"
import { code } from "@streamdown/code"
import { math } from "@streamdown/math"
import { mermaid } from "@streamdown/mermaid"

interface MarkdownRendererProps {
  children: string
  isStreaming?: boolean
}

export function MarkdownRenderer({ children, isStreaming }: MarkdownRendererProps) {
  return (
    <Streamdown
      plugins={{ code, math, mermaid }}
      animated={isStreaming}
      isAnimating={isStreaming}
    >
      {children}
    </Streamdown>
  )
}
```

Плагины: `@streamdown/code` (Shiki подсветка), `@streamdown/math` (KaTeX формулы), `@streamdown/mermaid` (диаграммы). CJK — не нужен.

> **Примечание:** `animated` и `isAnimating` — валидные props Streamdown (подтверждено в npm README и "With AI Streaming" разделе документации). Если при реализации TypeScript покажет ошибку — быстрая правка на уровне шага, не влияющая на архитектуру.

### Шаг 8: Линтинг и проверки

```bash
make lint-fe      # ESLint
make format-fe    # Prettier
cd frontend && npx tsc -b  # TypeScript strict mode
```

Исправить все ошибки до коммита.

## Создаваемые файлы

```
frontend/src/
├── shared/
│   ├── api/
│   │   ├── client.ts          # axios instance (NEW)
│   │   ├── types.ts           # TS-типы 1:1 с backend schemas (NEW)
│   │   ├── projects.ts        # getProjects, getProject, createProject, updateProject, deleteProject (NEW)
│   │   ├── chats.ts           # getChats, getChat, createChat, getRecentChats (NEW)
│   │   ├── sphere.ts          # getSphere, updateSphere (NEW)
│   │   └── artifacts.ts       # getArtifacts, getArtifact, downloadArtifact (NEW)
│   ├── components/
│   │   └── MarkdownRenderer.tsx  # обёртка над Streamdown (NEW)
│   └── ui/
│       ├── dialog.tsx          # shadcn/ui (NEW via CLI)
│       ├── tabs.tsx            # shadcn/ui (NEW via CLI)
│       ├── scroll-area.tsx     # shadcn/ui (NEW via CLI)
│       └── textarea.tsx        # shadcn/ui (NEW via CLI)
├── stores/
│   ├── ui-store.ts             # Zustand UI store (NEW)
│   └── stream-store.ts         # Zustand stream store (NEW)
└── main.tsx                    # добавить import "streamdown/styles.css" (EDIT)
```

## Модифицируемые файлы

| Файл | Изменение |
|------|-----------|
| `frontend/package.json` | npm install добавит axios, zustand, streamdown, @streamdown/code, @streamdown/math, @streamdown/mermaid, katex |
| `frontend/src/index.css` | `@source` для streamdown, @streamdown/code, @streamdown/math, @streamdown/mermaid |
| `frontend/src/main.tsx` | `import "streamdown/styles.css"` + `import "katex/dist/katex.min.css"` |

## Что НЕ входит в итерацию

- TanStack Query хуки — создаются в feat-003..006 вместе с feature-компонентами
- Интеграция stores с компонентами — feat-003 (sidebar toggle), feat-005 (streaming)
- Замена stub-компонентов — feat-003..006
- SSE `useAgentStream` хук — feat-005

## Верификация

Агент выполняет все проверки **после реализации, перед отдачей на ревью архитектору**.

### Фаза 1: Статический анализ

```bash
make format-fe                      # Prettier — форматирование
make lint-fe                        # ESLint — 0 errors, 0 warnings
cd frontend && npx tsc -b           # TypeScript strict — 0 errors
cd frontend && npx vite build       # Production build — success
```

Все четыре команды должны пройти без ошибок. Если `vite build` успешен — все модули, импорты и типы валидны.

### Фаза 2: Runtime-верификация (Claude In Chrome)

Запустить `make dev-fe`, открыть приложение в Chrome.

#### 2.1 Регрессия feat-001

Навигация по всем 6 маршрутам — убедиться, что ничего не сломано:

| # | Маршрут | Ожидание |
|---|---------|----------|
| 1 | `/` | WelcomePage рендерится |
| 2 | `/projects/demo` | ProjectLayout с табами Chats/Sphere/Artifacts |
| 3 | `/projects/demo/chats/test` | ChatStub |
| 4 | `/projects/demo/sphere` | SphereStub |
| 5 | `/projects/demo/artifacts` | ArtifactsStub |
| 6 | `/projects/demo/artifacts/a1` | ArtifactViewStub |

#### 2.2 API-моки (browser console)

Вызвать каждую функцию из каждого API-модуля, проверить shape ответа:

```js
// projects.ts
const p = await import('/src/shared/api/projects.ts')
console.log('getProjects:', await p.getProjects())
// → { items: [{ id, name, created_at, updated_at }, ...] }
console.log('getProject:', await p.getProject('id'))
// → { id, name, created_at, updated_at }
console.log('createProject:', await p.createProject({ name: 'test' }))
// → { id, name, created_at } — без updated_at
console.log('updateProject:', await p.updateProject('id', { name: 'upd' }))
// → { id, name, created_at, updated_at }
console.log('deleteProject:', await p.deleteProject('id'))
// → void / undefined

// chats.ts
const c = await import('/src/shared/api/chats.ts')
console.log('getChats:', await c.getChats('project-id'))
// → { items: [{ thread_id, title, created_at, updated_at }] }
console.log('getChat:', await c.getChat('project-id', 'chat-id'))
// → { thread_id, title, messages: [{ id, role, content, created_at }] }
console.log('createChat:', await c.createChat('project-id', {}))
// → { thread_id, title, created_at } — без updated_at
console.log('getRecentChats:', await c.getRecentChats())
// → { items: [{ thread_id, title, project_id, project_name, updated_at }] }

// sphere.ts
const s = await import('/src/shared/api/sphere.ts')
console.log('getSphere:', await s.getSphere('project-id'))
// → { project_id, content, updated_at }
console.log('updateSphere:', await s.updateSphere('project-id', { content: 'new' }))
// → { project_id, content, updated_at }

// artifacts.ts
const a = await import('/src/shared/api/artifacts.ts')
console.log('getArtifacts:', await a.getArtifacts('project-id'))
// → { items: [{ id, title, type, created_at }] }
console.log('getArtifact:', await a.getArtifact('project-id', 'artifact-id'))
// → { id, title, type, content, thread_id, created_at }
```

Проверка: каждый ответ содержит ожидаемые поля с правильными типами (строки, массивы). Никаких `undefined` полей.

#### 2.3 Zustand stores (browser console)

```js
// UI Store
const { useUIStore } = await import('/src/stores/ui-store.ts')
console.log('Initial:', useUIStore.getState())
// → { sidebarOpen: true, toggleSidebar: fn }
useUIStore.getState().toggleSidebar()
console.log('After toggle:', useUIStore.getState().sidebarOpen)
// → false
useUIStore.getState().toggleSidebar()
console.log('After 2nd toggle:', useUIStore.getState().sidebarOpen)
// → true

// Stream Store
const { useStreamStore } = await import('/src/stores/stream-store.ts')
console.log('Initial:', useStreamStore.getState())
// → { isStreaming: false, streamingText: "", activeTool: null, streamingChatId: null, ... }
useStreamStore.getState().startStream('chat-123')
console.log('After startStream:', useStreamStore.getState())
// → { isStreaming: true, streamingChatId: "chat-123", streamingText: "", ... }
useStreamStore.getState().appendText('Hello ')
useStreamStore.getState().appendText('world')
console.log('After appendText:', useStreamStore.getState().streamingText)
// → "Hello world"
useStreamStore.getState().setTool('web_search')
console.log('activeTool:', useStreamStore.getState().activeTool)
// → "web_search"
useStreamStore.getState().endStream()
console.log('After endStream:', useStreamStore.getState())
// → { isStreaming: false, streamingText: "", activeTool: null, streamingChatId: null }
```

#### 2.4 MarkdownRenderer (визуально)

**Перед верификацией**: временно добавить в WelcomePage:
```tsx
<MarkdownRenderer>{`# Heading\n\nSome **bold** and *italic* text.\n\n\`\`\`typescript\nconst greeting: string = "Hello, World!";\nconsole.log(greeting);\n\`\`\`\n\n- List item 1\n- List item 2\n\nМатематика: $$E = mc^2$$\n\n\`\`\`mermaid\ngraph LR\n    A[Start] --> B[End]\n\`\`\``}</MarkdownRenderer>
```

Визуально проверить на `/`:
- Heading рендерится как заголовок
- Bold/italic применяются
- Code block с подсветкой синтаксиса TypeScript (Shiki)
- Список рендерится
- LaTeX формула рендерится через KaTeX ($$E = mc^2$$)
- Mermaid диаграмма рендерится как граф (Start → End)

**После верификации**: удалить временную вставку из WelcomePage перед коммитом.

### Чеклист критериев приёмки

| # | Критерий | Как проверяется |
|---|----------|-----------------|
| 1 | API-модули экспортируют все функции из frontend.md | Фаза 2.2 — каждая функция вызвана |
| 2 | Моки возвращают типизированные данные, соответствующие backend schemas | Фаза 1 (tsc) + Фаза 2.2 (runtime shape) |
| 3 | Zustand stores работают: toggleSidebar переключает state | Фаза 2.3 — toggle + проверка |
| 4 | MarkdownRenderer рендерит Markdown с подсветкой синтаксиса | Фаза 2.4 — визуальная проверка |
| 5 | Типы покрывают все сущности: Project, Chat, Message, Sphere, Artifact, SSE events | Фаза 1 (tsc strict) — неиспользуемые типы компилируются |
| 6 | Линтер и TypeScript проходят без ошибок | Фаза 1 — lint + tsc |

## Финальный шаг

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.
