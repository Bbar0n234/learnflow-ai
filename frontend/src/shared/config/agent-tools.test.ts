import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  AGENT_TOOL_SIGNATURES,
  describeToolCall,
  resolveToolSignature,
} from "./agent-tools";

// Сторож полноты реестра подписей: имена инструментов берутся из
// машиночитаемого фикстура бэкенда, а не из списка на стороне фронта — иначе
// список сторожил бы сам себя и не покраснел бы на новый инструмент без
// подписи. Статический `import ... with { type: "json" }` за пределами vite
// root упирается в `server.fs.allow`, поэтому фикстур читается с диска.
interface ToolNameEntry {
  name: string;
  origin: "internal" | "builtin_mcp";
}

const FIXTURE_RELATIVE_PATH = "backend/contracts/agent-tool-names.json";

// Путь ищется вверх от cwd, а не через `import.meta.url`: под jsdom-окружением
// vitest он http-URL модуля дев-сервера, и `readFileSync` на нём падает.
function resolveFixturePath(): string {
  let dir = process.cwd();
  for (;;) {
    const candidate = join(dir, FIXTURE_RELATIVE_PATH);
    if (existsSync(candidate)) return candidate;
    const parent = dirname(dir);
    if (parent === dir) {
      throw new Error(`Фикстур имён инструментов не найден: ${dir}`);
    }
    dir = parent;
  }
}

const fixture = JSON.parse(
  readFileSync(resolveFixturePath(), "utf-8"),
) as ToolNameEntry[];

describe("реестр подписей инструментов", () => {
  it("фикстур имён бэкенда прочитан и непуст", () => {
    expect(fixture.length).toBeGreaterThan(0);
  });

  it.each(fixture)("имя $name ($origin) имеет подпись", ({ name }) => {
    const signature = resolveToolSignature(name);

    // known === false означает, что подпись собрана fallback'ом: инструмент
    // бэкенда добавили, а запись в реестр — нет.
    expect(signature.known, `нет подписи для инструмента ${name}`).toBe(true);
    expect(signature.label.trim()).not.toBe("");
    expect(AGENT_TOOL_SIGNATURES[name]).toBeDefined();
  });

  it("имя вне реестра резолвится в сырое имя с пометкой источника", () => {
    const described = describeToolCall("acme_do_thing");

    expect(described.known).toBe(false);
    expect(described.label).toBe("acme_do_thing");
    expect(described.arg).toBe("инструмент MCP");
    expect(described.icon).toBeDefined();
  });
});
