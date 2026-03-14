# Implementation Plan: feat-003 — Sidebar + Projects

## Context

Итерации feat-001 (scaffold) и feat-002 (shared infra) завершены. Есть работающее приложение со stub-sidebar, mock API-модулями, Zustand stores, shadcn/ui компонентами. Следующий шаг — реализовать полноценную sidebar-навигацию (список проектов, recent chats, кнопки создания) и обогатить ProjectLayout. После итерации — полноценная навигация по приложению, создание проектов.

## Референсы

- [workflow.md](../../../../workflow.md) — жизненный цикл итерации
- [conventions.md](../../../tech/conventions.md) — git flow, именование
- [frontend.md](../../../tech/frontend.md) — компоненты, state, query keys, module structure
- [tasklist-frontend.md](../../tasklist-frontend.md) — состав работ и критерии приёмки
- [backend.md](../../../tech/backend.md) — API-контракт (schemas)
- [ADR-008](../../../tech/adr/ADR-008-frontend-stack.md) — frontend stack

## Проверка API инструментов

Проверены из исходного кода установленных пакетов (приоритет 1 по CLAUDE.md):

| Инструмент | Версия | Ключевой API для feat-003 |
|-----------|--------|--------------------------|
| TanStack Query v5 | 5.90.0 | `useQuery({ queryKey, queryFn })`, `useMutation({ mutationFn, onSuccess })`, `useQueryClient()` — стандартный single-object API |
| shadcn/ui (base-ui) | 4.0.5 / @base-ui 1.3.0 | Dialog: `open`, `onOpenChange` props; Tabs: `value`, `onValueChange`, `TabsTrigger value={...}` |
| Zustand v5 | 5.0.11 | `create<T>()((set) => ...)` — уже используется в `ui-store.ts` |
| React Router v7 | 7.13.1 | `useParams`, `useMatch`, `useNavigate`, `Link`, `NavLink` — library mode |
| Lucide React | 0.577.0 | Tree-shakeable icons: `Plus`, `MessageSquare`, `FolderOpen`, `PanelLeft`, `PanelLeftClose` |

## Шаг 0 — Ветка

```bash
git fetch origin && git checkout -b feat/003-sidebar-projects origin/develop
```

## Шаг 1 — TanStack Query хуки

Создать хуки в `features/`. Query keys строго по спецификации из frontend.md. Каждый хук — отдельный файл.

### features/projects/hooks/

| Файл | Тип | Query Key / Mutation | Инвалидация |
|------|-----|---------------------|-------------|
| `useProjects.ts` | query | `["projects"]` | — |
| `useProject.ts` | query | `["projects", id]` | — |
| `useCreateProject.ts` | mutation | `createProject(data)` | `["projects"]` |
| `useUpdateProject.ts` | mutation | `updateProject(id, data)` | `["projects"]` |
| `useDeleteProject.ts` | mutation | `deleteProject(id)` | `["projects"]` |

Паттерн (пример `useProjects.ts`):
```tsx
import { useQuery } from "@tanstack/react-query";
import { getProjects } from "@/shared/api/projects";

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: getProjects,
  });
}
```

Паттерн мутации (пример `useCreateProject.ts`):
```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createProject } from "@/shared/api/projects";

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
```

### features/chat/hooks/

| Файл | Тип | Query Key |
|------|-----|-----------|
| `useRecentChats.ts` | query | `["chats", "recent"]` |

### Переиспользуемые модули

- API-функции: `shared/api/projects.ts` (getProjects, getProject, createProject, updateProject, deleteProject)
- API-функции: `shared/api/chats.ts` (getRecentChats)
- Типы: `shared/api/types.ts` (Project, RecentChat, CreateProjectRequest, etc.)

## Шаг 2 — Мутабельные моки

Для выполнения критерия приёмки «CreateProjectModal создаёт проект (mock), проект появляется в sidebar» — моки в `shared/api/projects.ts` должны стать мутабельными.

Изменения в `shared/api/projects.ts`:
- `MOCK_PROJECTS` → `let mockProjects = [...]` (мутабельный массив)
- `createProject()` — внутренне создаёт полный `Project` (с `updated_at = created_at`), pushes в `mockProjects`, но **возвращает `ProjectCreateResponse`** (без `updated_at`) — строго по API-контракту backend.md. Так `getProject(id)` найдёт корректный объект с `updated_at`.
- `getProjects()` → returns `{ items: mockProjects }`
- `deleteProject()` → removes from `mockProjects`
- `updateProject()` — **остаётся без мутации** (возвращает статический объект). В feat-003 нет UI для редактирования проекта, хук useUpdateProject просто вызывает существующий mock.

