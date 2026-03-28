# Post-Implementation Summary: feat-001 — Scaffold + App Shell

## Результат

Все критерии приёмки выполнены:
- `make dev-fe` запускает Vite dev server
- Навигация между 6 маршрутами работает
- Tailwind-классы применяются, shadcn/ui компоненты рендерятся
- TypeScript strict mode — 0 ошибок
- ESLint — 0 ошибок, 0 warnings
- Vite production build — success (261 kB JS, 25 kB CSS)

## Отклонения от плана

### shadcn v4: Base UI вместо Radix UI

**Что:** shadcn v4.0.5 перешёл на `@base-ui/react` (MUI). Стиль по умолчанию — `base-nova` (план ожидал `default` / `radix-nova`).

**Влияние:** у Button нет пропа `asChild` (Radix-паттерн). Для стилизации `<Link>` как кнопки использован `buttonVariants()` — стандартный shadcn-паттерн. Компонент `<Button>` не рендерится на scaffold-страницах, будет верифицирован в следующих итерациях.

**Решение архитектора:** допустимая адаптация.

### overrides вместо .npmrc

**Что:** `eslint-plugin-react-hooks@7.0.1` (октябрь 2025) декларирует peer dep `eslint@^3-9`. ESLint 10 вышел в феврале 2026 — авторы плагина не выпустили обновлённую стабильную версию.

**Первоначально:** добавлен `.npmrc` с `legacy-peer-deps=true` (глушит все peer dep проверки).

**Финальное решение:** `.npmrc` удалён. Добавлен таргетированный `overrides` в `package.json`:
```json
"overrides": {
  "eslint-plugin-react-hooks": {
    "eslint": "$eslint"
  }
}
```
Переопределяет peer dep только для этого плагина. Остальные проверки работают штатно. При выходе стабильной версии плагина с поддержкой ESLint 10 — убрать override и обновить плагин.

### ESLint: react-refresh для shadcn-файлов

**Что:** правило `react-refresh/only-export-components` выдавало warning на shadcn-компоненты (экспортируют и компонент, и variants-функцию).

**Решение:** исключить `src/shared/ui/**/*.tsx` из правила react-refresh в ESLint конфиге. Папка содержит только shadcn-сгенерированные файлы; наш код (в `app/`, `features/`) проверяется штатно.

## Актуализация документации

- `doc/tech/frontend.md` — Module Structure: `tailwind.css` → `src/index.css`, добавлен `app/components/`
