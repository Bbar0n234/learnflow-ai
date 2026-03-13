# Implementation Plan: feat-001 — Scaffold + App Shell

## Context

Первая итерация фронтенда. Цель — поднять React-приложение на полном стеке (Vite + TypeScript + Tailwind v4 + shadcn/ui), настроить роутинг и layout-каркас. После итерации — запускаемое приложение с навигацией между stub-страницами.

**Blocked by:**
- `infra/chore-001` ✅ Done — `frontend/` существует с `package.json` и каркасом проекта
- `infra/chore-002` ✅ Done — ESLint + Prettier + TypeScript настроены, `eslint.config.mjs` на месте
- `infra/chore-003` ✅ Done — Makefile с `dev-fe` (заглушка), `lint-fe`, `format-fe`

## Референсы

| Документ | Что берём |
|----------|-----------|
| [doc/tasks/tasklist-frontend.md](../../doc/tasks/tasklist-frontend.md) | Состав работ, критерии приёмки |
| [doc/tech/frontend.md](../../doc/tech/frontend.md) | Module structure, маршруты, layouts, компонентная архитектура |
| [doc/tech/adr/ADR-008-frontend-stack.md](../../doc/tech/adr/ADR-008-frontend-stack.md) | Обоснование стека |
| [doc/tech/backend.md](../../doc/tech/backend.md) | API-контракт (маршруты) |
| [doc/tech/conventions.md](../../doc/tech/conventions.md) | Git flow, именование, Code Quality |
| [doc/workflow.md](../../doc/workflow.md) | Жизненный цикл итерации |

## Verified Tool Versions

| Инструмент | Версия | Пакет | Примечание |
|-----------|--------|-------|------------|
| Vite | **7.3.1** | `vite` | v8 несовместим с @tailwindcss/vite (peer: ^5.2‖^6‖^7) |
| React | latest | `react`, `react-dom` | |
| TypeScript | ~5.9 | `typescript` (уже установлен) | |
| Tailwind CSS | 4.2.1 | `tailwindcss`, `@tailwindcss/vite` | CSS-first config, без tailwind.config.js |
| shadcn/ui | 4.0.5 | `shadcn` (CLI) | + class-variance-authority, clsx, tailwind-merge, lucide-react, tw-animate-css |
| React Router | 7.13.1 | `react-router` | Declarative mode (BrowserRouter + Routes + Route) |
| TanStack Query | 5.90.x | `@tanstack/react-query` | Только QueryClientProvider в этой итерации |
| @vitejs/plugin-react | 5.2.0 | `@vitejs/plugin-react` | Совместим с Vite 7 |
| ESLint React plugins | latest | `eslint-plugin-react-hooks`, `eslint-plugin-react-refresh` | Дополнение к существующему ESLint конфигу |

## Решения архитектора

- **Vite 7.3.1** — стабильная совместимость со всеми плагинами
- **CSS в `src/index.css`** — стандартная Vite-конвенция (отклонение от frontend.md, где показан `tailwind.css` на корневом уровне)
- **`npx shadcn@latest init`** → корректировка aliases под нашу структуру → `npx shadcn add`

---

## Шаги реализации

### Step 0: Branch

```bash
git fetch origin && git checkout -b feat/001-scaffold-app-shell origin/develop
```

Ветка: `feat/001-scaffold-app-shell` (conventions.md: `<type>/<NNN>-<short-desc>`).

---

### Step 1: Vite + React + TypeScript

**Что делаем:** Устанавливаем зависимости и создаём конфигурационные файлы поверх существующего `frontend/package.json`.

**Файлы:**

1. **`frontend/package.json`** — добавить dependencies, devDependencies и scripts:
   ```
   dependencies:
     react, react-dom, react-router, @tanstack/react-query

   devDependencies (дополнение к существующим eslint, prettier, typescript):
     vite@^7.3.1, @vitejs/plugin-react@^5.2.0,
     @types/react, @types/react-dom, @types/node,
     eslint-plugin-react-hooks, eslint-plugin-react-refresh

   scripts:
     "dev": "vite", "build": "tsc -b && vite build", "preview": "vite preview"
   ```

2. **`frontend/vite.config.ts`**:
   ```ts
   import { defineConfig } from "vite";
   import react from "@vitejs/plugin-react";
   import tailwindcss from "@tailwindcss/vite";
   import path from "path";

   export default defineConfig({
     plugins: [react(), tailwindcss()],
     resolve: {
       alias: {
         "@": path.resolve(__dirname, "./src"),
       },
     },
   });
   ```

3. **`frontend/tsconfig.json`** — базовый с references на tsconfig.app.json и tsconfig.node.json.

4. **`frontend/tsconfig.app.json`** — strict mode, JSX react-jsx, path alias `@/*` → `./src/*`, include: `src`.

5. **`frontend/tsconfig.node.json`** — для vite.config.ts, include: `vite.config.ts`.

6. **`frontend/index.html`** — entry HTML с `<div id="root">` и `<script type="module" src="/src/main.tsx">`.

