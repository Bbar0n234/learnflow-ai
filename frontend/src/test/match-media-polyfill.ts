// Local test helper (not part of the frozen harness). jsdom does not implement
// `window.matchMedia`, but the theme store calls it at module load to resolve
// the initial theme from `(prefers-color-scheme: dark)`. Importing this module
// installs a minimal, always-"no match" implementation so any component tree
// containing the app chrome (Sidebar, AppLayout) can render under jsdom.
// Import it from any test that mounts such a tree.

if (typeof window !== "undefined" && typeof window.matchMedia !== "function") {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}

export {};
