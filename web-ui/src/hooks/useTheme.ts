import { useState, useEffect, useCallback } from 'react';

type Theme = 'light' | 'dark' | 'system';

const getPreferredTheme = (): Theme => {
  const stored = localStorage.getItem('theme') as Theme | null;
  if (stored) return stored;
  // If nothing stored, use system preference and return the concrete theme
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
};

const applyThemeTokens = (theme: Theme): 'light' | 'dark' => {
  const actualTheme: 'light' | 'dark' =
    theme === 'system'
      ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : theme;

  console.log('[applyThemeTokens] Applying theme:', actualTheme, 'from:', theme);

  // Ensure mutually exclusive classes to override system preference
  if (actualTheme === 'dark') {
    document.documentElement.classList.add('dark');
    document.documentElement.classList.remove('light');
  } else {
    document.documentElement.classList.remove('dark');
    document.documentElement.classList.add('light');
  }

  console.log('[applyThemeTokens] Classes after apply:', 
    'dark:', document.documentElement.classList.contains('dark'),
    'light:', document.documentElement.classList.contains('light'));

  return actualTheme;
};

export const useTheme = () => {
  // Initialize asap to reduce FOUC
  const initialTheme = getPreferredTheme();
  const initialActual = applyThemeTokens(initialTheme);

  const [theme, setThemeState] = useState<Theme>(initialTheme);
  const [isDark, setIsDark] = useState<boolean>(initialActual === 'dark');

  const updateTheme = useCallback((newTheme: Theme) => {
    const previousTheme = (localStorage.getItem('theme') as Theme | null) ?? '(none)';
    const actual = applyThemeTokens(newTheme);
    setIsDark(actual === 'dark');
    localStorage.setItem('theme', newTheme);

    if (!import.meta.env.PROD) {
      // eslint-disable-next-line no-console
      console.info(`[theme] ${previousTheme} -> ${newTheme} | effective=${actual}`);
    }

    // Sync across tabs
    window.dispatchEvent(
      new StorageEvent('storage', {
        key: 'theme',
        newValue: newTheme,
        storageArea: localStorage,
      })
    );
  }, []);

  const setTheme = useCallback(
    (newTheme: Theme) => {
      setThemeState(newTheme);
      updateTheme(newTheme);
    },
    [updateTheme]
  );

  const toggleTheme = useCallback(() => {
    const newTheme: Theme = theme === 'dark' ? 'light' : 'dark';
    setTheme(newTheme);
  }, [theme, setTheme]);

  const setSystemTheme = useCallback(() => {
    setTheme('system');
  }, [setTheme]);

  // React to system preference changes when in system mode
  useEffect(() => {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => {
      if (theme === 'system') {
        updateTheme('system');
      }
    };
    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [theme, updateTheme]);

  // Handle cross-tab synchronization
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'theme' && e.newValue) {
        const newTheme = e.newValue as Theme;
        setThemeState(newTheme);
        const actual = applyThemeTokens(newTheme);
        setIsDark(actual === 'dark');
      }
    };

    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, []);

  return {
    theme,
    isDark,
    toggleTheme,
    setSystemTheme,
    initializeTheme: () => getPreferredTheme(),
    applyThemeTokens: (t: Theme) => applyThemeTokens(t),
    getPreferredTheme,
    setTheme,
  };
};