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

---

## T4c — Welcome ✅

Рестайл `frontend/src/pages/welcome/ui/WelcomePage.tsx`. Элементы T2 (wordmark) и T3 (hero-иллюстрация) сохранены; добавлены: serif-приветствие, CTA, карточки проектов.

**Структура (сверху вниз, центр по вертикали):**

- **Wordmark** — `<Wordmark />` полная форма (из T2), сохранён как `<h1>`.
- **Hero-врезка 460×270** — `<Illustration scene="welcome-hero" … className="h-[270px] max-w-[460px] object-contain" />` (из T3), сохранена.
- **Serif-приветствие** — `<h2>Добро пожаловать</h2>`, `font-serif text-[38px] font-semibold leading-tight text-foreground`.
- **Подзаголовок** — `text-base text-muted-foreground`.
- **CTA** — `<Button size="lg">` (primary, «+ Новый проект») и `<Button variant="outline" size="lg">` («Продолжить …», появляется только при наличии проектов, ведёт на последний по `updated_at`).
- **Карточки проектов** — `flex gap-4`; до 3 штук, сортированных по `updated_at` desc (client-side из `useProjects()`). Каждая карточка: `w-[220px]`, `border border-border bg-card rounded-xl`, мини-`<SphereOrb size={20} />` с `opacity` по «свежести» (`getOrbOpacity`), serif-название `line-clamp-2`. При нулевом списке проектов блок карточек скрыт.

**Вспомогательная функция `getOrbOpacity(updatedAt)`:**

| Давность | Opacity |
|---|---|
| < 1 дня | 1.0 |
| 1–3 дня | 0.8 |
| 3–14 дней | 0.6 |
| > 14 дней | 0.4 |

**Диалог создания проекта** — инлайн в WelcomePage (дублировать `app/components/CreateProjectModal` нельзя: `pages/` не импортирует из `app/` по FSD). Использует `Dialog/Input/Button` из `shared/ui` и `useCreateProject` из `shared/api/projects`.

**Принятые решения:**
1. FSD: диалог инлайн — не импортируем из `app/components/`, чтобы не нарушать направление зависимостей layers.
2. Сортировка по `updated_at` — client-side (API возвращает все проекты за один запрос с limit=200; данные уже в кеше TanStack Query из sidebar).
3. `SphereOrb size=20` — без колец и искр (`showSparks = size >= 30 = false`); чистый mini-орб, как рекомендует docstring компонента.
4. Текст «Продолжить …» без имени проекта — по хэндоффу; имя видно в карточке.

**Verification:** `make check-fe` GREEN (tsc + ESLint + Prettier), `tsc -b && vite build` GREEN. {L0.3} shadcn-примитивы не правлены ✓; {L0.4} нет hex/numeric-цветов в тронутом файле ✓; {L0.5} только существующие endpoints (`/projects`) ✓; wordmark и hero-иллюстрация не сломаны ✓. Полное 🔍 {T4.3} (vs макет) — на VISUAL_REVIEW.

---

## T4d — Сфера + Артефакты (базовый вид группы A) ✅

Рестайл вьюера/редактора сферы и списка/вьюера артефактов. Группа B (rich-редактор, вьюеры slides/image/audio) не тронута.

**Сфера — вьюер (`SphereViewer.tsx`):**
- Заголовок «Сфера знаний» переведён в `font-serif text-lg font-semibold`.
- Кнопка редактирования — `<Button variant="outline" size="sm">` с accent-бордером (`border-ring/60 text-ring hover:bg-accent`).
- Markdown-контент обёрнут в `<div className="sphere-prose max-w-[680px]">` — применяет H-serif и маркеры «—» из нового CSS-блока.
- Empty-state `<Illustration scene="empty-sphere" …>` (T3) сохранён; текст placeholder переведён на русский.

**Сфера — редактор (`SphereEditor.tsx`):**
- Заголовок «Редактировать сферу» в serif, кнопки «Отмена» (outline) / «Сохранить» (primary, sm).
- Textarea обёрнут в `rounded-xl border border-border bg-card` — textarea прозрачная внутри карточки, `border-0 bg-transparent focus-visible:ring-0`.
- Placeholder переведён на русский; семантика без изменений.

**Артефакты — новый сплит-лэйаут (`ArtifactsPage.tsx`, новый):**
- Обёртка `<div className="flex h-full">` с `<aside className="w-[318px] shrink-0 border-r">` (список) + `<div className="flex-1">` (Outlet).
- Роутер обновлён: `<Route path="artifacts" element={<ArtifactsPage />}>` с вложенными `<Route index ...>` (заглушка «выберите артефакт») и `<Route path=":aid">` (ArtifactView).
- `pages/artifacts/index.ts` экспортирует `ArtifactsPage`.

