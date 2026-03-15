# Implementation Plan: feat-002 — Frontend → Backend Connection

## Context

Все frontend API-модули (`shared/api/*.ts`) используют hardcoded mock-данные. Backend API полностью рабочий (верифицирован в feat-001, контракты согласованы в fix-001). Цель итерации — заменить моки реальными HTTP-вызовами, добавить MVP-авторизацию (ввод username) и настроить dev proxy.

## Референсы

- **Workflow:** [doc/workflow.md](../../doc/workflow.md) — итерационный цикл, формат веток и коммитов
- **Conventions:** [doc/tech/conventions.md](../../doc/tech/conventions.md) — git flow, именование, code quality
- **Tasklist:** [doc/tasks/tasklist-integration.md](../../doc/tasks/tasklist-integration.md) — feat-002 scope
- **Backend spec:** [doc/tech/backend.md](../../doc/tech/backend.md) — API endpoints, schemas, SSE protocol, auth
- **Frontend spec:** [doc/tech/frontend.md](../../doc/tech/frontend.md) — API-интеграция, state management, module structure
- **fix-001 summary:** [doc/tasks/iterations/integration/fix-001-contract-alignment/summary.md](...) — что было согласовано
- **Vite proxy docs:** [.firecrawl/vite-server-options.md] — актуальный API `server.proxy`
- **FastAPI CORS docs:** [.firecrawl/fastapi-cors.md] — CORSMiddleware reference

## Архитектурные решения (согласованы с архитектором)

1. **Dev proxy:** Vite Proxy (`server.proxy`), не CORS. Зеркалит будущий Nginx reverse proxy на VM. Frontend использует относительный URL `/api`. CORS на backend остаётся как fallback.
2. **SSE transition:** Вариант B — удалить ВСЕ моки, принять регрессию chat messaging до feat-003.
3. **Download artifact:** Axios blob download вместо `window.open()` (X-User-Name header).
4. **Auth UI:** shadcn Dialog (модалка при первом визите).

## Шаги

### 0. Prerequisites + Git setup

**Зависимости (verified):**
- `integration/fix-001` — ✅ Done, merged (commit `a5d103b`)
- `frontend/feat-006` — ✅ Done, merged в develop (commit `9796ffa`, PR #23)

```bash
git fetch origin && git checkout -b feat/002-frontend-backend origin/develop
```

Ветка `feat/002-frontend-backend` согласно conventions.md: `<type>/<NNN>-<short-desc>`.

---

### 1. Vite Proxy

**Файл:** `frontend/vite.config.ts`

Добавить `server.proxy` для перенаправления `/api/*` → `http://localhost:8000/*`:

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
      rewrite: (path) => path.replace(/^\/api/, ''),
    },
  },
},
```

Логика: `/api/projects` → `http://localhost:8000/projects` (strip `/api` prefix).

---

### 2. HTTP-клиент: baseURL + dynamic X-User-Name

**Файл:** `frontend/src/shared/api/client.ts`

Изменения:
1. `baseURL`: `import.meta.env.VITE_API_URL ?? "/api"` (относительный URL, Vite proxy подхватит)
2. Убрать hardcoded `X-User-Name` из `headers` конфига
3. Добавить request interceptor, который читает username из `localStorage` и ставит `X-User-Name` header
4. Экспортировать helper `getUsername(): string` для использования в `useAgentStream` (fetch, не axios)

```typescript
const USERNAME_KEY = "learnflow-username";

export function getUsername(): string {
  return localStorage.getItem(USERNAME_KEY) ?? "";
}

export function setUsername(name: string): void {
  localStorage.setItem(USERNAME_KEY, name);
}

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL ?? "/api",
});

apiClient.interceptors.request.use((config) => {
  const username = getUsername();
  if (username) {
    config.headers["X-User-Name"] = username;
  }
  return config;
});

// error interceptor stays as-is
```

---

### 3. MVP Auth UI (AuthGate)

**Новый файл:** `frontend/src/app/components/AuthGate.tsx`

Компонент-обёртка:
- Проверяет `localStorage` на наличие username (через `getUsername()` из client.ts)
- Если нет — показывает shadcn `Dialog` (open=true) с `Input` + `Button`
- **Защита от закрытия без ввода:** `onOpenChange` — игнорировать если username пустой; `DialogContent` → `onEscapeKeyDown={e => e.preventDefault()}`, `onPointerDownOutside={e => e.preventDefault()}`
- При сабмите: вызывает `setUsername(name)` → рендерит children
- Shadcn компоненты: `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogDescription` — уже есть в `shared/ui/dialog.tsx`; `Input` и `Button` — тоже есть