## Шаг 3 — Feature-компоненты

### features/projects/components/ProjectCard.tsx

Элемент списка проектов в sidebar. Принимает `Project`, рендерит имя проекта. Клик → `Link` на `/projects/:id`. Подсвечивает текущий проект (активный маршрут).

### features/projects/components/ProjectList.tsx

Использует `useProjects()` хук. Рендерит список `ProjectCard`. Обрабатывает loading/error states.

### features/projects/components/CreateProjectModal.tsx

shadcn `Dialog` с controlled state (`open` / `onOpenChange`). Содержит:
- `DialogHeader` с `DialogTitle` "New Project"
- `Input` для названия проекта
- `Button` "Create" — вызывает `useCreateProject().mutate({ name })`
- При успешном создании: закрывает модалку, навигация на `/projects/:id`

Использует: `Dialog`, `DialogContent`, `DialogHeader`, `DialogTitle`, `DialogFooter` из `shared/ui/dialog`, `Input` из `shared/ui/input`, `Button` из `shared/ui/button`.

## Шаг 4 — Sidebar

### app/components/Sidebar.tsx

Замена stub-sidebar из AppLayout. Структура:

```
┌─────────────────────┐
│ LearnFlowAI    [<<]  │  ← заголовок + кнопка collapse
├─────────────────────┤
│ [+ New Chat]        │  ← disabled если !projectId
│ [+ New Project]     │  ← открывает CreateProjectModal
├─────────────────────┤
│ Projects            │  ← секция
│  ▸ Project 1        │
│  ▸ Project 2        │
│  ▸ Project 3        │
├─────────────────────┤
│ Recents             │  ← секция
│  ▸ Chat title (proj)│  ← recent chats
│  ▸ Chat title (proj)│
└─────────────────────┘
```

**Определение контекста проекта:**
```tsx
const projectMatch = useMatch("/projects/:id/*");
const projectId = projectMatch?.params.id;
// New Chat disabled={!projectId}
```

**New Chat** — UI-элемент: кнопка присутствует, `disabled` вне контекста проекта, клик — **no-op**. Граница scope: кнопка готова визуально и по логике enabled/disabled, creation action подключается в feat-004 (useCreateChat явно отнесён к feat-004 в таск-листе). Фиксируется в summary итерации.

**Recents** — использует `useRecentChats()` хук. Каждый элемент: `Link` на `/projects/${chat.project_id}/chats/${chat.thread_id}`, отображает `chat.title` и `chat.project_name`. Именование полей строго по `RecentChat` из `types.ts` (`project_id`, `thread_id`), route param — `:cid` (из `router.tsx`).

**Collapse** — кнопка вызывает `useUIStore().toggleSidebar()`.

## Шаг 5 — AppLayout

### app/layouts/AppLayout.tsx

Изменения:
- Импорт и рендер `Sidebar` вместо inline-стаба
- Интеграция с `useUIStore().sidebarOpen` через **CSS-based скрытие** (не conditional rendering):
  - `sidebarOpen === true`: sidebar с `w-64`
  - `sidebarOpen === false`: sidebar с `w-0 overflow-hidden` (sidebar остаётся mounted, хуки кешированы, скролл сохраняется)
  - `transition-all duration-200` для плавной анимации
- Кнопка expand (Lucide `PanelLeft`) в main area — видна только при `!sidebarOpen`

```tsx
export function AppLayout() {
  const { sidebarOpen, toggleSidebar } = useUIStore();
  return (
    <div className="flex h-screen">
      <aside className={cn(
        "shrink-0 border-r border-border bg-sidebar transition-all duration-200 overflow-hidden",
        sidebarOpen ? "w-64" : "w-0 border-r-0"
      )}>
        <Sidebar />
      </aside>
      <main className="flex-1 overflow-auto">
        {!sidebarOpen && (
          <button onClick={toggleSidebar} className="...">
            <PanelLeft />
          </button>
        )}
        <Outlet />
      </main>
    </div>
  );
}
```

## Шаг 6 — ProjectLayout

### app/layouts/ProjectLayout.tsx

Изменения:
- Добавить `useProject(id!)` хук для получения реального имени проекта
- Заменить `"Project: {id}"` на `project.name` (с loading fallback)
- Табы (NavLink) остаются как есть — это route-based навигация, shadcn `Tabs` не подходит для маршрутизации через `Outlet`

## Шаг 6.5 — WelcomePage (минимальный fix)

### app/components/WelcomePage.tsx

