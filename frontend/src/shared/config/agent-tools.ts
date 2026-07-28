import {
  Bot,
  BookOpen,
  Brain,
  FilePlus,
  FileSearch,
  FileText,
  Globe,
  ImagePlus,
  PenLine,
  Save,
  Search,
  Sparkles,
  Trash2,
  Wrench,
  type LucideIcon,
} from "lucide-react";

/**
 * Реестр человекочитаемых подписей инструментов агента: имя с провода →
 * действие по-русски, иконка и осмысленное дополнение подписи из аргументов.
 *
 * Полноту реестра сторожит `agent-tools.test.ts` против машиночитаемого
 * фикстура имён бэкенда (`backend/contracts/agent-tool-names.json`): новый
 * инструмент без подписи роняет CI. Список на стороне фронта был бы сторожем
 * самому себе и на забытую подпись не покраснел бы.
 *
 * Реестр полной ширины — все имена фикстура, включая read-only (`get_section`,
 * `get_skill_context`) и объявленный, но выключенный сервер (`tavily_*`):
 * read-only порождают обычные `tool_call_*` и видны в ленте наравне с
 * пишущими, а выключенный сервер может включиться на бэкенде без правок фронта.
 */

/** Разобранные аргументы вызова; ключи — параметры инструмента. */
export type ToolArgs = Record<string, unknown>;

export interface ToolSignature {
  /** Действие по-русски: «Ищу в интернете», «Обновляю память проекта». */
  label: string;
  icon: LucideIcon;
  /** Дополнение подписи из аргументов, без разделителя — его ставит рендер. */
  argTemplate?: (args: ToolArgs) => string | null;
  /**
   * Подпись, зависящая от аргументов (`run_subagent` → «Проверяющий субагент»).
   * `null` — читаемого варианта под эти аргументы нет, остаётся `label`.
   */
  labelTemplate?: (args: ToolArgs) => string | null;
}

export interface ResolvedToolSignature extends ToolSignature {
  /** Сырое имя инструмента — доступно в развороте всегда. */
  name: string;
  /** `false` — имя вне реестра (пользовательский MCP), подпись собрана fallback'ом. */
  known: boolean;
}

/**
 * Пометка для имён вне реестра. Имя сервера подставить нельзя: его нет ни в
 * SSE-событиях, ни в `ToolCallPart`, ни в фикстуре — пометка нейтральная.
 */
const MCP_FALLBACK_NOTE = "инструмент MCP";

