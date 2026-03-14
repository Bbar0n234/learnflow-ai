# Post-Implementation Summary: feat-006 — Sphere + Artifacts

## Результат

Все критерии приёмки выполнены:
- Таб Sphere рендерит Knowledge Sphere из mock-данных (proj-1: Distributed Systems, proj-2: ML Fundamentals с LaTeX)
- Переключение Viewer → Editor → Save → Viewer работает, mock-персистентность обеспечена
- Cancel возвращает в Viewer без изменений
- Пустой sphere — placeholder с подсказкой
- Таб Artifacts показывает список артефактов из mock-данных (иконка, title, type, дата)
- Клик по артефакту → `/projects/:id/artifacts/:aid`, контент рендерится через MarkdownRenderer (таблицы, mermaid, LaTeX)
- Кнопки скачивания (MD/PDF) формируют корректный URL: `http://localhost:8000/projects/:id/artifacts/:aid/download?format=md|pdf`
- Все хуки типизированы, ESLint — 0 ошибок, TypeScript strict — 0 ошибок

Верификация: 13 из 14 кейсов — автоматическая через Claude in Chrome, 1 кейс (window.open URL) — ручная архитектором. Все 14/14 PASS.

## Отклонения от плана

### SphereView — контейнер не в спецификации

**Что:** frontend.md описывает SphereViewer и SphereEditor, но не контейнер для toggle-логики. Добавлен SphereView по паттерну ChatView (контейнер + дочерние компоненты). Это было явно указано в плане как ожидаемое отклонение.

**Вывод:** frontend.md актуализирован — SphereView добавлен в Module Structure.

### Button без asChild — buttonVariants для Link

**Что:** план предполагал `<Button asChild><Link>` для кнопки "Back to artifacts". shadcn/ui в проекте использует `@base-ui/react/button`, который не поддерживает `asChild`. Решение: `<Link className={buttonVariants({ variant, size })}>`.

**Вывод:** идиоматический подход для base-ui. Остальные кнопки-ссылки в проекте следуют тому же паттерну.

### MOCK_ARTIFACT_DETAILS — привязка к projectId (ревью-fix)

**Что:** исходные mock-данные (из feat-002) использовали flat `Record<artifactId, ArtifactDetail>`, игнорируя `projectId`. Ревью архитектора выявил расхождение с контрактом `GET /projects/:id/artifacts/:aid` — артефакт другого проекта мог быть доступен по чужому projectId. Исправлено: структура изменена на `Record<projectId, Record<artifactId, ArtifactDetail>>`.

**Вывод:** mock-данные теперь корректно эмулируют project-scoped доступ к артефактам.

## Созданные файлы

| Файл | Назначение |
|------|-----------|
| `frontend/src/features/sphere/hooks/useSphere.ts` | Query: данные sphere проекта |
| `frontend/src/features/sphere/hooks/useUpdateSphere.ts` | Mutation: обновление sphere + инвалидация |
| `frontend/src/features/sphere/components/SphereView.tsx` | Контейнер: toggle viewer/editor, loading/error |
| `frontend/src/features/sphere/components/SphereViewer.tsx` | Отображение sphere (MarkdownRenderer + Edit button) |
| `frontend/src/features/sphere/components/SphereEditor.tsx` | Редактирование sphere (Textarea + Save/Cancel) |
| `frontend/src/features/artifacts/hooks/useArtifacts.ts` | Query: список артефактов проекта |
| `frontend/src/features/artifacts/hooks/useArtifact.ts` | Query: детали артефакта |
| `frontend/src/features/artifacts/components/ArtifactList.tsx` | Список артефактов (иконка, title, type, дата) |
| `frontend/src/features/artifacts/components/ArtifactView.tsx` | Просмотр артефакта (MarkdownRenderer + Download MD/PDF + Back) |

## Модифицированные файлы

| Файл | Изменение |
|------|-----------|
| `frontend/src/shared/api/sphere.ts` | updateSphere мутирует MOCK_SPHERE (mock-персистентность) |
| `frontend/src/shared/api/artifacts.ts` | + art-2 detail, nested MOCK_ARTIFACT_DETAILS по projectId, downloadArtifact → window.open |
| `frontend/src/app/router.tsx` | SphereStub → SphereView, ArtifactsStub → ArtifactList, ArtifactViewStub → ArtifactView |

## Удалённые файлы

| Файл | Причина |
|------|---------|
| `frontend/src/features/sphere/components/SphereStub.tsx` | Заменён на SphereView |
| `frontend/src/features/artifacts/components/ArtifactsStub.tsx` | Заменён на ArtifactList |
| `frontend/src/features/artifacts/components/ArtifactViewStub.tsx` | Заменён на ArtifactView |

## Актуализация документации

- **frontend.md** — добавлен `SphereView` в Module Structure (секция `sphere/components/`). Остальная документация актуальна, архитектурных отклонений нет.
