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