**Артефакты — список (`ArtifactList.tsx`):**
- Заголовок «Артефакты» в `font-serif text-base font-semibold` внутри 56px-шапки панели.
- Вспомогательная функция `ArtifactIcon({ type })`: `FileText` (md/text/default) / `Image` / `Mic` (audio) / `LayoutDashboard` (slides).
- Иконка в контейнере `h-9 w-9 rounded-md bg-muted` (36px).
- Выбранный элемент (сравнение `artifact.id === selectedId` из `useParams()`): `border border-secondary bg-secondary/30 [border-left-color:var(--ring)] [border-left-width:3px]` — лавандовая граница + 3px акцент слева.
- Empty-state `<Illustration scene="empty-artifacts" …>` (T3) сохранён; текст переведён.

**Артефакты — markdown-вьюер (`ArtifactView.tsx`):**
- Заголовок `font-serif text-[26px] font-semibold leading-tight`.
- Метаданные: `{type} · {created_at}` в `text-xs text-muted-foreground`.
- Кнопки (3 шт.): «Редактировать» — `variant="outline" disabled className="border-ring/60 text-ring"` (визуальная заглушка, группа B не активирована, {L0.5}); «.md» — `variant="default"` (primary); «.pdf» — `variant="outline"`.
- Контент в карточке: `rounded-xl border border-border bg-card px-8 py-6`, внутри `<div className="sphere-prose">` + `MarkdownRenderer`.
- Кнопка «← Назад» удалена (в сплит-лэйауте список всегда виден).

**CSS — `.sphere-prose` (добавлено в `index.css`):**
- H1–H6: `font-family: var(--font-serif)`, weight 600, line-height 1.3; первый заголовок без верхнего margin.
- `ul > li::before`: `content: "—"`, `color: var(--primary)`, absolute left.
- `ol > li::marker`: `color: var(--primary)`.
- Базовый prose-стиль: параграфы, blockquote (border-left 3px primary), code/pre (font-mono, bg-muted), ссылки (primary underline), hr, strong, em.

**Принятые решения:**
1. Сплит-лэйаут реализован новым компонентом `ArtifactsPage` — минимальное изменение роутера (вложенные роуты), логика загрузки не тронута.
2. `border-left` выбранного элемента через произвольные CSS-свойства Tailwind v4 `[border-left-*:...]` — чище, чем inline style; работает с Tailwind v4 CSS-first.
3. «Редактировать» в ArtifactView — `disabled` без onClick: редактирование артефактов — группа B (T6c); заглушка не вызывает несуществующий endpoint ({L0.5}).
4. `.sphere-prose` — единый класс для сферы и артефактов (одинаковые требования к типографике H-serif и маркерам); именование по основному контексту.
5. `cn()` из `@/shared/lib/utils` использован для условного className в ArtifactList.

**Verification:** `make check-fe` GREEN (tsc + ESLint + Prettier), `tsc -b && vite build` GREEN. {L0.3} shadcn-примитивы не правлены ✓; {L0.4} нет hex/numeric-цветов в тронутых .tsx ✓; {L0.5} заглушка «Редактировать» без endpoint-вызовов ✓; T3 empty-state иллюстрации сохранены ✓. Статические проверки {T4.4}/{T4.5} — пройдены. Полное 🔍 (seed-данные vs макеты) — на VISUAL_REVIEW.

---

## T4e — Проект + Настройки + Sidebar-полировка ✅

**Новые токены** (`frontend/src/index.css`): добавлены три группы переменных с маппингом в `@theme inline`:
- `--destructive-warm: #B0573F` (light) / `#D06050` (dark) → `text-destructive-warm`, `bg-destructive-warm` — терракота для деструктивных текстовых ссылок.
- `--mcp-connected: #4C9A6E` (light) / `#6AB88A` (dark) → `bg-mcp-connected` — зелёная точка статуса MCP.
- `--mcp-disabled: #C8C0AE` (light) / `#7E7490` (dark) → `bg-mcp-disabled` — серая точка отключённого сервера.

**Табы проекта** (`frontend/src/app/layouts/ProjectLayout.tsx`): активный таб — `text-primary [box-shadow:inset_0_-2px_0_var(--ring)]` (цвет акцента + подчёркивание снизу). Nav расширен до `h-full`, элементы — `flex h-full items-center px-3`. Имя проекта переведено на `font-serif font-semibold`. Кнопочный стиль `bg-primary rounded-md` убран.

