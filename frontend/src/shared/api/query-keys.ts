// Единый источник истины по queryKey TanStack Query.
// Иерархия ключей сохраняется для префиксной инвалидации: инвалидация родителя
// (например queryKeys.projects.detail(id)) задевает всех потомков того же префикса.

type Scope = "user" | "project" | "thread";

export const queryKeys = {
  projects: {
    all: ["projects"] as const,
    detail: (id: string | undefined) => ["projects", id] as const,
    chats: (id: string | undefined) => ["projects", id, "chats"] as const,
    chat: (id: string | undefined, chatId: string | undefined) =>
      ["projects", id, "chats", chatId] as const,
    sphere: (id: string | undefined) => ["projects", id, "sphere"] as const,
    artifacts: (id: string | undefined) =>
      ["projects", id, "artifacts"] as const,
    artifact: (id: string | undefined, artifactId: string | undefined) =>
      ["projects", id, "artifacts", artifactId] as const,
  },
  chats: {
    recent: ["chats", "recent"] as const,
  },
  models: ["models"] as const,
  instructions: ["instructions"] as const,
  memories: ["memories"] as const,
  settings: (scope: Scope, projectId?: string, threadId?: string) =>
    ["settings", scope, projectId, threadId].filter(Boolean),
  mcpServers: (scope: Scope, projectId?: string, threadId?: string) =>
    ["mcp-servers", scope, projectId, threadId].filter(Boolean),
  auth: {
    me: ["auth", "me"] as const,
  },
  security: {
    events: (params: Record<string, unknown>) =>
      ["security", "events", params] as const,
    // prefix для инвалидации всех списков алертов
    alerts: ["security", "alerts"] as const,
    alertsList: (params: Record<string, unknown>) =>
      ["security", "alerts", params] as const,
    alert: (id: number) => ["security", "alert", id] as const,
    // prefix для инвалидации всех списков правил
    rules: ["security", "rules"] as const,
    rulesList: (params: Record<string, unknown>) =>
      ["security", "rules", params] as const,
    rule: (id: number) => ["security", "rule", id] as const,
  },
};