**Файл:** `frontend/src/App.tsx`

Обернуть содержимое в `AuthGate`:
```tsx
export function App() {
  return (
    <AuthGate>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </AuthGate>
  );
}
```

`AuthGate` вне `BrowserRouter` и `Providers` — не зависит от роутинга и React Query.

---

### 4. Удаление моков из API-модулей

Для каждого модуля: удалить mock-данные, удалить mock-логику, раскомментировать/написать реальные axios-вызовы. Паттерн одинаковый — тип уже совпадает с backend schemas (выверено в fix-001).

#### 4.1 `frontend/src/shared/api/projects.ts`

Удалить: `mockProjects`, всю mock-логику.
Реализация (каждая функция — одна строка):
```typescript
import { apiClient } from "./client";

export async function getProjects(): Promise<ListResponse<Project>> {
  return (await apiClient.get("/projects")).data;
}
export async function getProject(id: string): Promise<Project> {
  return (await apiClient.get(`/projects/${id}`)).data;
}
export async function createProject(data: CreateProjectRequest): Promise<Project> {
  return (await apiClient.post("/projects", data)).data;
}
export async function updateProject(id: string, data: UpdateProjectRequest): Promise<Project> {
  return (await apiClient.put(`/projects/${id}`, data)).data;
}
export async function deleteProject(id: string): Promise<void> {
  await apiClient.delete(`/projects/${id}`);
}
```

#### 4.2 `frontend/src/shared/api/chats.ts`

Удалить: `MOCK_CHATS`, `MOCK_CHAT_DETAIL`, `MOCK_RECENT_CHATS`, `MOCK_RESPONSE_TEXT`, `delay()`, `encodeSSE()`, `mockSendMessage()`, `cancelledChats`.

Реализация:
```typescript
import { apiClient } from "./client";

export async function getChats(projectId: string): Promise<ListResponse<Chat>> {
  return (await apiClient.get(`/projects/${projectId}/chats`)).data;
}
export async function getChat(projectId: string, chatId: string): Promise<ChatDetail> {
  return (await apiClient.get(`/projects/${projectId}/chats/${chatId}`)).data;
}
export async function createChat(projectId: string, data: CreateChatRequest): Promise<Chat> {
  return (await apiClient.post(`/projects/${projectId}/chats`, data)).data;
}
export async function getRecentChats(): Promise<ListResponse<RecentChat>> {
  return (await apiClient.get("/chats/recent")).data;
}
export async function cancelChat(projectId: string, chatId: string): Promise<{ ok: boolean }> {
  return (await apiClient.post(`/projects/${projectId}/chats/${chatId}/cancel`)).data;
}
```

#### 4.3 `frontend/src/shared/api/sphere.ts`

Удалить: `MOCK_SPHERE`.

```typescript
import { apiClient } from "./client";

export async function getSphere(projectId: string): Promise<Sphere> {
  return (await apiClient.get(`/projects/${projectId}/sphere`)).data;
}
export async function updateSphere(projectId: string, data: UpdateSphereRequest): Promise<Sphere> {
  return (await apiClient.put(`/projects/${projectId}/sphere`, data)).data;
}
```

#### 4.4 `frontend/src/shared/api/artifacts.ts`

Удалить: `MOCK_ARTIFACTS`, `MOCK_ARTIFACT_DETAILS`.

```typescript
export async function getArtifacts(projectId: string): Promise<ListResponse<Artifact>> {
  return (await apiClient.get(`/projects/${projectId}/artifacts`)).data;
}
export async function getArtifact(projectId: string, artifactId: string): Promise<ArtifactDetail> {
  return (await apiClient.get(`/projects/${projectId}/artifacts/${artifactId}`)).data;
}
```

`downloadArtifact` — см. шаг 5.

---

### 5. downloadArtifact: axios blob download

**Файл:** `frontend/src/shared/api/artifacts.ts`

Заменить `window.open()` на axios blob download с X-User-Name header:

