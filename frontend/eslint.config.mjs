import eslint from "@eslint/js";
import tseslint from "typescript-eslint";
import eslintConfigPrettier from "eslint-config-prettier";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import boundaries from "eslint-plugin-boundaries";

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  reactHooks.configs["recommended-latest"],
  eslintConfigPrettier,
  {
    plugins: {
      "react-refresh": reactRefresh,
    },
    rules: {
      "react-refresh/only-export-components": [
        "warn",
        { allowConstantExport: true },
      ],
    },
  },
  // FSD layer boundaries (arch-checker, feat-008). Layers import strictly
  // downward (app → pages → features → shared); `stores` is cross-cutting
  // client state. No cross-slice imports inside a layer. `pages`/`features`
  // are reachable only through their slice `index.ts`; `shared` is imported
  // by domain file (no barrel) and is exempt from the entry-point rule.
  // Rationale: conventions.md § Frontend, doc/tech/frontend.md.
  {
    files: ["src/**/*.{ts,tsx}"],
    plugins: { boundaries },
    settings: {
      "import/resolver": {
        typescript: { project: "./tsconfig.app.json" },
      },
      "boundaries/include": ["src/**/*"],
      "boundaries/elements": [
        { type: "app", pattern: "src/app", mode: "folder" },
        { type: "app", pattern: "src/*.{ts,tsx}", mode: "file" },
        {
          type: "pages",
          pattern: "src/pages/*",
          mode: "folder",
          capture: ["slice"],
        },
        {
          type: "features",
          pattern: "src/features/*",
          mode: "folder",
          capture: ["slice"],
        },
        { type: "stores", pattern: "src/stores", mode: "folder" },
        { type: "shared", pattern: "src/shared", mode: "folder" },
      ],
    },
    rules: {
      // Single dependencies rule (v6). `internalPath` doubles as the entry-point
      // constraint: pages/features are reachable only through their slice
      // `index.ts`. Same-slice imports are internal and skipped by default;
      // cross-slice (pages→pages, features→features) is disallowed since it is
      // not allow-listed. Unknown local targets (e.g. *.css) are ignored.
      "boundaries/dependencies": [
        "error",
        {
          default: "disallow",
          rules: [
            {
              from: { type: "app" },
              allow: [
                { to: { type: "app" } },
                {
                  to: {
                    type: ["pages", "features"],
                    internalPath: "index.{ts,tsx}",
                  },
                },
                { to: { type: ["shared", "stores"] } },
              ],
            },
            {
              from: { type: "pages" },
              allow: [
                { to: { type: "features", internalPath: "index.{ts,tsx}" } },
                { to: { type: ["shared", "stores"] } },
              ],
            },
            {
              from: { type: "features" },
              allow: [{ to: { type: ["shared", "stores"] } }],
            },
            {
              from: { type: "stores" },
              allow: [{ to: { type: ["stores", "shared"] } }],
            },
            { from: { type: "shared" }, allow: [{ to: { type: "shared" } }] },
          ],
        },
      ],
    },
  },
  {
    files: ["src/shared/ui/**/*.tsx"],
    rules: {
      "react-refresh/only-export-components": "off",
    },
  },
  {
    ignores: ["dist/", "build/", "node_modules/"],
  },
);
