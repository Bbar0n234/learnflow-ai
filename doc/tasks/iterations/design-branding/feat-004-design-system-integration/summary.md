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
