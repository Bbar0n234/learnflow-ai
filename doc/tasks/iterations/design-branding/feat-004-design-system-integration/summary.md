# Summary: feat-004 — Design-system integration

Сквозное состояние итерации. Каждая фаза дописывает свой раздел.

---

## T1 — Фундамент: токены, шрифты, тема, переключатель ✅

**Токены** (`frontend/src/index.css`): нейтральная shadcn-палитра заменена на «Электрик» по таблицам хэндоффа (hex-приоритет). Light: `--background #FAF7F1`, `--foreground #2E2A24`, `--primary #7434F4`, лаванда `#EFE7FE`, `--sidebar #F1EDE3`. Dark: `--background #181420`, крем `#EDE8E2`, fill-акцент `#8A5CF6`, rgba-лаванда. `--radius: 0.7rem`. Добавлены `--brand-lavender`, `--bubble-user` в обеих темах; в `@theme inline` — `--font-serif`, `--font-mono`, `--color-brand-lavender`, `--color-bubble-user`.

**Шрифты**: удалён `@fontsource-variable/geist`; добавлены (имена верифицированы по установке):
- `@fontsource/source-serif-4` (5.2.9), веса 600/700 → `--font-serif` (заголовки/имена сущностей)
- `@fontsource/instrument-sans` (5.2.8), 400/500/600/700 → `--font-sans` (UI/body)
- `@fontsource/ibm-plex-mono` (5.2.7), 400/500 → `--font-mono` (версии/таймкоды)

**Theme-store** (`frontend/src/stores/theme-store.ts`): Zustand + persist (ключ `learnflow-theme`), `applyTheme()` вешает/снимает `.dark` на `document.documentElement`. Инициализация: localStorage → иначе `prefers-color-scheme`. No-FOUC: инлайн-скрипт в `index.html <head>` применяет `.dark` до первого рендера (читает тот же ключ); ранний импорт стора в `main.tsx`.

**Переключатель темы**: user-строка sidebar (`Sidebar.tsx` footer), иконка Moon/Sun (lucide) рядом с Settings/Logout.

**Рефактор захардкоженных цветов**: `ErrorBoundary.tsx` — инлайн-hex → токен-классы (`bg-background`, `text-foreground`, `text-muted-foreground`, `border-border`, `bg-card`, `bg-muted`). `pages/security/ui/*` (SeverityBadge, StatusBadge, SecurityRules, SecurityEvents, SecurityAlerts, RuleForm) — палитра `red/green/blue/yellow-*` → семантические токены (ошибки → `destructive`, info/new → `accent`/лаванда, warning → `muted`, success → `muted/60`).

**Сопутствующее**: `frontend/.prettierignore` (исключает `dist/`, `node_modules/`).

**Принятые решения:**
1. Dark `--primary` = `#8A5CF6` (button fill); текстовый акцент `#B194FF` применяется точечно в компонентах на T4.
2. Точки шрифтов/переключателя — по рекомендации плана.

**Verification:** `make check-fe` GREEN (tsc + ESLint + Prettier), `tsc -b && vite build` GREEN. Полное визуальное 🔍-подтверждение {T1.1}–{T1.6} — на VISUAL_REVIEW.

**Зона для последующих фаз:** dark текстовый акцент `#B194FF` — применять в рестайле компонентов (T4). ErrorBoundary получит брендовый вид с иллюстрацией error-state в T5/T3.

---

## T2 — Бренд-примитивы: wordmark K5, знак, Сфера-орб, фавиконы ✅

**Новые компоненты** (`frontend/src/shared/ui/`):

- **`SphereOrb.tsx`** — параметризованный орб (prop `size`, `showRings`, `showSparks`). Градиент берётся из CSS-переменных `--orb-gradient` / `--orb-shadow` (добавлены в `index.css` для light и dark), что позволяет компоненту реагировать на тему без подписки на theme-store — просто CSS custom properties. При `size >= 100` добавляются 2 концентрических кольца (`--orb-ring-1/2`). При `size >= 30` — до 3 искр-ромбов (brand-lavender / primary / primary-foreground); позиции вычисляются геометрически по углу от вертикали. Это **единственное место с градиентом** в системе.

- **`BrandMark.tsx`** — знак для аватара агента: `SphereOrb` (size−6) в круглом контейнере с border 1.5px `--brand-lavender`. `showRings=false`, `showSparks=false` — кольцо само по себе выступает обрамлением.

