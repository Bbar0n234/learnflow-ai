import { create } from "zustand";
import { persist } from "zustand/middleware";

type Theme = "light" | "dark";

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
}

function applyTheme(theme: Theme): void {
  if (theme === "dark") {
    document.documentElement.classList.add("dark");
  } else {
    document.documentElement.classList.remove("dark");
  }
}

function resolveInitialTheme(): Theme {
  // Try reading the persisted value before Zustand rehydrates
  try {
    const raw = localStorage.getItem("learnflow-theme");
    if (raw) {
      const parsed: unknown = JSON.parse(raw);
      if (
        parsed !== null &&
        typeof parsed === "object" &&
        "state" in parsed &&
        parsed.state !== null &&
        typeof parsed.state === "object" &&
        "theme" in parsed.state &&
        (parsed.state.theme === "light" || parsed.state.theme === "dark")
      ) {
        return parsed.state.theme;
      }
    }
  } catch {
    // ignore parse errors
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: resolveInitialTheme(),
      setTheme: (theme) => {
        applyTheme(theme);
        set({ theme });
      },
      toggleTheme: () => {
        set((s) => {
          const next: Theme = s.theme === "light" ? "dark" : "light";
          applyTheme(next);
          return { theme: next };
        });
      },
    }),
    {
      name: "learnflow-theme",
    },
  ),
);