**Проект — Чаты** (`frontend/src/pages/project-chats/ui/ChatList.tsx`): инпут нового чата обёрнут в карточку `rounded-xl border border-border bg-card p-3` с `boxShadow: var(--shadow-input)`. Textarea: `border-0 bg-transparent focus-visible:ring-0`. Чипы «Прикрепить» / «Модель» (secondary, rounded-full). Кнопка отправки: `h-[34px] w-[34px] rounded-full`. Список чатов: title через `font-serif font-semibold`, превью `truncate text-xs text-muted-foreground`, чипы вклада (заглушки на index, per plan: «N артефакта» / «+N в сферу»), дата. Empty-state illustration сохранена (T3).

**Проект — Настройки** (`frontend/src/pages/project-settings/ui/ProjectSettingsPage.tsx`): 4 карточки-секции `rounded-xl border border-border bg-card p-5`. Секция Модели (ModelSelector). Секция MCP-серверов. Секция «Имя проекта»: `input border-input` + кнопка «Сохранить» (через существующие `useProject`/`useUpdateProject`). Секция «Удалить проект»: текстовая кнопка `text-destructive-warm` без красной кнопки (через существующий `useDeleteProject` → navigate «/» после успеха). Заголовок `font-serif text-xl`.

**Настройки пользователя** (`frontend/src/pages/user-settings/ui/SettingsPage.tsx`): `max-w-[640px]`, заголовок `font-serif text-xl`. Каждая секция обёрнута в `rounded-xl border border-border bg-card p-5`. Порядок: Модель → Свои инструкции → Память агента → MCP-серверы.

**Custom instructions** (`CustomInstructionsSection.tsx`): textarea в `div rounded-lg border border-border bg-background` (textarea-card), textarea прозрачная без собственной рамки. Метки и placeholder переведены на русский.

**Память агента** (`AgentMemorySection.tsx`): шапка секции с `Switch checked={true}` (визуальный тоггл; управление включением — группа B) + счётчик `{n} записей`. Записи в карточках `rounded-lg border bg-background`. Метки русифицированы.

**features/model-selector** (`ModelSelector.tsx`): метка «Модель», опция «По умолчанию» / «Наследовать» (ru). Подсказка для scope=«project»: «Переопределяет модель пользователя для этого проекта».

**features/mcp-servers** (`MCPServersSection.tsx`): рефакторинг на `OwnedServerRow` (`MCPServer`, `is_active`) / `InheritedServerRow` (`InheritedMCPServer`, `is_disabled`) — исправлена проблема типов (оригинальный код использовал `is_disabled` для обоих). `StatusDot` компонент с `bg-mcp-connected` / `bg-mcp-disabled`. Mono-шрифт для URL/transport (`font-mono text-[10px]`). Метки русифицированы.

**Sidebar** (`frontend/src/app/components/Sidebar.tsx`): метки «Projects» → «Проекты», «Recents» → «Недавнее» + `tracking-wide`. Активный юзер-блок: `useMatch('/settings')` → `bg-sidebar-accent rounded-lg` на footer-строке (highlight per handoff item 11).

**Принятые решения:**
1. `Switch` в AgentMemorySection — `checked={true}` как визуальная заглушка: реального управления включением памяти нет (группа B). {L0.5} соблюдён.
2. Contribution chips в ChatList — stub-данные на основе index: явно помечены комментарием `visual only, no backend contract`.
3. `useDeleteProject` навигирует на «/» при успехе — естественный UX без нового контракта.
4. `OwnedServerRow` не показывает Switch — у `MCPServer` нет поля `is_disabled`; управление активацией через `is_active` планируется в отдельном тикете (группа B).
5. Терракота в `.dark` — `#D06050` (осветлённый вариант `#B0573F` для читаемости на тёмном фоне); точный тёмный вариант не задан в хэндоффе.

**Verification:** `make check-fe` GREEN (tsc + ESLint + Prettier), `tsc -b && vite build` GREEN. {L0.3} shadcn-примитивы не правлены ✓; {L0.4} нет hardcoded hex в тронутых .tsx (grep чистый) ✓; {L0.5} stub-chips/тоггл без endpoint-вызовов ✓; T3 empty-state сохранён ✓. Статические проверки {T4.6} — пройдены. Полное 🔍 (vs макеты screens 9–11) — на VISUAL_REVIEW.

---

## T6a — Студия-панель S1.2 + линза S2 + peek S3 (заглушки)