- **`Wordmark.tsx`** — логотип K5. Сборка через `inline-flex` + три части:
  - `OrbLetter()`: контейнер 0.8em × 0.8em, орб-круг (`--orb-gradient`), эллиптическое орбитальное кольцо (`rotate(-18deg)`, 1.5px, `color-mix(var(--ring) 65%)`), искра-ромб 0.2em у правого верхнего края (`--brand-lavender`). Все размеры в `em` — масштабируется с родительским font-size.
  - `AiWithCircle()`: текст «AI» цветом `var(--ring)` (= `--primary` #7434F4 в light, #B194FF в dark — сменяется автоматически), два эллипса-бордера `rotate(-9deg/+8deg)` с opacity 75%/35% через `color-mix`.
  - Prop `short` убирает «AI» и кружок (для sidebar/шапок).

**SVG-фавиконы** (`frontend/public/`):
- `favicon.svg` (16×16): чистый орб с radialGradient; используется браузером как основной favicon.
- `favicon-32x32.svg` (32×32): орб + diamond-искра у правого верхнего края.
- `apple-touch-icon.svg` (180×180): орб на тёплом фоне `#FAF7F1`, два спарка; скруглённые углы `rx=38`.

**Подключение** (`frontend/index.html`): добавлены `<link rel="icon">` (svg/svg-32/apple-touch) после `<title>`, перед no-FOUC скриптом. Существующий инлайн-скрипт не затронут.

**Замена текстового логотипа**:
- `Sidebar.tsx:55` — `<h2>LearnFlowAI</h2>` → `<h2><Wordmark short /></h2>` (сохранён класс `text-sidebar-foreground` на родителе; `font-bold` перенесён внутрь Wordmark).
- `WelcomePage.tsx:5` — `<h1 font-bold>LearnFlowAI</h1>` → `<h1><Wordmark /></h1>`.

**Принятые решения:**
1. Цвет «AI» и кружок используют `var(--ring)` (не `var(--primary)`): в light это одно и то же (#7434F4), в dark `--ring: #B194FF` — точно соответствует спеке «акцентные элементы #B194FF» для dark.
2. Орбитальное кольцо в wordmark — эллипс 0.8em+10px × 0.56em+7px (≈0.7× от ширины), что визуально передаёт перспективу наклонённой орбиты.
3. CSS-переменные для градиента вместо JS-чтения темы: чище, не нужна зависимость от theme-store в примитивах.
4. `inset` в AiWithCircle: CSS-свойство `inset` поддерживается во всех целевых браузерах; Prettier и tsc прошли без предупреждений.
5. `public/` директория создана (ранее отсутствовала).

**Verification:** `make check-fe` GREEN (tsc + ESLint + Prettier), `tsc -b && vite build` GREEN. Статические грепы: «LearnFlowAI» отсутствует в Sidebar/WelcomePage {T2.2} ✓; `gradient` не в фоне обычных UI-элементов {T2.3} ✓; фавиконы прилинкованы {T2.4} ✓; shadcn-примитивы не тронуты {L0.3} ✓. Визуальное 🔍-подтверждение {T2.1}–{T2.4} — на VISUAL_REVIEW.

---

## T3 — Ассет-пайплайн + иллюстрации ✅

**Ассеты** (`frontend/src/shared/assets/illustrations/{light,dark}/`): скопированы 6 сцен × 2 темы из `doc/.../feat-001-poc/refs/illustrations/candidates/transparent/soft-balanced/{light,dark}/`. Имена сохранены: `welcome-hero`, `sidebar-vignette`, `empty-chats`, `empty-sphere`, `empty-artifacts`, `error-state`.

**Централизованная карта** (`frontend/src/shared/assets/illustrations/index.ts`): единственная точка импорта PNG-ассетов. Типы:

```typescript
type Scene = "welcome-hero" | "sidebar-vignette" | "empty-chats" | "empty-sphere" | "empty-artifacts" | "error-state";
type IllustrationTheme = "light" | "dark";

function getIllustration(scene: Scene, theme: IllustrationTheme): string;
```

Все 12 PNG импортируются статически (Vite resolves to asset URL) и хранятся в объекте `Record<IllustrationTheme, Record<Scene, string>>`. `getIllustration` — единственный публичный API; компоненты не импортируют PNG напрямую.

**Обёртка** (`frontend/src/shared/ui/Illustration.tsx`): принимает `{ scene: Scene; alt: string; className?: string }`. Читает тему из `useThemeStore` (T1), вызывает `getIllustration(scene, theme)`, рендерит `<img>`. Переключение light↔dark происходит реактивно вместе с темой.

**Врезки (5 сцен)**:
- `welcome-hero` → `pages/welcome/ui/WelcomePage.tsx`: под подзаголовком, `max-w-[460px]`.
- `sidebar-vignette` → `app/components/Sidebar.tsx`: между scrollable-областью проектов/чатов и user-footer; `pointer-events-none`, full-width.
- `empty-chats` → `pages/project-chats/ui/ChatList.tsx`: обёртка пустого state, `max-w-[280px]`.
- `empty-sphere` → `pages/sphere/ui/SphereViewer.tsx`: обёртка пустого state, `max-w-[280px]`.
- `empty-artifacts` → `pages/artifacts/ui/ArtifactList.tsx`: обёртка пустого state, `max-w-[280px]`.
- `error-state` — не тронут; потребляется T5 в ErrorBoundary.

**Отклонения:** нет. Рестайл экранов не выполнялся (T4). ErrorBoundary не тронут (T5).

**Принятые решения:**
1. Статические `import` PNG (не `import.meta.glob`) — детерминированный бандл, все 12 файлов всегда включены; объём приемлем (cutout RGBA).
2. `sidebar-vignette` рендерится всегда (не только при пустом state) — декоративный низ sidebar, `pointer-events-none`.
3. `alt=""` для sidebar-vignette (декоративный ассет); осмысленный `alt` у остальных.

**Verification:** `make check-fe` GREEN (tsc + ESLint + Prettier), `tsc -b && vite build` GREEN. Грепы: {T3.1} 6×6 файлов ✓; {T3.2} нет прямых PNG-импортов в `pages/` и `app/` ✓; {T3.4} врезки в 5 файлах ✓. Визуальное 🔍 {T3.3} (тема переключает иллюстрации) — на VISUAL_REVIEW.

---

## T5 — Error UX: sonner-тосты + ErrorBoundary ✅

**Адаптация `sonner.tsx`** — **санкционированное отклонение от {L0.3}:** shadcn CLI сгенерировал файл с `import { useTheme } from "next-themes"` (Next.js-специфичный). Поскольку проект работает на Vite/React без `next-themes ThemeProvider`, источник темы заменён на `useThemeStore` (T1, Zustand): `const theme = useThemeStore((s) => s.theme)`. Иконки, CSS-переменные тоста (`--normal-bg`, `--normal-text`, `--normal-border`, `--border-radius`) и `toastOptions` — не тронуты. `next-themes` остаётся в `package.json` (добавлен CI при генерации), но больше не импортируется — при следующей чистке зависимостей можно удалить.

**Монтаж `<Toaster/>`** (`frontend/src/app/providers/index.tsx`): добавлен как sibling к `{children}` внутри `<QueryProvider>` — единственное место монтажа в дереве приложения. Тема тоста следует за `useThemeStore`, тостер рендерится поверх всего контента через портал sonner.

**QueryClient onError → тост** (`frontend/src/app/providers/QueryProvider.tsx`): в `QueryCache.onError` и `MutationCache.onError` добавлен `toast.error(message)` с сообщением из `getApiErrorMessage(error)` (переиспользует существующий парсер `shared/lib/api-error.ts`). Логирование через `logger.error` сохранено. 4xx-политика без ретраев (существующий `shouldRetryQuery`) не затронута.

**ErrorBoundary — брендовый error-state** (`frontend/src/app/components/ErrorBoundary.tsx`): добавлена `<Illustration scene="error-state" alt="Иллюстрация ошибки" className="h-48 w-auto select-none" />` из T3. Токены оставлены как есть (были перенесены с инлайн-hex в T1). Класс `gap-4` увеличен до `gap-8` для воздушности; текст кнопки сохранён; описание ошибки расширено уточнением «Попробуйте обновить страницу».

**Error-bars** — существующие инлайн-сообщения об ошибках (ArtifactView, ChatView, SphereView, ProjectList, AuthGate, CreateProjectModal, ProjectActions, CustomInstructionsSection, SphereEditor, ChatList, ArtifactList, MessageList, SecurityRules, SecurityEvents, SecurityAlerts, RuleForm, MCPServerForm) уже переведены на токены `destructive` в T1 — дополнительных изменений не требуется.

**Принятые решения:**
1. `toast` импортируется из `"sonner"` напрямую (пакет), не из обёртки `@/shared/ui/sonner` — обёртка экспортирует только `Toaster` (компонент монтажа); `toast` — это сам API sonner, импортируемый везде по-прямой.
2. `<Toaster>` размещён в `providers/index.tsx`, а не в `App.tsx` — провайдерный слой; `<ErrorBoundary>` находится ниже в `App.tsx` и потому всегда может показывать тосты (тостер уже смонтирован выше).
3. Класс ErrorBoundary — не функциональный компонент, поэтому `useThemeStore` нельзя вызвать напрямую; `<Illustration>` — функциональный компонент, который сам читает стор — это корректно (хуки вызываются в контексте Illustration, не ErrorBoundary).

**Verification:** `make check-fe` GREEN (tsc + ESLint + Prettier — после `prettier --write sonner.tsx`), `tsc -b && vite build` GREEN. Статические проверки: {T5.1} `toast.error` в обоих `onError`, `shouldRetryQuery` не тронут ✓; {T5.3} `<Illustration scene="error-state">` в ErrorBoundary ✓; {L0.4} нет hex в тронутых файлах ✓; `next-themes` не импортируется ✓. Полное 🔍 {T5.1}–{T5.3} — на VISUAL_REVIEW (эмуляция 4xx/5xx).

_Примечание: `next-themes` удалён из зависимостей оркестратором при коммите T5._

---

## T4a — Каркас (layout shell) ✅

**Геометрия по хэндоффу:** Sidebar 252px (`AppLayout.tsx` aside `w-[252px]`, было `w-64`; `Sidebar.tsx` внутренний div `w-[252px]`; фон `--sidebar` + граница справа сохранены). Sidebar header 56px (`py-3` → `h-[56px]`). `ProjectLayout` header реструктурирован с вертикального (~90px) на горизонтальный `flex h-[56px] items-center gap-6` (имя проекта + табы inline; serif/цвет таба/sphere-chip — T4e).

**Центр-колонка:** в `index.css` добавлены `--content-max-w: 680px` (`:root`) и `.studio-open { --content-max-w: 520px; }` (T6 навесит класс при открытой студии).

**Структура sidebar:** «+ Новый чат» → `variant="default"` (primary) `w-full`; «Новый проект» → `variant="outline"` `w-full`; тексты русифицированы. Wordmark/переключатель/vignette (T1–T3) сохранены. `ProjectCard.tsx`: иконка `FolderOpen` → точка-статус `bg-brand-lavender` (динамика по статусу сферы — когда бэкенд добавит поле).

**Verification:** `make check-fe` + `tsc -b && vite build` GREEN. {T4.1} статически: sidebar 252px, центр max≈680px, шапки 56px. Полное 🔍 (`getComputedStyle`) — на VISUAL_REVIEW.

---

## T4b — Главный экран (чат) ✅

Рестайл ленты и инпут-бара по макету «Главный экран» (`frontend/src/pages/chat/ui/*` + токен тени в `index.css`). Логика стрима/отправки/контракты не тронуты.

- **MessageItem**: bubble пользователя `bg-bubble-user`, скошенный угол `rounded-[14px_4px_14px_14px]` (dark — `+ border-border`); ответ агента плоским текстом без bubble (markdown через `MarkdownRenderer`).
- **MessageList**: центр-колонка `max-width: var(--content-max-w)`; стрим-контейнер тоже плоский.
- **ToolIndicator**: лавандовый чип `bg-secondary rounded-full` + точка-маркер (spinner убран).
- **ReviewIndicator**: акцентный прямоугольник `h-4 w-2 bg-primary` + текст.
- **ArtifactCard**: `border-left: 3px solid var(--ring)` на card (обычная рамка убрана).
- **FeedbackButtons**: метки «Полезно / Не то / Перегенерировать» («Перегенерировать» — визуальная заготовка, API не вызывает, {L0.5}).
- **ChatInput**: card + тень через новый токен `--shadow-input: 0 2px 10px rgba(80,70,50,0.06)`; send/cancel — круг 34px `rounded-full` (primary / destructive); textarea прозрачная внутри card.
- **ChatHeader**: `h-[56px]`, serif-название, два чипа (Модель/Инструменты) открывают Dialog (инлайн-ModelSelector перенесён в Dialog), кнопка ← назад.

**Verification:** `make check-fe` + `tsc -b && vite build` GREEN. Hardcoded-цветов в тронутых .tsx нет; shadcn-примитивы не правлены; {L0.5} соблюдён. Полное 🔍 (на seed-данных vs макет) — на VISUAL_REVIEW.
