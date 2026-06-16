import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import { queryKeys } from "./query-keys";

type Scope = "user" | "project" | "thread";

// === Types ===

export interface Settings {
  model_name: string | null;
  extra_body: object | null;
  resolved_model: string;
  resolved_source: string;
}

export interface SettingsUpdate {
  model_name: string | null;
  extra_body?: object | null;
}

// === API ===

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

// === Hooks ===

export function useSettings(
  scope: Scope,
  projectId?: string,
  threadId?: string,
) {
  return useQuery({
    queryKey: queryKeys.settings(scope, projectId, threadId),
    queryFn: () => getSettings(scope, projectId, threadId),
  });
}

export function useUpdateSettings(
  scope: Scope,
  projectId?: string,
  threadId?: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SettingsUpdate) =>
      updateSettings(scope, body, projectId, threadId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.settings(scope, projectId, threadId),
      });
    },
  });
}
