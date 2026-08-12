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
    // Запись именно своя, а не унаследованная от `Object.prototype`: обычное
    // обращение к свойству истинно и на имени `constructor`, то есть сторожило
    // бы полноту реестра вхолостую.
    expect(
      Object.prototype.hasOwnProperty.call(AGENT_TOOL_SIGNATURES, name),
    ).toBe(true);
  });

  it("имя вне реестра резолвится в сырое имя с пометкой источника", () => {
    const described = describeToolCall("acme_do_thing");

    expect(described.known).toBe(false);
    expect(described.label).toBe("acme_do_thing");
    expect(described.arg).toBe("инструмент MCP");
    expect(described.icon).toBeDefined();
  });

  // Имена инструментов приезжают с провода, и ключ `Object.prototype` — такое
  // же имя вне реестра, как любое другое: fallback обязан сработать. Пока
  // реестр опрашивался обычным обращением, эти имена резолвились в
  // унаследованные члены — подпись считалась известной, но приходила без
  // `label` и `icon`, и строка ленты роняла рендер всего сообщения.
  it.each(["constructor", "toString", "valueOf", "hasOwnProperty"])(
    "имя %s из Object.prototype резолвится fallback'ом, а не членом прототипа",
    (name) => {
      const described = describeToolCall(name, { args: "{}" });

      expect(described.known).toBe(false);
      expect(described.label).toBe(name);
      expect(described.arg).toBe("инструмент MCP");
      expect(described.icon).toBeDefined();
    },
  );

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
      tool: "search_web",
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
      tool: "read_url",
      args: { url: "docs.langchain.com/subagents" },
      label: "Читаю страницу",
      arg: "docs.langchain.com/subagents",
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

  it("тип субагента, совпадающий с ключом Object.prototype, даёт базовую подпись", () => {
    // Реестр читаемых имён субагентов опрашивается тем же именем с провода —
    // ключ прототипа обязан считаться неизвестным типом, а не подписью.
    const described = describeToolCall(SUBAGENT_TOOL_NAME, {
      args: JSON.stringify({ agent_type: "constructor" }),
    });

    expect(described.label).toBe("Субагент");
    expect(described.arg).toBe("constructor");
  });

  it("вызов без аргументов подписан без дополнения", () => {
    const described = describeToolCall("search_web");

    expect(described.label).toBe("Ищу в интернете");
    expect(described.arg).toBeNull();
  });

  it("усечённые аргументы не разбираются — подпись остаётся без дополнения", () => {
    // Обрезанная сервером строка не парсится по контракту: она оборвана
    // посреди JSON, и подпись из неё собрать нечем.
    const described = describeToolCall("search_web", {
      args: '{"query": "изоляция конте',
      truncated: true,
    });

    expect(described.label).toBe("Ищу в интернете");
    expect(described.arg).toBeNull();
  });

  it("аргументы нештатной формы не роняют подпись", () => {
    const described = describeToolCall("search_web", {
      args: "не json вовсе",
    });

    expect(described.label).toBe("Ищу в интернете");
    expect(described.arg).toBeNull();
  });

  it("пустое значение аргумента не даёт пустого дополнения", () => {
    const described = describeToolCall("search_web", {
      args: JSON.stringify({ query: "   " }),
    });

    expect(described.arg).toBeNull();
  });
});

// Грамматика подписи — глагол 1-го лица, время спрягает статус вызова: идущий
// читается настоящим, успешный — прошедшим совершенного вида, прерванный —
// прошедшим несовершенного («делал, но не довёл»). Ожидаемые формы утверждены
// архитектором на приёмке (вариант 1б), а не списаны из реестра.
describe("грамматика подписи по статусу вызова", () => {
  it.each([
    { status: undefined, label: "Обновляю память проекта" },
    { status: "running" as const, label: "Обновляю память проекта" },
    { status: "success" as const, label: "Обновил память проекта" },
    { status: "error" as const, label: "Обновлял память проекта" },
    { status: "pending" as const, label: "Обновлял память проекта" },
    { status: "cancelled" as const, label: "Обновлял память проекта" },
  ])(
    "update_section при статусе $status читается «$label»",
    ({ status, label }) => {
      const described = describeToolCall("update_section", { status });

      expect(described.label).toBe(label);
    },
  );

  it("у глагола без видовой пары обе прошедшие формы совпадают", () => {
    // «Искать» естественной пары вида не имеет: успех и прерывание читаются
    // одинаково — «Искал в интернете».
    expect(describeToolCall("search_web", { status: "success" }).label).toBe(
      "Искал в интернете",
    );
    expect(describeToolCall("search_web", { status: "error" }).label).toBe(
      "Искал в интернете",
    );
  });

  it("субагент остаётся именем действующего лица во всех статусах", () => {
    // «Субагент» — не действие, спрягать его нечем (решение архитектора).
    const source = {
      args: JSON.stringify({ agent_type: "judge" }),
      status: "success" as const,
    };

    expect(describeToolCall(SUBAGENT_TOOL_NAME, source).label).toBe(
      "Проверяющий субагент",
    );
    expect(
      describeToolCall(SUBAGENT_TOOL_NAME, { ...source, status: "error" })
        .label,
    ).toBe("Проверяющий субагент");
  });

  it("MCP fallback остаётся сырым именем во всех статусах", () => {
    expect(describeToolCall("acme_do_thing", { status: "success" }).label).toBe(
      "acme_do_thing",
    );
    expect(describeToolCall("acme_do_thing", { status: "pending" }).label).toBe(
      "acme_do_thing",
    );
  });
});

