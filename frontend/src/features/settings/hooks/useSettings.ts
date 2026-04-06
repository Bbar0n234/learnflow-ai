import { useQuery } from "@tanstack/react-query";
import { getSettings } from "@/shared/api/settings";

export function useSettings(
  scope: "user" | "project" | "thread",
  projectId?: string,
  threadId?: string,
) {
  return useQuery({
    queryKey: ["settings", scope, projectId, threadId].filter(Boolean),
    queryFn: () => getSettings(scope, projectId, threadId),
  });
}