7. **`frontend/src/vite-env.d.ts`** — `/// <reference types="vite/client" />`.

8. **`npm install`** — установить все добавленные зависимости. Нужно выполнить **до Step 3** (shadcn init), т.к. wizard'у нужен рабочий node_modules с React и Tailwind.

```bash
cd frontend && npm install
```

---

### Step 2: Tailwind CSS v4

**Что делаем:** Устанавливаем Tailwind CSS и Vite-плагин. CSS-first конфигурация (без tailwind.config.js).

```bash
cd frontend && npm install tailwindcss @tailwindcss/vite
```

**Файл `frontend/src/index.css`** — создаётся на Step 3 (shadcn init), содержит `@import "tailwindcss"` + shadcn theme variables.

Плагин `tailwindcss()` уже добавлен в `vite.config.ts` (Step 1).

---

### Step 3: shadcn/ui

**Что делаем:** Инициализируем shadcn, корректируем aliases под нашу module structure, добавляем Button и Input.

**3.1. Запустить `npx shadcn@latest init`**

Ожидаемые ответы wizard'а:
- Style: `default` или `radix-nova` (по умолчанию)
- Base color: `neutral`
- CSS file: `src/index.css`
- CSS variables: yes
- TypeScript: yes
- RSC: no (это не Next.js)

Wizard создаст:
- `frontend/components.json`
- `frontend/src/index.css` (с @import "tailwindcss", @import "shadcn/tailwind.css", @theme inline, CSS variables)
- `frontend/src/lib/utils.ts` (cn function)

**3.2. Скорректировать `components.json` aliases:**

```json
{
  "aliases": {
    "components": "@/shared",
    "ui": "@/shared/ui",
    "lib": "@/shared/lib",
    "utils": "@/shared/lib/utils",
    "hooks": "@/hooks"
  }
}
```

**3.3. Перенести файлы** в правильные директории (если shadcn создал в `src/components/ui/` или `src/lib/`):
- `src/lib/utils.ts` → `src/shared/lib/utils.ts`

**3.4. Добавить компоненты:**

```bash
npx shadcn@latest add button input
```

Результат: `frontend/src/shared/ui/button.tsx`, `frontend/src/shared/ui/input.tsx`.

---

### Step 4: React Router v7 — 6 маршрутов

**Что делаем:** Настраиваем роутинг в declarative mode. Все 6 маршрутов из frontend.md со stub-компонентами.

**Файл `frontend/src/app/router.tsx`** — отдельный файл с конфигурацией маршрутов (как в frontend.md). Экспортирует JSX-дерево `<Routes>`:

```
Routes:
  / → element: <AppLayout>
    index → element: <WelcomePage>
    /projects/:id → element: <ProjectLayout>
      index → element: <ProjectChatsStub>        (default tab = Chats)
      /chats/:cid → element: <ChatStub>
      /sphere → element: <SphereStub>
      /artifacts → element: <ArtifactsStub>
      /artifacts/:aid → element: <ArtifactViewStub>
```

**Файл `frontend/src/App.tsx`** — минимальный: рендерит `<BrowserRouter>` и импортирует `<AppRoutes />` из `router.tsx`.

**Маршруты (из frontend.md):**

| Маршрут | Stub-компонент | Расположение |
|---------|---------------|-------------|
| `/` | `WelcomePage` | `src/app/components/WelcomePage.tsx` |
| `/projects/:id` | `ProjectLayout` (layout) + `ProjectChatsStub` (index) | `src/app/layouts/ProjectLayout.tsx` + `src/features/projects/components/ProjectChatsStub.tsx` |
| `/projects/:id/chats/:cid` | `ChatStub` | `src/features/chat/components/ChatStub.tsx` |
| `/projects/:id/sphere` | `SphereStub` | `src/features/sphere/components/SphereStub.tsx` |
| `/projects/:id/artifacts` | `ArtifactsStub` | `src/features/artifacts/components/ArtifactsStub.tsx` |
| `/projects/:id/artifacts/:aid` | `ArtifactViewStub` | `src/features/artifacts/components/ArtifactViewStub.tsx` |

Каждый stub: React-компонент с заголовком страницы и текущим URL (через `useParams`), минимальный Tailwind-стилинг для визуальной верификации.

---

### Step 5: QueryClientProvider + providers

