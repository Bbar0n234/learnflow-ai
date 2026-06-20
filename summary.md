# feat-004 Implementation Summary

## T4a — Каркас (layout shell)

### Что сделано

Приведена геометрия каркаса к числам хэндоффа «Чернила / Электрик». Scope: только layout-каркас и структура sidebar; контент экранов не рестайлился.

### Геометрия

**Sidebar — 252px**

- `AppLayout.tsx`: `aside` c `sidebarOpen ? "w-[252px]" : "w-0"` (было `w-64` = 256px).
- `Sidebar.tsx`: внутренний `div` с `w-[252px]` (был `w-64`).
- Фон `--sidebar` и граница справа (`border-r border-border`) присутствовали до T4a, сохранены.

**Sidebar header — 56px**

Заменён `py-3` (переменная высота) на `h-[56px]` (фиксированная, в диапазоне 52–58px). Класс `items-center` сохранён.

**ProjectLayout header — 56px**

Реструктурирован с вертикальной раскладки (h1 + nav стопкой, ~90px) на горизонтальную (`flex h-[56px] items-center gap-6`). Проект-имя и табы теперь в одну строку — геометрически укладываются в 52–58px. Рестайл шрифта, цвет активного таба и sphere-chip — T4e.

**Центр-колонка — CSS переменная --content-max-w**

В `frontend/src/index.css` добавлены:
- `--content-max-w: 680px` внутри `:root {}` (рядом с другими бренд-токенами).
- Правило `.studio-open { --content-max-w: 520px; }` — T6 навесит этот класс на контейнер чата когда студия-панель открыта.
- Использование в компонентах: `max-w-[var(--content-max-w)]` или `style={{ maxWidth: "var(--content-max-w)" }}`. T4b применит это в ChatView.

**Правая панель**

Не применимо к текущим layout-файлам. Студия-панель (318/470px) будет добавлена в T6 прямо в ChatView, минуя AppLayout/ProjectLayout.

### Структура sidebar

- Кнопка «+ Новый чат»: `variant="ghost"` -> `variant="default"` (primary), `w-full justify-start`.
- Кнопка «Новый проект»: `variant="ghost"` -> `variant="outline"`, `w-full justify-start`.
- Текст кнопок русифицирован по хэндоффу.
- Wordmark короткая форма, переключатель темы, sidebar-vignette — сохранены без изменений (T2/T3).

**Точки-статусы проектов**

В `ProjectCard.tsx` иконка `FolderOpen` заменена на `<span className="h-2 w-2 shrink-0 rounded-full bg-brand-lavender" />`. Цвет точки (`--brand-lavender` = сирень) соответствует «неактивным/нейтральным» маркерам по хэндоффу. Логика смены цвета по статусу сферы появится когда бэкенд добавит поле статуса.

### Качество (L0)

- `make check-fe` (tsc + ESLint + Prettier): зелёный.
- `tsc -b && vite build`: зелёный (предупреждение chunk size — pre-existing, не от T4a).
- Hardcoded hex/цвета Tailwind palette в тронутых файлах: отсутствуют (grep чист).
- Компоненты `shared/ui` руками не правлены.