Реализованы три новых жеста доступа к сфере из чата. Весь интерактив — на локальном состоянии, без сетевых вызовов. Mock-данные захардкожены в коде слайса чата.

**Новые файлы (все в `frontend/src/pages/chat/`):**

- **`model/useStudio.ts`** — хук `useStudio()` возвращает стейт `{ open, tab, selectedArtifactId, lensOpen }` + контролы. `StudioControls = ReturnType<typeof useStudio>`. Состояние на уровне `ChatView`, персистентно по маунту чата.

- **`ui/StudioPanel.tsx`** — Студия-панель S1.2, 470px, `bg-muted`, `border-l`. Шапка: сегментный переключатель «Сфера | Артефакты» (трек `bg-bubble-user`, активный таб `bg-card shadow-sm`) + кнопка ✕ `close`. Вкладка «Сфера»: `SphereOrb size=80` (без колец, с искрами), метаданные `font-mono`, кнопка «Открыть в линзе», превью контента через `.sphere-prose`. Вкладка «Артефакты»: чипы материалов (3 мока: md/slides/audio), мини-вьюер с превью, футер «Открыть / .md / .pdf».

- **`ui/SphereLens.tsx`** — Оверлей-линза S2, модал 920×620. Скрим `var(--scrim-overlay)`, тень `var(--shadow-lens)` (добавлены в `index.css`). Содержимое: документ сферы (`.sphere-prose`) + рейл истории версий 252px. Текущая версия (`v2.4.1`) подсвечена `bg-secondary/30`. Найденный фрагмент — `<span className="bg-secondary text-secondary-foreground">`. Закрытие — ✕ или Esc (`useEffect` → `document.addEventListener('keydown')`).

- **`ui/SphereWriteCard.tsx`** — Peek-карточка S3. Шапка на `bg-secondary` (лаванда): «Записано в сферу → ‹раздел›» + mono-чип версии `v2.4.0 → v2.4.1 · патч`. Тело: diff-строки с зелёным `+` (`text-mcp-connected`) в `font-mono`. Действия: «Открыть в сфере» (`text-primary`) / «Подправить» (`text-muted-foreground`) / «Откатить» (`text-destructive-warm`, терракота). «Откатить» переключает локальное `reverted`-состояние без API-вызовов. Экспортирует `MOCK_SPHERE_WRITES` — константа с одним демо-событием.

**Изменённые файлы:**

- **`ui/ChatView.tsx`** — добавлен `useStudio()`, корневой `div` получает класс `studio-open` при `studio.open === true` (сужает `--content-max-w` до 520px по уже существующему CSS). Layout: `flex h-full` — чат-колонка (`flex-1 min-w-0`) + `{studio.open && <StudioPanel>}` + `<SphereLens>`.

- **`ui/ChatHeader.tsx`** — добавлены props `studioOpen: boolean` + `onToggleStudio: () => void`. Новый чип «Студия» (`PanelRight` icon) справа от инструментов: лавандовый `bg-secondary text-secondary-foreground` при открытой студии, иначе `bg-muted text-muted-foreground`.

- **`ui/MessageList.tsx`** — добавлен prop `onOpenLens: () => void`. Mock peek-карточки из `MOCK_SPHERE_WRITES` рендерятся после 2-го сообщения (index 1); при меньшем числе сообщений — в конце ленты (ключ `demo-{id}` исключает конфликт ключей).

- **`index.css`** — в `:root` добавлены `--scrim-overlay: rgba(24, 16, 36, 0.45)` и `--shadow-lens: 0 24px 80px rgba(24, 16, 36, 0.35)` (рядом с `--shadow-input`).

**Принятые решения:**

1. Стейт студии — в `useStudio()` hook на уровне `ChatView` (не Zustand): студия chat-специфична, по FSD `features/` только для 2+ страниц.
2. `--scrim-overlay` и `--shadow-lens` вынесены в CSS-переменные, а не инлайн rgba, чтобы не нарушать {L0.4}.
3. Peek-карточка всегда видна (хотя бы в конце ленты) — для демонстрации интерактива при пустом чате.
4. ESLint warning `react-refresh/only-export-components` для `SphereWriteCard.tsx` — не ошибка (`allowConstantExport: true` в конфиге); exit code 0.

**Verification:** `make check-fe` GREEN (exit 0: tsc чистый, ESLint 0 errors, Prettier чистый), `tsc -b && vite build` GREEN (exit 0). {L0.3} shadcn-примитивы не тронуты ✓; {L0.4} нет hardcoded hex/numeric-цветов в тронутых .tsx (grep чистый) ✓; {L0.5} все 4 новых файла без API-вызовов (grep чистый) ✓. Статические {T6.1}/{T6.2} — пройдены (открытие/закрытие студии, состояние локальное, нет сетевых вызовов). Полное 🔍 (визуальное vs хэндофф) — на VISUAL_REVIEW.

