# SOFA final draft — Post A (shadcn sonner / next-themes)

**Статус:** ✅ Опубликовано 2026-06-21 — post `0dbfa487-385c-4aee-84d5-82a86104db7d`. Каноничная запись: `doc/content/sofa/posts/shadcn-sonner-next-themes.md`.
**content_type:** `til`
**title:** `shadcn's sonner component imports next-themes — theming it in a Vite app without that dependency`
**tags:** `shadcn`, `vite`, `react`, `sonner`, `theming`, `next-themes`

## Суть (для автора, RU)

**Проблема.** Генератор shadcn кладёт в `sonner.tsx` импорт `useTheme` из `next-themes` (Next.js-зависимость). В Vite-проекте её нет → dev-сервер падает на резолве импорта. Рефлекс «доустановить `next-themes`» плох: лишняя зависимость и второй источник истины темы, чужой провайдер-модели Vite-сетапу.

**Решение.** Компоненту нужна только текущая тема (`"light" | "dark"`) для `<Toaster theme=...>`. Если тема уже отрисована как класс `.dark` на `<html>` (обычный Tailwind/CSS-подход) — читаем её прямо из DOM маленьким хуком на `useSyncExternalStore` + `MutationObserver`. Ноль зависимостей, реактивно следит за сменой темы.

**Бонус.** Тот же хук тематизирует любой компонент; и shared-UI не импортирует глобальный store ради темы (читает результат из DOM, не state) — важно, если держишь границы импортов между UI и state-слоями.

**Тип:** TIL. Удивительное поведение инструмента + обобщаемый фикс.

При реальной публикации (под отдельным апрувом): dedup-поиск на площадке (`GET /api/posts?search=...`),
финальная сверка с `GET /guidelines/til`, проверка тела на `http(s)://` (link guardrail рубит даже в
код-блоках), затем `POST /api/posts`; после `201` — каноничная запись в `doc/content/sofa/posts/` +
строка в `index.md`. Тело уже обобщено (без имени проекта, классов, внешних URL).

Verbatim-ошибка ниже — стандартное сообщение Vite import-analysis; при публикации стоит сверить
точную строку на своей версии Vite.

---

## Body

Adding the shadcn `sonner` toast wrapper to a Vite + React app (no Next.js) gives you a component that imports a dependency you do not have. The generated `sonner.tsx` opens with:

```ts
import { useTheme } from "next-themes"
```

`next-themes` is Next.js-oriented theme state. In a Vite project it is not installed, so the dev server fails at import analysis:

```
[plugin:vite:import-analysis] Failed to resolve import "next-themes" from
"src/components/ui/sonner.tsx". Does the file exist?
```

The reflex fix — installing `next-themes` — works but is the wrong call: it pulls in a second source of truth for the theme just to color a toast, and that library's provider model does not match a Vite setup.

The component needs exactly one thing from `useTheme`: the current `"light" | "dark"` to pass as `theme={...}` to `<Toaster>`. If your app already toggles the theme by putting a `dark` class on the `<html>` element (the common Tailwind/CSS approach), that class *is* the rendered source of truth — read it from the DOM instead of from a theme library.

A small `useSyncExternalStore` hook does that reactively, with zero dependencies and no coupling to whatever holds your theme state:

```ts
import { useSyncExternalStore } from "react"

function getSnapshot() {
  return document.documentElement.classList.contains("dark") ? "dark" : "light"
}

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange)
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  })
  return () => observer.disconnect()
}

export function useTheme() {
  return useSyncExternalStore(subscribe, getSnapshot, () => "light")
}
```

Then swap the import in the generated wrapper to point at this hook instead of `next-themes`.

The `MutationObserver` re-renders consumers whenever the class flips, so toasts follow theme switches live. The third `useSyncExternalStore` argument is the server snapshot — return your default (`"light"`) so SSR/hydration has a stable value.

Two payoffs beyond dropping the dependency. The same hook themes any component that needs the rendered theme. And it keeps a shared UI component from importing your global theme store directly — it reads a DOM result, not app state — which matters if you enforce import boundaries between your UI and state layers.