```typescript
export async function downloadArtifact(
  projectId: string,
  artifactId: string,
  format: "md" | "pdf" = "md",
): Promise<void> {
  const response = await apiClient.get(
    `/projects/${projectId}/artifacts/${artifactId}/download`,
    { params: { format }, responseType: "blob" },
  );
  const blob = new Blob([response.data]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  // Extract filename from Content-Disposition header or fallback
  const disposition = response.headers["content-disposition"];
  const filenameMatch = disposition?.match(/filename="?(.+?)"?$/);
  a.download = filenameMatch?.[1] ?? `artifact.${format}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
```

**Влияние на вызывающий код:** `downloadArtifact` становится `async` (возвращает `Promise<void>` вместо `void`). Проверить вызов в `ArtifactView` — обернуть в `onClick` handler с `await` или `.catch()`.

---

### 6. Project CRUD UI (rename/delete)

**Проблема:** Хуки `useUpdateProject` и `useDeleteProject` существуют, но в UI нет элементов для вызова rename/delete. Acceptance criteria: "CRUD-операции с проектами работают через UI".

**Установка shadcn компонента:** `npx shadcn@latest add dropdown-menu` — для контекстного меню на ProjectCard.

**Новый компонент:** `frontend/src/features/projects/components/ProjectActions.tsx`

DropdownMenu с двумя пунктами:
- **Rename** → открывает Dialog с Input (pre-filled текущим именем), вызывает `useUpdateProject`
- **Delete** → открывает Dialog с подтверждением, вызывает `useDeleteProject`. После удаления — redirect на `/` (через `useNavigate`)

Trigger: кнопка "..." (MoreHorizontal icon из lucide-react), появляется при hover на ProjectCard.

**Модификация:** `frontend/src/features/projects/components/ProjectCard.tsx`

Добавить `ProjectActions` как sibling к NavLink (абсолютно позиционированный, visible on hover). `stopPropagation` на клике по DropdownMenu, чтобы не триггерить NavLink.

Переиспользуемые компоненты: `Dialog`, `Input`, `Button` из `shared/ui/`, `useUpdateProject`/`useDeleteProject` из `features/projects/hooks/`.

---

### 7. useAgentStream: переключение на real fetch

**Файл:** `frontend/src/features/chat/hooks/useAgentStream.ts`

Удалить импорт `mockSendMessage` из `@/shared/api/chats`.
Заменить вызов `mockSendMessage(...)` на real `fetch()`:

```typescript
import { getUsername } from "@/shared/api/client";