---

## T6b — Семвер-UI сферы (заглушки)

UI версионирования сферы на mock-данных. Никаких сетевых вызовов — все данные из локальных констант (группа B, {L0.5}).

**Новые файлы:**

- **`pages/sphere/model/mock-sphere-version.ts`** — источник правды по mock-данным T6b. Типы: `SphereVersionBump` («мажор» | «минор» | «патч»), `SphereVersionEntry` (version, summary, author, timestamp, bump, isNew), `SphereStats`. Константы: `MOCK_SPHERE_CURRENT_VERSION = "v2.4.1"`, `MOCK_SPHERE_STATUS = "растёт"`, `MOCK_SPHERE_STATS` (42 записи / 18 связей / 7 версий), `MOCK_SPHERE_HISTORY` (4 версии — v2.4.1/патч новый, v2.4.0/минор, v2.3.0/минор, v2.0.0/мажор), `MOCK_AGENT_SUGGESTION = "патч"`.

- **`pages/sphere/ui/SaveVersionDropdown.tsx`** — дропдаун «Сохранить версию ▾». Триггер через `render` prop (паттерн Base UI из `ProjectActions.tsx`). В раскрытом меню: лейбл «Предложение агента: патч» + разделитель + три пункта (патч/минор/мажор); пункт агента предвыбран — `bg-secondary text-secondary-foreground` (лаванда). Каждый пункт — двустрочный (название + описание). При клике: локальный setState → 3 сек. показывает inline-бейдж «Сохранено · патч» (`bg-secondary`, иконка Check), затем сброс. Никаких API-вызовов.

- **`pages/sphere/ui/SphereVersionPanel.tsx`** — правая панель «Жизнь сферы», 318px. Компоновка: заголовок 56px + `ScrollArea flex-1`. Содержимое сверху вниз:
  - `SphereOrb size={148}` — с кольцами и искрами (defaults).
  - Чип `v2.4.1 · растёт` — mono-шрифт, `bg-secondary`.
  - Счётчики: 3 карточки в `grid-cols-3` — записи / связи / версии (цифра + подпись).
  - Хроника (4 записи): точка-маркер `h-2 w-2 rounded-full` — `bg-primary` (isNew=true) / `bg-brand-lavender` (старое); рядом summary + «N часов назад · агент/вы».
  - История версий: каждая запись — `VersionBadge` (мажор → `bg-primary text-primary-foreground`; минор/патч → `bg-secondary text-secondary-foreground`) + summary + метаданные; текущая версия подсвечена `bg-secondary/30`.

**Изменённые файлы:**

- **`pages/sphere/ui/SphereViewer.tsx`** — добавлен `<SaveVersionDropdown />` в header рядом с кнопкой «Редактировать»; обёртка `flex gap-2`.

- **`pages/sphere/ui/SphereView.tsx`** — viewer-режим реструктурирован в `flex h-full overflow-hidden`: `<SphereViewer>` (`flex-1 min-w-0`) + `<SphereVersionPanel />` (318px). Режим редактирования (`SphereEditor`) без изменений — панель не добавляется.

- **`app/layouts/ProjectLayout.tsx`** — в шапке проекта: `projectName` обёрнут в `flex gap-2.5`, рядом добавлен чип `сфера v2.4.1 · растёт` (`rounded-full bg-secondary font-mono text-[10px]`). Mock-константы (`SPHERE_CHIP_VERSION`, `SPHERE_CHIP_STATUS`) определены локально в файле — без импорта из `pages/`, чтобы не нарушать FSD-направление зависимостей.

**Принятые решения:**

1. `DropdownMenuTrigger` использует `render` prop (Base UI паттерн, как в `ProjectActions.tsx`) — не `asChild`, т.к. Base UI не поддерживает `asChild`.
2. Чип состояния сферы в `ProjectLayout.tsx` — mock-значения инлайн (не импорт из `pages/sphere/`): app-слой не должен импортировать из internals page-слоя.
3. `SphereVersionPanel` не появляется в режиме редактора — правая панель с историей версий в редакторе относится к T6c (rich-редактор), не T6b.
4. `VersionBadge` — не экспортируется из файла (только `SphereVersionPanel`): внутренняя вспомогательная функция компонента, не предназначена для внешнего использования.