Текущая ссылка `"Open Demo Project" → /projects/demo` станет мёртвой после подключения реальных mock-проектов. Минимальное исправление: убрать кнопку с хардкод-ссылкой, оставить welcome-текст. Проекты доступны через sidebar — отдельная кнопка на welcome-странице не нужна (frontend.md: "Welcome — без input, создание чата только из проекта").

## Шаг 7 — Верификация

Верификация обязательна и состоит из двух этапов: технические проверки (lint/typecheck) и **ручное прохождение всех критериев приёмки через браузер** с использованием Claude in Chrome (MCP browser automation).

### 7.1 — Технические проверки

```bash
make lint-fe     # ESLint — 0 ошибок
make format-fe   # Prettier
# TypeScript strict — 0 ошибок (часть build: tsc -b)
```

Если есть ошибки — исправить до перехода к браузерной верификации.

### 7.2 — Браузерная верификация (Claude in Chrome)

Запустить `make dev-fe`, открыть приложение в Chrome. Пройти каждый критерий приёмки через MCP browser tools, фиксируя результат (pass/fail).

**Чеклист:**

1. **Sidebar отображает список проектов из mock-данных**
   - Открыть `/` — sidebar видим, содержит секцию Projects с 3 mock-проектами
   - Проверить: имена проектов соответствуют mock-данным

2. **Клик по проекту → навигация на `/projects/:id`**
   - Кликнуть по проекту в sidebar
   - Проверить: URL изменился на `/projects/proj-1` (или соответствующий ID)
   - Проверить: ProjectLayout рендерится с именем проекта (не ID)

3. **CreateProjectModal открывается, создаёт проект, проект появляется в sidebar**
   - Кликнуть "New Project" в sidebar
   - Проверить: модалка открылась
   - Ввести название (например, "Test Project") → кликнуть "Create"
   - Проверить: модалка закрылась
   - Проверить: новый проект появился в списке sidebar
   - Проверить: навигация на страницу нового проекта произошла

4. **ProjectLayout рендерит табы, переключение работает**
   - На странице проекта: заголовок = имя проекта (не raw ID)
   - Кликнуть каждый таб (Chats / Sphere / Artifacts)
   - Проверить: URL меняется соответственно
   - Проверить: содержимое центральной области меняется (стабы)

5. **Recent chats отображаются в sidebar, клик → навигация в чат**
   - Проверить: секция Recents показывает mock recent chats с названиями и именами проектов
   - Кликнуть по recent chat
   - Проверить: URL = `/projects/:id/chats/:cid` (корректные ID из mock-данных)

6. **Sidebar складывается/разворачивается**
   - Кликнуть кнопку collapse
   - Проверить: sidebar скрыт (плавная анимация)
   - Проверить: кнопка expand видна в main area
   - Кликнуть expand
   - Проверить: sidebar восстановлен

7. **New Chat кнопка — enabled/disabled по контексту**
   - На `/` — кнопка New Chat disabled
   - На `/projects/:id` — кнопка New Chat enabled

При обнаружении fail — исправить и повторить проверку до полного прохождения всех пунктов.

## Создаваемые файлы

| Файл | Назначение |
|------|-----------|
| `frontend/src/features/projects/hooks/useProjects.ts` | Query: список проектов |
| `frontend/src/features/projects/hooks/useProject.ts` | Query: один проект |
| `frontend/src/features/projects/hooks/useCreateProject.ts` | Mutation: создание проекта |
| `frontend/src/features/projects/hooks/useUpdateProject.ts` | Mutation: обновление проекта |
| `frontend/src/features/projects/hooks/useDeleteProject.ts` | Mutation: удаление проекта |
| `frontend/src/features/chat/hooks/useRecentChats.ts` | Query: recent chats |
| `frontend/src/features/projects/components/ProjectCard.tsx` | Карточка проекта в sidebar |
| `frontend/src/features/projects/components/ProjectList.tsx` | Список проектов (вызывает useProjects) |
| `frontend/src/features/projects/components/CreateProjectModal.tsx` | Модалка создания проекта |
| `frontend/src/app/components/Sidebar.tsx` | Полноценный sidebar (замена стаба) |

## Модифицируемые файлы

| Файл | Изменение |
|------|-----------|
| `frontend/src/shared/api/projects.ts` | Мутабельные моки (createProject pushes с полным Project, deleteProject removes; updateProject без мутации) |
| `frontend/src/app/layouts/AppLayout.tsx` | Sidebar компонент + CSS-based toggle (w-0/w-64 + transition) |
| `frontend/src/app/layouts/ProjectLayout.tsx` | useProject хук для имени проекта |
| `frontend/src/app/components/WelcomePage.tsx` | Убрать мёртвую ссылку на /projects/demo |

## Финальный шаг

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.