// Файловый и исполняющий слой (feat-011, T2.6). Ожидания — из мокапа
// `mockups/attachments-artifacts.html` блок 1 («Прочитал файл · uploads/notes.md»,
// «Записал файл · artifacts/lecture-1/konspekt.md», «Выполнил команду · pandoc …»),
// а не из самого реестра.
describe("подписи файловых и исполняющих инструментов", () => {
  it.each([
    {
      tool: "read_file",
      args: { path: "uploads/notes.md" },
      label: "Прочитал файл",
      arg: "uploads/notes.md",
    },
    {
      tool: "write_file",
      args: { path: "artifacts/lecture-1/konspekt.md", content: "текст" },
      label: "Записал файл",
      arg: "artifacts/lecture-1/konspekt.md",
    },
    {
      tool: "list_files",
      args: { path: "artifacts" },
      label: "Просмотрел файлы",
      arg: "artifacts",
    },
    {
      tool: "run_command",
      args: { cmd: "pandoc lecture.pdf -t plain" },
      label: "Выполнил команду",
      arg: "pandoc lecture.pdf -t plain",
    },
  ])(
    "завершённый $tool читается как «$label · $arg»",
    ({ tool, args, label, arg }) => {
      const described = describeToolCall(tool, {
        args: JSON.stringify(args),
        status: "success",
      });

      expect(described).toMatchObject({ label, arg, known: true });
    },
  );

  it("путь в подписи идёт голым, без кавычек свободного текста", () => {
    // Кавычки в реестре маркируют введённый человеком/моделью текст (ключ
    // памяти, поисковый запрос); путь — структурный идентификатор, и мокап
    // показывает его тем же голым моноширинным стилем, что URL.
    const described = describeToolCall("read_file", {
      args: JSON.stringify({ path: "uploads/notes.md" }),
    });

    expect(described.arg).toBe("uploads/notes.md");
  });

  it("запись файла подписана одинаково и при создании, и при перезаписи", () => {
    // Строка ленты о результате записи ничего не знает: «создано» против
    // «обновлено» несёт бейдж карточки артефакта, а не подпись вызова.
    const running = describeToolCall("write_file", {
      args: JSON.stringify({ path: "artifacts/konspekt.md" }),
      status: "running",
    });
    const done = describeToolCall("write_file", {
      args: JSON.stringify({ path: "artifacts/konspekt.md" }),
      status: "success",
    });

    expect(running.label).toBe("Записываю файл");
    expect(done.label).toBe("Записал файл");
  });

  it("обход корня воркспейса дополнением не становится", () => {
    // `list_files` дефолтит путь на «.» — показывать точку в строке ленты
    // бессмысленно, это не адресное дополнение.
    const described = describeToolCall("list_files", {
      args: JSON.stringify({ path: "." }),
    });

    expect(described.label).toBe("Просматриваю файлы");
    expect(described.arg).toBeNull();
  });

  it("исполнение кода остаётся без дополнения — код виден только в развороте", () => {
    const described = describeToolCall("execute_code", {
      args: JSON.stringify({
        code: "import pandas as pd\nprint(pd.__version__)",
      }),
      status: "success",
    });

    expect(described.label).toBe("Выполнил код");
    expect(described.arg).toBeNull();
  });

  it("упразднённый create_artifact подписи больше не имеет", () => {
    // Инструмент снят на бэкенде (`write_file` в `artifacts/` — его замена):
    // запись в реестре пережила бы его и врала бы о доступном инструменте.
    const described = describeToolCall("create_artifact");

    expect(described.known).toBe(false);
    expect(described.label).toBe("create_artifact");
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