**Verification:** `make check-fe` GREEN (exit 0: tsc чистый, ESLint 0 errors, Prettier чистый), `tsc -b && vite build` GREEN (exit 0). {L0.3} shadcn-примитивы не тронуты ✓; {L0.4} нет hardcoded hex/numeric-цветов в тронутых .tsx (grep чистый) ✓; {L0.5} новые файлы без API-вызовов (grep чистый) ✓. Статический {T6.3} — пройден (дропдаун, бейджи, панель на моках без сети). Полное 🔍 (визуальное vs хэндофф экран 2) — на VISUAL_REVIEW.

---

## T6c — Вьюеры артефактов по типу + rich-редактор сферы (заглушки)

Вьюеры slides/image/audio выбираются по `type` артефакта и rich-редактор сферы — всё на mock-данных, без бэкенд-контрактов (группа B, {L0.5}). Существующий md-вьюер (T4d) и базовый редактор не сломаны.

**Новые файлы:**

- **`pages/artifact/model/mock-artifact-data.ts`** — единственный источник mock-данных T6c (не-компонентные экспорты вынесены в `.ts`, react-refresh чист). Содержит: `MockSlide[]`/`MockKeyMoment[]` типы; 5 слайдов (title + body); заголовки/даты/подпись изображения; заголовок/длительность аудио (742 сек = 12:22), саммари/транскрипт/заметки, 4 ключевых момента с таймкодами и `timeSeconds`.

- **`pages/artifact/ui/SlidesViewer.tsx`** — презентация. Слайд 16:9 (`aspectRatio: "16 / 9"`) в **намеренно ТЁМНОЙ теме слайдов** через CSS-переменные `--slides-bg`/`--slides-fg` (не реагируют на тему приложения — часть дизайна вьюера): orb-лого + mono-колонтитул `LearnFlowAI`, serif-заголовок 44px, mono-футер «N / M». Лента миниатюр 86×50 (активная — `ring-2 ring-ring ring-offset`, прочие — `opacity-60 ring-1 ring-border`). Навигация «‹ N / M ›» (`icon-sm`-кнопки + mono-счётчик), кнопки `.pdf` (primary) / `.pptx` (outline). Локальный стейт `currentIndex`. Guard `if (!slide) return null` для strict array access.

- **`pages/artifact/ui/ImageViewer.tsx`** — изображение. Плейсхолдер-карточка (реального URL нет) с масштабированием по `zoom%`; зум-пилюля по центру низа (`absolute bottom-4 left-1/2 -translate-x-1/2`): «− {zoom}% +» + разделитель + «По ширине» (сброс к 100%). Шаги зума `[50,75,100,125,150,200]`, дефолт 100%. Подпись с происхождением внизу. Кнопки `.png` (primary) / «Открыть в окне» (outline). Локальный стейт `zoomIndex`.

- **`pages/artifact/ui/AudioViewer.tsx`** — аудио. Плеер: play/pause-круг 40px (`bg-primary`), прогресс-бар 5px (`<input type="range">` с кастомным `::-webkit-slider-thumb` 12px primary, отформатированные таймкоды mono), кнопка скорости (цикл `[0.5…2]`, дефолт 1.5×). Табы Саммари/Транскрипт/Заметки агента (локальный стейт, активный — `text-primary [box-shadow:inset_0_-2px_0_var(--ring)]`). В «Саммари» — текст + «Ключевые моменты» с кликабельными mono-таймкодами (`text-ring`, при клике `seekTo` → выставляет `currentTime` и `isPlaying`). Транскрипт/Заметки — `pre` с `whitespace-pre-wrap`.

**Изменённые файлы:**

- **`pages/artifact/ui/ArtifactView.tsx`** — добавлен type-dispatch перед существующим md-вьюером: `type === "slides"|"image"|"audio"` → соответствующий вьюер; иначе — md-вьюер группы A без изменений. Дата форматируется один раз (`new Date(...).toLocaleDateString("ru-RU")`) и пробрасывается как `createdAt` (вьюеры дефолтят к mock-дате при отсутствии). Loading/error/markdown-логика не тронута.