**Файл `frontend/src/app/providers/QueryProvider.tsx`:**

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
const queryClient = new QueryClient();
// Обёртка с QueryClientProvider
```

**Файл `frontend/src/app/providers/index.tsx`:**

Компонент `Providers` — оборачивает children в QueryClientProvider (расширяется в будущих итерациях).

Используется в `main.tsx`:
```tsx
import { Providers } from "./app/providers";
// <Providers><App /></Providers>
```

---

### Step 6: AppLayout

**Файл `frontend/src/app/layouts/AppLayout.tsx`:**

- Sidebar-заглушка (фиксированная боковая панель с текстом "Sidebar" и списком-заглушкой)
- Центральная область с `<Outlet />`
- Tailwind-стилизация: flex layout, sidebar фиксированной ширины, центральная область flex-1
- Минимальный визуал для верификации layout

**Файл `frontend/src/app/layouts/ProjectLayout.tsx`:**

- Stub: имя проекта (из useParams), tab-навигация (Chats / Sphere / Artifacts) через NavLink
- `<Outlet />` для дочерних маршрутов
- Минимальный Tailwind-стилинг

---

### Step 7: Welcome page

**Файл `frontend/src/app/components/WelcomePage.tsx`:**

> **Осознанное решение:** WelcomePage не описан в module structure frontend.md (не является feature). Размещаем в `src/app/components/` как часть app shell — это не бизнес-фича, а экран-заглушка корневого маршрута.

- Welcome-текст / placeholder
- Без input (создание чата только из контекста проекта)
- Минимальная стилизация: центрирование, заголовок, описание
- shadcn/ui Button для визуальной верификации рендеринга

---

### Step 8: ESLint update for React

**Файл `frontend/eslint.config.mjs`** — добавить React-специфичные плагины:

```js
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";

// Добавить в конфиг:
// reactHooks.configs["recommended-latest"]
// reactRefresh с правилом react-refresh/only-export-components: warn
```

Сохраняем существующую конфигурацию (typescript-eslint, eslint-config-prettier), дополняем React-правилами.

---

### Step 9: Makefile update

**Файл `Makefile`** — обновить `dev-fe`:

```makefile
dev-fe:  ## Run frontend dev server
	cd frontend && npx vite
```

---

## Итоговая структура файлов (feat-001)

```
frontend/
├── index.html                          NEW
├── vite.config.ts                      NEW
├── tsconfig.json                       NEW
├── tsconfig.app.json                   NEW
├── tsconfig.node.json                  NEW
├── components.json                     NEW (shadcn)
├── package.json                        MODIFIED
├── package-lock.json                   MODIFIED
├── eslint.config.mjs                   MODIFIED
│
├── src/
│   ├── main.tsx                        NEW — entry point
│   ├── App.tsx                         NEW — BrowserRouter + AppRoutes
│   ├── index.css                       NEW (shadcn init) — Tailwind + theme
│   ├── vite-env.d.ts                   NEW
│   │
│   ├── app/
│   │   ├── router.tsx                  NEW — Routes configuration
│   │   ├── layouts/
│   │   │   ├── AppLayout.tsx           NEW — sidebar stub + Outlet
│   │   │   └── ProjectLayout.tsx       NEW — project name + tabs + Outlet
│   │   ├── providers/
│   │   │   ├── QueryProvider.tsx       NEW — QueryClientProvider
│   │   │   └── index.tsx               NEW — Providers wrapper
│   │   └── components/
│   │       └── WelcomePage.tsx         NEW — welcome screen
│   │
│   ├── features/
│   │   ├── projects/
│   │   │   └── components/
│   │   │       └── ProjectChatsStub.tsx    NEW — stub
│   │   ├── chat/
│   │   │   └── components/
│   │   │       └── ChatStub.tsx            NEW — stub
│   │   ├── sphere/
│   │   │   └── components/
│   │   │       └── SphereStub.tsx          NEW — stub
│   │   └── artifacts/
│   │       └── components/
│   │           ├── ArtifactsStub.tsx       NEW — stub
│   │           └── ArtifactViewStub.tsx    NEW — stub
│   │
│   └── shared/
│       ├── ui/
│       │   ├── button.tsx              NEW (shadcn add)
│       │   └── input.tsx               NEW (shadcn add)
│       └── lib/
│           └── utils.ts                NEW (shadcn init, relocated)

Makefile                                MODIFIED — dev-fe command
```

## Верификация

После реализации проверить все критерии приёмки:

1. **`make dev-fe`** — запускает Vite dev server, приложение открывается в браузере
2. **Навигация** — переход между всеми 6 маршрутами:
   - `/` → WelcomePage
   - `/projects/test-id` → ProjectLayout с табами
   - `/projects/test-id/chats/chat-id` → ChatStub
   - `/projects/test-id/sphere` → SphereStub
   - `/projects/test-id/artifacts` → ArtifactsStub
   - `/projects/test-id/artifacts/art-id` → ArtifactViewStub
3. **Tailwind** — классы применяются (визуально: стили видны)
4. **shadcn/ui** — Button рендерится корректно на WelcomePage
5. **`make lint-fe`** — ESLint проходит без ошибок
6. **`make format-fe`** — Prettier проходит без ошибок
7. **TypeScript** — `cd frontend && npx tsc -b` без ошибок (strict mode)

## Финальный шаг

Дождаться ревью и обратной связи от архитектора перед коммитом и пушем.

---

## Отклонения от frontend.md

| Что | frontend.md | Реализация | Причина |
|-----|------------|------------|---------|
| CSS-файл | `frontend/tailwind.css` (root) | `frontend/src/index.css` | Решение архитектора: стандартная Vite-конвенция |
| WelcomePage | Не описан в module structure | `src/app/components/WelcomePage.tsx` | Не feature, а часть app shell |

При завершении итерации — обновить frontend.md (расположение CSS файла).
