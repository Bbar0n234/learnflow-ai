# Post-Implementation Summary: feat-003 — Sidebar + Projects

## Результат

Все критерии приёмки выполнены:
- Sidebar отображает список проектов из mock-данных (3 проекта)
- Клик по проекту в sidebar навигирует на `/projects/:id`, заголовок — имя проекта
- CreateProjectModal создаёт проект (mock), проект появляется в sidebar, навигация на страницу нового проекта
- ProjectLayout рендерит табы (Chats / Sphere / Artifacts), переключение работает через NavLink
- Recent chats отображаются в sidebar с project_name, клик навигирует в чат
- Sidebar складывается/разворачивается через ui-store toggle (CSS-based: w-0/w-64 + transition)
- New Chat кнопка disabled вне контекста проекта, enabled на `/projects/:id`
- TypeScript strict — 0 ошибок, ESLint — 0 ошибок

## Отклонения от плана

### base-ui Dialog: controlled mode без conditional rendering

**Что:** план не специфицировал паттерн управления open/close для Dialog. Первая реализация использовала conditional rendering (`if (!open) return null` + `<Dialog open>`), что сломало lifecycle base-ui Dialog — exit-анимации не завершались, Portal оставался в DOM.

**Корень проблемы:** base-ui Dialog (v1.3.0, @base-ui/react) при conditional rendering не видит переход `open={true}` → `open={false}` — компонент unmount происходит раньше, чем store синхронизирует `openProp`. Portal/Backdrop cleanup зависит от `element.getAnimations()`, который требует, чтобы элемент оставался в DOM для завершения exit-анимации.

**Решение:** чистый controlled mode — `<Dialog open={open} onOpenChange={onOpenChange}>` без conditional rendering. Dialog всегда mounted, base-ui управляет Portal visibility через `open` prop и exit-анимации (`data-closed:animate-out`).

**Вывод:** с base-ui (в отличие от Radix) не использовать conditional rendering для Dialog. Компонент должен быть always-mounted, visibility управляется через `open` prop.

### getProject() fallback

**Что:** исходная mock-реализация из feat-002 возвращала `mockProjects[0]` при несуществующем ID. Это маскировало навигацию на несуществующие проекты.

**Решение:** заменено на `throw new Error()`. useQuery обрабатывает ошибку через `isError` state.

### New Chat — no-op по дизайну

**Что:** кнопка New Chat присутствует в sidebar, `disabled` вне контекста проекта, enabled на `/projects/:id`. При клике — no-op. Создание чата (useCreateChat) отнесено к feat-004 по таск-листу.

## Созданные файлы

| Файл | Назначение |
|------|-----------|
| `frontend/src/features/projects/hooks/useProjects.ts` | Query: список проектов |
| `frontend/src/features/projects/hooks/useProject.ts` | Query: один проект по ID |
| `frontend/src/features/projects/hooks/useCreateProject.ts` | Mutation: создание проекта + инвалидация |
| `frontend/src/features/projects/hooks/useUpdateProject.ts` | Mutation: обновление проекта + инвалидация |
| `frontend/src/features/projects/hooks/useDeleteProject.ts` | Mutation: удаление проекта + инвалидация |
| `frontend/src/features/chat/hooks/useRecentChats.ts` | Query: recent chats |
| `frontend/src/features/projects/components/ProjectCard.tsx` | NavLink-карточка проекта с active-state |
| `frontend/src/features/projects/components/ProjectList.tsx` | Список проектов (loading/error/empty states) |
| `frontend/src/features/projects/components/CreateProjectModal.tsx` | Dialog: создание проекта с навигацией |
| `frontend/src/app/components/Sidebar.tsx` | Полноценный sidebar (проекты, recents, actions) |

## Модифицированные файлы

| Файл | Изменение |
|------|-----------|
| `frontend/src/shared/api/projects.ts` | Мутабельные моки (createProject pushes, deleteProject removes), getProject throws on missing ID |
| `frontend/src/app/layouts/AppLayout.tsx` | Sidebar компонент + CSS-based toggle (w-0/w-64 + transition), кнопка expand |
| `frontend/src/app/layouts/ProjectLayout.tsx` | useProject хук для имени проекта вместо raw ID |
| `frontend/src/app/components/WelcomePage.tsx` | Убрана мёртвая ссылка на /projects/demo |

## Актуализация документации

Отклонения не влияют на проектную архитектуру. Паттерн base-ui Dialog (controlled, always-mounted) — локальное знание, не требует ADR. Документация в `doc/tech/frontend.md` актуальна, обновление не требуется.
