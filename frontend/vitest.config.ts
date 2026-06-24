import react from "@vitejs/plugin-react";
import path from "path";
import { defineConfig } from "vitest/config";

// Separate from vite.config.ts (D1): Vitest owns the jsdom test environment.
// globals are off — tests import { describe, it, expect, vi } from "vitest".
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