- **`pages/sphere/ui/SphereEditor.tsx`** — апгрейд до rich-редактора при **сохранённом интерфейсе пропсов** (`content`/`isPending`/`error`/`onSave`/`onCancel` — реальное сохранение работает). Тулбар: дропдаун «Абзац ▾» (Абзац/Заголовок 2/Заголовок 3), B/I/S, H2/H3, список, цитата, код, ссылка, переключатель «Markdown-режим». Форматирование вставляет markdown-синтаксис в textarea через манипуляцию `selectionStart/End` (`applyInline`/`applyLinePrefix`). «Markdown-режим» (дефолт on) переключает между raw-textarea и предпросмотром через `MarkdownRenderer` (`.sphere-prose`). Автосейв-строка «черновик сохранён · HH:MM» (локальный `useEffect`-таймер 2 сек после ввода, без API). Правый рейл истории версий 252px (`w-[252px] border-l`) на `MOCK_SPHERE_HISTORY` из T6b: версия (mono) + `BumpBadge` (мажор — `bg-primary`; минор/патч — `bg-secondary`) + summary + метаданные.

- **`frontend/src/index.css`** — в `:root` добавлены `--slides-bg: #181420` / `--slides-fg: #ede8e2` (намеренно dark-палитра слайдов, не зависит от темы приложения; единственный способ держать слайды dark без hex в .tsx → {L0.4}).

**Принятые решения:**

1. Тёмная тема слайдов — через CSS-переменные `--slides-bg`/`--slides-fg`, а не классы `.dark`/инлайн-hex: слайд всегда dark независимо от темы приложения (по хэндоффу «слайды всегда dark `#181420`»), при этом {L0.4} соблюдён (нет hex в .tsx).
2. Date-форматирование — в `ArtifactView` при диспетче (real `created_at` → ISO), вьюеры получают уже отформатированную строку; mock-дефолты остаются человекочитаемыми для standalone-демонстрации.
3. ImageViewer рендерит плейсхолдер, а не реальное изображение: бэкенд бинарных артефактов нет (группа B), зум применяется к плейсхолдер-карточке для демонстрации интерактива.
4. Rich-редактор работает с реальным сохранением сферы (`onSave`/`onCancel`/`isPending`/`error` не тронуты) — тулбар/автосейв/история навешаны поверх; автосейв и история — заглушки ({L0.5}), реальное сохранение — существующий `useUpdateSphere`.
5. `BumpBadge`/`formatTime`/`applyInline`/`applyLinePrefix` — внутренние хелперы, не экспортируются из файлов компонентов (react-refresh чист).

