import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

function getThemeSnapshot(): Theme {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function subscribe(onChange: () => void): () => void {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["class"],
  });
  return () => observer.disconnect();
}

/**
 * Текущая тема, как она отрисована на документе (класс `.dark` на `<html>`).
 * Источник истины темы — theme-store (`stores/`), который вешает/снимает класс;
 * здесь читаем результат через DOM. Это держит `shared/ui` независимым от
 * `stores` (граница FSD: shared → только shared), при этом реактивно следит за
 * сменой темы через MutationObserver.
 */
export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, getThemeSnapshot, () => "light");
}