function text(args: ToolArgs, key: string): string | null {
  const value = args[key];
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function firstUrl(args: ToolArgs): string | null {
  const urls = args.urls;
  if (!Array.isArray(urls)) return text(args, "url");
  const first = urls.find((item) => typeof item === "string" && item.trim());
  return typeof first === "string" ? first.trim() : null;
}

function quoted(value: string | null): string | null {
  return value === null ? null : `«${value}»`;
}

function section(args: ToolArgs): string | null {
  const id = quoted(text(args, "section_id"));
  return id === null ? null : `раздел ${id}`;
}

/** Читаемые имена субагентов из реестра бэкенда (`configs/agent.yaml`). */
const SUBAGENT_LABELS: Record<string, string> = {
  judge: "Проверяющий субагент",
  "web-research": "Исследующий субагент",
  "general-purpose": "Субагент общего назначения",
};

export const AGENT_TOOL_SIGNATURES: Record<string, ToolSignature> = {
  create_artifact: {
    label: "Сохраняю артефакт",
    icon: FileText,
    argTemplate: (args) => quoted(text(args, "title")),
  },
  create_section: {
    label: "Создаю раздел памяти проекта",
    icon: FilePlus,
    argTemplate: section,
  },
  delete_section: {
    label: "Удаляю раздел памяти проекта",
    icon: Trash2,
    argTemplate: section,
  },
  delete_skill_context: {
    label: "Удаляю документ навыка",
    icon: Trash2,
    argTemplate: (args) => quoted(text(args, "key")),
  },
  delete_user_memory: {
    label: "Удаляю запись из памяти о вас",
    icon: Trash2,
    argTemplate: (args) => quoted(text(args, "key")),
  },
  firecrawl_extract: {
    label: "Извлекаю данные со страницы",
    icon: FileSearch,
    argTemplate: firstUrl,
  },
  firecrawl_scrape: {
    label: "Читаю страницу",
    icon: Globe,
    argTemplate: (args) => text(args, "url"),
  },
  firecrawl_search: {
    label: "Ищу в интернете",
    icon: Search,
    argTemplate: (args) => quoted(text(args, "query")),
  },
  generate_image: {
    label: "Генерирую изображение",
    icon: ImagePlus,
    argTemplate: (args) => quoted(text(args, "title")),
  },
  get_section: {
    label: "Читаю память проекта",
    icon: BookOpen,
    argTemplate: section,
  },
  get_skill_context: {
    label: "Читаю документ навыка",
    icon: BookOpen,
    argTemplate: (args) => quoted(text(args, "key")),
  },
  load_skill: {
    label: "Загружаю навык",
    icon: Sparkles,
    argTemplate: (args) => quoted(text(args, "skill_name")),
  },
  run_subagent: {
    label: "Субагент",
    icon: Bot,
    labelTemplate: (args) => {
      const agentType = text(args, "agent_type");
      return agentType === null ? null : (SUBAGENT_LABELS[agentType] ?? null);
    },
    argTemplate: (args) => text(args, "agent_type"),
  },
  save_skill_context: {
    label: "Сохраняю документ навыка",
    icon: Save,
    argTemplate: (args) => quoted(text(args, "key")),
  },
  save_user_memory: {
    label: "Запоминаю о вас",
    icon: Brain,
    argTemplate: (args) => quoted(text(args, "key")),
  },
  tavily_extract: {
    label: "Извлекаю данные со страницы",
    icon: FileSearch,
    argTemplate: firstUrl,
  },
  tavily_search: {
    label: "Ищу в интернете",
    icon: Search,
    argTemplate: (args) => quoted(text(args, "query")),
  },
  update_section: {
    label: "Обновляю память проекта",
    icon: PenLine,
    argTemplate: section,
  },
};

/**
 * Подпись инструмента по имени. Имя вне реестра (пользовательский MCP) даёт
 * сырое имя с нейтральной пометкой источника — не пустую строку и не исключение.
 */
export function resolveToolSignature(name: string): ResolvedToolSignature {
  const signature = AGENT_TOOL_SIGNATURES[name];
  if (signature) return { ...signature, name, known: true };
  return {
    label: name,
    icon: Wrench,
    argTemplate: () => MCP_FALLBACK_NOTE,
    name,
    known: false,
  };
}

/**
 * Безопасный разбор аргументов вызова. `args` приезжает JSON-строкой, и при
 * `truncated === true` она обрезана посреди JSON — парсить можно только целую,
 * и всё равно под `try/catch`: при неудаче подпись остаётся без аргумента.
 */
export function parseToolArgs(
  args: string | null | undefined,
  truncated: boolean | undefined,
): ToolArgs | null {
  if (truncated === true || !args) return null;
  try {
    const parsed: unknown = JSON.parse(args);
    if (
      typeof parsed !== "object" ||
      parsed === null ||
      Array.isArray(parsed)
    ) {
      return null;
    }
    return parsed as ToolArgs;
  } catch {
    return null;
  }
}

export interface ToolCallDescription {
  /** Сырое имя инструмента. */
  name: string;
  label: string;
  /** Дополнение подписи (без разделителя) либо `null`. */
  arg: string | null;
  icon: LucideIcon;
  known: boolean;
}

/** Подпись строки ленты для одного вызова — из имени и (по возможности) аргументов. */
export function describeToolCall(
  tool: string,
  source?: { args?: string | null; truncated?: boolean },
): ToolCallDescription {
  const signature = resolveToolSignature(tool);
  const args = parseToolArgs(source?.args, source?.truncated) ?? {};
  return {
    name: signature.name,
    label: signature.labelTemplate?.(args) ?? signature.label,
    arg: signature.argTemplate?.(args) ?? null,
    icon: signature.icon,
    known: signature.known,
  };
}
