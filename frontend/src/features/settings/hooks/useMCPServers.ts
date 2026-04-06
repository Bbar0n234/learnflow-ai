import { useQuery } from "@tanstack/react-query";
import { getMCPServers } from "@/shared/api/mcp-servers";

export function useMCPServers(
  scope: "user" | "project" | "thread",
  projectId?: string,
  threadId?: string,
) {
  const includeInherited = scope !== "user";
  return useQuery({
    queryKey: ["mcp-servers", scope, projectId, threadId].filter(Boolean),
    queryFn: () => getMCPServers(scope, projectId, threadId, includeInherited),
  });
}