// Inside send() — вся async логика обёрнута в try-catch:
const send = useCallback(
  (content: string) => {
    const { startStream, appendText, setTool, addArtifact, endStream } =
      useStreamStore.getState();

    startStream(chatId);
    isCancellingRef.current = false;
    const controller = new AbortController();
    abortRef.current = controller;

    (async () => {
      try {
        const response = await fetch(
          `/api/projects/${projectId}/chats/${chatId}/messages`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-User-Name": getUsername(),
            },
            body: JSON.stringify({ content }),
            signal: controller.signal,
          },
        );

        if (!response.ok) {
          endStream();
          optionsRef.current?.onError?.(`HTTP ${response.status}`);
          return;
        }

        const reader = response.body!.getReader();
        // ...existing stream reading logic (unchanged)
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        console.error("[SSE stream error]", err);
        endStream();
        optionsRef.current?.onError?.(
          err instanceof Error ? err.message : "Connection error",
        );
      }
    })();
  },
  [projectId, chatId, queryClient],
);
```

**Ключевые изменения vs текущий код:**
1. `send` остаётся **синхронной** (возвращает `void`, не `Promise`) — async IIFE внутри. Вызов из ChatView не меняется.
2. Весь async-код (fetch + read) обёрнут в **единый try-catch** → при ошибке fetch (сеть, CORS, non-200) → `endStream()` + `onError()`. Optimistic message в `localMessages` остаётся — `ChatView.onError` может обработать (показать toast, например).
3. `response.ok` check — ловит HTTP-ошибки до начала чтения стрима.

**Примечание:** Это естественное следствие удаления `mockSendMessage` из chats.ts. Базовая SSE-связка заработает (backend endpoint рабочий с feat-001). Thorough SSE verification (все event types, cancel E2E, error handling, reconnection) — scope feat-003.

---

### 8. Проверка и адаптация вызывающего кода

Проверить компоненты и хуки, которые вызывают изменённые API-функции:

| Хук/Компонент | API-функция | Изменение |
|---|---|---|
| `useProjects` | `getProjects` | Без изменений (сигнатура та же) |
| `useProject` | `getProject` | Без изменений |
| `useCreateProject` | `createProject` | Без изменений |
| `useUpdateProject` | `updateProject` | Без изменений (теперь вызывается из ProjectActions) |
| `useDeleteProject` | `deleteProject` | Без изменений (теперь вызывается из ProjectActions) |
| `useChats` | `getChats` | Без изменений |
| `useChat` | `getChat` | Без изменений |
| `useCreateChat` | `createChat` | Без изменений |
| `useRecentChats` | `getRecentChats` | Без изменений |
| `useSphere` | `getSphere` | Без изменений |
| `useUpdateSphere` | `updateSphere` | Без изменений |
| `useArtifacts` | `getArtifacts` | Без изменений |
| `useArtifact` | `getArtifact` | Без изменений |
| `ArtifactView` | `downloadArtifact` | Проверить: стала async, обработать Promise |
| `useAgentStream` | `mockSendMessage` → `fetch` | Переписано (шаг 6) |
| `useAgentStream` | `cancelChat` | Остаётся как есть (уже импортирует из chats.ts) |

---

### 9. Линтинг и проверка типов

```bash
make lint-fe          # ESLint
cd frontend && npx tsc --noEmit   # TypeScript strict
```

Убедиться: нет ошибок, нет неиспользуемых импортов после удаления моков.

---

### 10. Верификация (ручная)

**Prerequisite:** backend и PostgreSQL запущены (`make docker-up && make migrate && make dev`), frontend dev server (`make dev-fe`).

#### REST-потоки:
- [ ] Ввод username при первом визите → имя сохраняется в localStorage → используется в запросах
- [ ] Создать проект → появляется в sidebar (данные из реального API)
- [ ] Список проектов загружается с backend
- [ ] Переименовать проект через "..." menu → название обновляется в sidebar и на странице проекта
- [ ] Удалить проект через "..." menu → подтверждение → проект исчезает из sidebar, redirect на `/`
- [ ] Создать чат в проекте → появляется в списке чатов
- [ ] Список чатов проекта загружается с backend
- [ ] Recents загружаются с backend
- [ ] Sphere: просмотр (GET) → отображается Markdown
- [ ] Sphere: редактирование (PUT) → данные персистятся, повторный GET отражает изменения
- [ ] Artifacts: список загружается с backend
- [ ] Artifacts: просмотр конкретного артефакта
- [ ] Artifacts: скачивание (md) через blob download
- [ ] CORS: нет ошибок в консоли (запросы идут через Vite proxy, не cross-origin)

#### Known limitations (regression до feat-003):
- Отправка сообщений в чат: SSE endpoint вызывается реально, но full E2E flow не верифицирован. Могут быть edge cases. Thorough SSE verification — scope feat-003.

---

### 11. Ревью и коммит

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.

## Затрагиваемые файлы

| Файл | Тип изменения |
|---|---|
| `frontend/vite.config.ts` | Modify: add `server.proxy` |
| `frontend/src/shared/api/client.ts` | Modify: baseURL, dynamic X-User-Name, export helpers |
| `frontend/src/shared/api/projects.ts` | Modify: remove mocks → real axios |
| `frontend/src/shared/api/chats.ts` | Modify: remove mocks + mockSendMessage → real axios |
| `frontend/src/shared/api/sphere.ts` | Modify: remove mocks → real axios |
| `frontend/src/shared/api/artifacts.ts` | Modify: remove mocks → real axios, blob download |
| `frontend/src/app/components/AuthGate.tsx` | **New**: auth modal component |
| `frontend/src/App.tsx` | Modify: wrap with AuthGate |
| `frontend/src/shared/ui/dropdown-menu.tsx` | **New**: shadcn DropdownMenu (install) |
| `frontend/src/features/projects/components/ProjectActions.tsx` | **New**: rename/delete dropdown + dialogs |
| `frontend/src/features/projects/components/ProjectCard.tsx` | Modify: add ProjectActions trigger |
| `frontend/src/features/chat/hooks/useAgentStream.ts` | Modify: mockSendMessage → real fetch + error handling |
| `frontend/src/features/artifacts/components/ArtifactView.tsx` | Modify: handle async downloadArtifact (if needed) |
