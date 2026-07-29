import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, expect, it } from "vitest";

import {
  AGENT_TOOL_SIGNATURES,
  describeToolCall,
  parseToolArgs,
  resolveToolSignature,
  SUBAGENT_TASK_ARG,
  SUBAGENT_TOOL_NAME,
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

  it("имя вызова с вложенной лентой присутствует в фикстуре бэкенда", () => {
    // Вложенность рендерится по имени инструмента: переименуй его бэкенд — и
    // шаги субагента молча перестанут узнаваться, ничего при этом не уронив.
    expect(fixture.map((entry) => entry.name)).toContain(SUBAGENT_TOOL_NAME);
  });
});

// Подпись строки — то, что пользователь читает вместо машинного имени вызова.
// Ожидания взяты из design-brief § Frontend и утверждённого мокапа
// `live-timeline-v3.html` («Ищу в интернете · «…»», «Обновляю память проекта ·
// раздел «…»», «Проверяющий субагент · judge»), а не из самого реестра —
// иначе тест сверял бы реестр с реестром.
describe("подпись вызова из имени и аргументов", () => {
  it.each([
    {
      tool: "firecrawl_search",
      args: { query: "изоляция контекста субагентов" },
      label: "Ищу в интернете",
      arg: "«изоляция контекста субагентов»",
    },
    {
      tool: "update_section",
      args: { section_id: "Субагенты" },
      label: "Обновляю память проекта",
      arg: "раздел «Субагенты»",
    },
    {
      tool: "firecrawl_scrape",
      args: { url: "docs.langchain.com/subagents" },
      label: "Читаю страницу",
      arg: "docs.langchain.com/subagents",
    },
    {
      tool: "firecrawl_extract",
      args: { urls: ["arxiv.org/2606.01441", "example.com"] },
      label: "Извлекаю данные со страницы",
      arg: "arxiv.org/2606.01441",
    },
    {
      tool: "load_skill",
      args: { skill_name: "langgraph-patterns" },
      label: "Загружаю навык",
      arg: "«langgraph-patterns»",
    },
    {
      tool: "save_user_memory",
      args: { key: "любимый язык" },
      label: "Запоминаю о вас",
      arg: "«любимый язык»",
    },
  ])("$tool читается как «$label · $arg»", ({ tool, args, label, arg }) => {
    const described = describeToolCall(tool, { args: JSON.stringify(args) });

    expect(described).toMatchObject({ name: tool, label, arg, known: true });
  });

  it.each([
    { agentType: "judge", label: "Проверяющий субагент" },
    { agentType: "web-research", label: "Исследующий субагент" },
    { agentType: "general-purpose", label: "Субагент общего назначения" },
  ])(
    "субагент $agentType подписан как «$label»",
    ({ agentType, label }: { agentType: string; label: string }) => {
      const described = describeToolCall(SUBAGENT_TOOL_NAME, {
        args: JSON.stringify({
          agent_type: agentType,
          [SUBAGENT_TASK_ARG]: "Проверь выводы.",
        }),
      });

      // Читаемое имя — в подписи, машинное — в дополнении: разделять их нужно
      // для стилей мокапа (`.act-label` против `.act-label .arg`).
      expect(described.label).toBe(label);
      expect(described.arg).toBe(agentType);
    },
  );

  it("субагент неизвестного типа остаётся с базовой подписью", () => {
    const described = describeToolCall(SUBAGENT_TOOL_NAME, {
      args: JSON.stringify({ agent_type: "brand-new-role" }),
    });

    expect(described.label).toBe("Субагент");
    expect(described.arg).toBe("brand-new-role");
  });

  it("вызов без аргументов подписан без дополнения", () => {
    const described = describeToolCall("firecrawl_search");

    expect(described.label).toBe("Ищу в интернете");
    expect(described.arg).toBeNull();
  });

  it("усечённые аргументы не разбираются — подпись остаётся без дополнения", () => {
    // Обрезанная сервером строка не парсится по контракту: она оборвана
    // посреди JSON, и подпись из неё собрать нечем.
    const described = describeToolCall("firecrawl_search", {
      args: '{"query": "изоляция конте',
      truncated: true,
    });

    expect(described.label).toBe("Ищу в интернете");
    expect(described.arg).toBeNull();
  });

  it("аргументы нештатной формы не роняют подпись", () => {
    const described = describeToolCall("firecrawl_search", {
      args: "не json вовсе",
    });

    expect(described.label).toBe("Ищу в интернете");
    expect(described.arg).toBeNull();
  });

  it("пустое значение аргумента не даёт пустого дополнения", () => {
    const described = describeToolCall("firecrawl_search", {
      args: JSON.stringify({ query: "   " }),
    });

    expect(described.arg).toBeNull();
  });
});

describe("разбор аргументов вызова", () => {
  it("возвращает объект аргументов на целой JSON-строке", () => {
    expect(parseToolArgs('{"query": "langgraph", "limit": 10}', false)).toEqual(
      {
        query: "langgraph",
        limit: 10,
      },
    );
  });

  it.each([
    { name: "усечённая строка", args: '{"query": "lang', truncated: true },
    { name: "оборванный JSON", args: '{"query": "lang', truncated: false },
    { name: "массив", args: "[1, 2, 3]", truncated: false },
    { name: "скаляр", args: '"строка"', truncated: false },
    { name: "null", args: "null", truncated: false },
    { name: "пустая строка", args: "", truncated: false },
  ])("$name аргументами не считается", ({ args, truncated }) => {
    expect(parseToolArgs(args, truncated)).toBeNull();
  });

  it("целая строка при поднятом флаге усечения всё равно не разбирается", () => {
    // Флаг — слово сервера о том, что данные неполны; доверять форме важнее,
    // чем случайной парсимости обрезка.
    expect(parseToolArgs('{"query": "lang"}', true)).toBeNull();
  });
});
