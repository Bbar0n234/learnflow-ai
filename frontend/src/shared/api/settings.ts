import { apiClient } from "./client";
import type { Settings, SettingsUpdate } from "./types";

type Scope = "user" | "project" | "thread";

function buildUrl(scope: Scope, projectId?: string, threadId?: string): string {
  if (scope === "user") return "/users/me/settings";
  if (scope === "project") return `/projects/${projectId}/settings`;
  return `/projects/${projectId}/chats/${threadId}/settings`;
}

export async function getSettings(
  scope: Scope,
  projectId?: string,
  threadId?: string,
): Promise<Settings> {
  const { data } = await apiClient.get(buildUrl(scope, projectId, threadId));
  return data;
}

export async function updateSettings(
  scope: Scope,
  body: SettingsUpdate,
  projectId?: string,
  threadId?: string,
): Promise<Settings> {
  const { data } = await apiClient.put(
    buildUrl(scope, projectId, threadId),
    body,
  );
  return data;
}