**Verification:** `make check-fe` GREEN (exit 0: tsc + ESLint 0 errors + Prettier чистый), `tsc -b && vite build` GREEN (built ~16s). {L0.3} shadcn-примитивы не тронуты ✓; {L0.4} нет hardcoded hex в новых/тронутых .tsx (grep чистый — слайды через CSS-переменные) ✓; {L0.5} новые вьюер-файлы без API-вызовов (grep `fetch|axios|apiClient|useQuery|useMutation` чистый) ✓; md-вьюер группы A не сломан (диспетч добавлен перед ним, логика идентична) ✓. Статические {T6.4}/{T6.5} — пройдены (вьюеры на заглушках, нет несуществующих endpoint'ов). Полное 🔍 (визуальное vs хэндофф экраны 4/8) — на VISUAL_REVIEW.

---

## Code-review fixes ✅

По итогам CODE_REVIEW (0 blockers, 6 nit, 3 nice-to-have) применены 3 точечных фикса:

1. **Тост только на мутациях** (`QueryProvider.tsx`): `toast.error` убран из `QueryCache.onError` (оставлено логирование) — устраняет двойное отображение с инлайн-error-барами и toast-спам на фоновых refetch. В `MutationCache.onError` тост сохранён.
2. **InheritedServerRow без теста** (`MCPServersSection.tsx`): убрана кнопка «Проверить соединение» (`Zap`) у наследованных серверов — возврат к прежнему поведению (тест остался только у собственных серверов `OwnedServerRow`), т.к. валидность `test` по inherited-id не верифицирована и это было поведенческим выходом за рамки рестайла.
3. **Алиас иконки** (`ArtifactList.tsx`): `Image` → `Image as ImageIcon` для консистентности со `StudioPanel`/`ImageViewer`.

**Verification:** `make check-fe` GREEN + `tsc -b && vite build` GREEN.

**В предпродакшн-гейт (feat-006) — заглушки группы B видны в реальных вью** (не баг, by design scope, но не должно уехать в прод без gate/флага): peek-карточка `SphereWriteCard` рендерится в каждом реальном чате с fake-данными сферы; fake contribution-чипы в списке чатов; инертные кнопки-заглушки («Перегенерировать», футер студии, «Подправить»); всегда-включённый Switch памяти агента (`AgentMemorySection`); mock-подпись в `ImageViewer`; тулбар-префиксы rich-редактора не toggle (наслаивают `## ##`).

---

## DP — Data-prep: seed реальной БД ✅

**Что это.** Идемпотентный seed-скрипт `backend/scripts/seed_demo.py` (+ цель `make seed-demo`) наполняет реальную БД детерминированными учебными данными для визуального ревью населённых экранов. Вариант A (согласован архитектором): данные пишутся напрямую через существующие code-paths — без LLM, без прогона графа, без изменения схемы.

**Креды demo-пользователя** (dev/test-only):
- логин: `demo`
- пароль: `demo-pass-1234`
- проект: «Демо: Высшая математика»

Пользователь создаётся с `is_admin=True` (для security-экранов).

**Что сеется и через какие code-paths:**
- **User** `demo` — `UserRepository.create` + `hash_password`; admin-грант через `update(User).values(is_admin=True)` (как в `grant_admin.py`).
- **Project** «Демо: Высшая математика» — `ProjectRepository.create`.
- **3 чата** (`ThreadViewRepository.create`): «Цепное правило дифференцирования» (полный диалог с tool-вызовом), «С чего начать линейную алгебру» (простой двухходовой диалог), «Пределы и непрерывность» (пустой — для empty-state в ленте).
- **Сообщения** — через LangGraph-checkpointer (`AsyncPostgresSaver`). Подход: минимальный `StateGraph(MessagesState)`-проход компилируется с реальным checkpointer и `ainvoke`-ится с детерминированными `id` сообщений (uuid5). Так переиспользуется собственная сериализация LangGraph (та же форма, что читает рантайм-граф через `checkpoint_history.py`), без ручного конструирования внутренностей чекпойнта. Чат 1: `HumanMessage` → `AIMessage` с `tool_calls` (`create_artifact`) → `ToolMessage` → финальный `AIMessage`. `additional_kwargs["created_at"]` — фиксированные таймстампы.
- **Инлайн-артефакт** «Конспект: цепное правило» (`type=summary`) — `ArtifactRepository.create(thread_id=...)` + `set_message_id([id], <id финального AIMessage чата 1>)`; связь повторяет post-hoc-логику `ChatService.send_message`.
- **Standalone-артефакты** — `ArtifactRepository.create` с разными `type`: `plan`, `outline`, `code`, `slides`, `image`, `audio` (тип freeform Text). Вьюеры группы B (slides/image/audio) на фронте mock-driven — рендерятся по `type` на реальных строках списка.
- **Документ сферы** — `LangGraphSphereService.update(project_id, content=<markdown с ## разделами>)` (replace-by-section, идемпотентно по дизайну).

**Идемпотентность.** Реляционные сущности матчатся по натуральным ключам (`user.name`, имя проекта, заголовок чата/артефакта) — повторный прогон переиспользует существующие id. Сообщения дедуплицируются reducer-ом `add_messages` по детерминированным `id`. Сфера — replace-by-section.

**Запуск:** `make seed-demo` (грузит `.env`/`.env.local`, требует поднятую БД и применённые миграции; langgraph-таблицы создаёт сам через `store.setup()`/`checkpointer.setup()`).

**Verification:** `make seed-demo` — зелёный, прогон ×2 не дублирует (проверено read-back: чат1/чат2 по 4 сообщения, 3 чата, 7 артефактов 7 разных типов, инлайн-артефакт связан с сообщением, admin=True). `make check` (ruff + mypy) — зелёный.

---

## VISUAL_REVIEW ✅ PASS

Локальный стек (backend :8000 + frontend :5173 + Postgres/Redis) на seed-данных, Playwright MCP, light+dark. Полный отчёт + 7 скриншотов: `visual-review/visual-review-report.md`.

**Детерминированные (🔍 getComputedStyle):** `--primary #7434f4`/`--background #faf7f1` (light), `#181420`/`#ede8e2`/`--primary #8a5cf6`/`--ring #b194ff` (dark), `--radius 0.7rem`, sidebar 252px, `--content-max-w 680px`, body=Instrument Sans, переключатель темы вешает/снимает `.dark`. Консоль на всех маршрутах — **0 ошибок/ворнингов**.

**Экраны vs хэндофф:** welcome (light/dark, тема переключает иллюстрацию), chat (seed tool-flow: bubble/плоский ответ/ArtifactCard/peek), artifacts (сплит + 7 типов + чип сферы), slides-вьюер (dark-тема слайдов + миниатюры), sphere (документ + «Жизнь сферы»). Mismatch/blocker — нет.

**Остаток:** вкусовая полировка архитектору ({T4.8}/{E2E.6}) + предпрод-пункты (края cutout soft-balanced; стабы группы B с fake-данными в реальных вью — gate в feat-006).
