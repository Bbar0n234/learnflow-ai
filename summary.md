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

---

## T4b — Главный экран (чат)

### Что сделано

Рестайл ленты чата и инпут-бара по хэндоффу «Главный экран». Затронуты файлы `frontend/src/pages/chat/ui/*` и `frontend/src/index.css` (токен тени).

### Компоненты

**MessageItem.tsx**

- Bubble пользователя: `bg-bubble-user` (токен `--bubble-user`: `#ede7da` light / `#262031` dark), `rounded-[14px_4px_14px_14px]` — скошенный верхний-правый угол (14px остальные, 4px top-right). В dark добавлен `border-border` (хэндофф: `#262031 + border #322a44`).
- Ответ агента: плоский текст без bubble-обёртки (`w-full text-foreground`), markdown через существующий `MarkdownRenderer`.
- Redacted-сообщение обрабатывается в обеих ветках (user/agent).

**MessageList.tsx**

- Центр-колонка переключена на `style={{ maxWidth: "var(--content-max-w)" }}` (T4a токен 680px / 520px при открытой студии).
- Streaming-контейнер (`isStreaming`) также стал плоским — убраны `rounded-lg bg-muted px-4 py-3`, оставлен только `w-full text-foreground`.

**ToolIndicator.tsx**

- Spinner `Loader2` заменён на лавандовый чип: `bg-secondary px-3 py-1 rounded-full` + точка-маркер `h-1.5 w-1.5 rounded-full bg-current opacity-60` внутри.
- Текст инструмента рядом с точкой.

**ReviewIndicator.tsx**

- Иконка `ShieldCheck` заменена на акцентный прямоугольник 8×16px (`h-4 w-2 rounded-[2px] bg-primary`) + текст «Проверяем ответ...».

**ArtifactCard.tsx**

- Убрана рамка `border border-border`, добавлена `borderLeft: "3px solid var(--ring)"` (акцентный левый бордер).
- Фон `bg-card` сохранён; hover переключается на `bg-accent`.

**FeedbackButtons.tsx**

- Добавлены текстовые метки: «Полезно» (thumbs-up), «Не то» (thumbs-down), «Перегенерировать» (RotateCcw).
- «Перегенерировать» — визуальная заготовка (`onClick={() => {}}`), API-вызов не производится ({L0.5}).

**ChatInput.tsx**

- Убран `border-t border-border`, wrapper стал `card + shadow` через `bg-card rounded-[var(--radius)]` + `boxShadow: "var(--shadow-input)"`.
- Ширина ограничена `maxWidth: "var(--content-max-w)"`.
- Send-кнопка — нативный `<button>` `h-[34px] w-[34px] rounded-full bg-primary text-primary-foreground` (34px круг primary).
- Cancel-кнопка — аналогично, `bg-destructive`, 34px круг.
- Textarea: `border-0 shadow-none focus-visible:ring-0` для прозрачного вида внутри card.
- Placeholder русифицирован: «Сообщение...».

**ChatHeader.tsx**

- Высота зафиксирована `h-[56px]`, вертикально центрировано (`flex flex-col justify-center`).
- Строка 1: кнопка ← {project.name} — `text-xs text-muted-foreground`.
- Строка 2: название чата `font-serif text-[17px] font-semibold tracking-tight` (title из `useChat`, TanStack Query дедуплицирует запрос).
- Справа в строке 2: два чипа (`bg-secondary rounded-full text-xs`) — «Модель» (Bot icon) и «Инструменты» (Settings2 icon). Каждый открывает Dialog с ModelSelector / MCPServersSection.
- Исходный инлайн-ModelSelector (w-64, с label) перенесён в Dialog → header стал компактным.

### Новый токен

`--shadow-input: 0 2px 10px rgba(80, 70, 50, 0.06)` добавлен в `:root {}` в `index.css`. Используется в ChatInput через `var(--shadow-input)`.

### Качество (L0)

- `make check-fe` (tsc + ESLint + Prettier): **зелёный**.
- `vite build`: **зелёный** (chunk size warning — pre-existing).
- Hardcoded hex/Tailwind-палитра в тронутых .tsx: отсутствуют (grep чист).
- `shared/ui` компоненты не правлены.
- `{L0.5}` соблюдён: «Перегенерировать» не вызывает API.
