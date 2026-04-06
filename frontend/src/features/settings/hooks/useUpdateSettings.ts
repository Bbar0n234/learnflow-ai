import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateSettings } from "@/shared/api/settings";
import type { SettingsUpdate } from "@/shared/api/types";

export function useUpdateSettings(
  scope: "user" | "project" | "thread",
  projectId?: string,
  threadId?: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SettingsUpdate) =>
      updateSettings(scope, body, projectId, threadId),
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: ["settings", scope, projectId, threadId].filter(Boolean),
      });
    },
  });
}
