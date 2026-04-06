import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  createMCPServer,
  deleteMCPServer,
  testMCPServer,
  toggleInheritedServer,
  updateMCPServer,
} from "@/shared/api/mcp-servers";
import type { MCPServerCreate, MCPServerUpdate } from "@/shared/api/types";

export function useMCPServerMutations(
  scope: "user" | "project" | "thread",
  projectId?: string,
  threadId?: string,
) {
  const queryClient = useQueryClient();
  const queryKey = ["mcp-servers", scope, projectId, threadId].filter(Boolean);

  const create = useMutation({
    mutationFn: (body: MCPServerCreate) =>
      createMCPServer(scope, body, projectId, threadId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: MCPServerUpdate }) =>
      updateMCPServer(scope, id, body, projectId, threadId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  const remove = useMutation({
    mutationFn: (id: string) => deleteMCPServer(scope, id, projectId, threadId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  const test = useMutation({
    mutationFn: (id: string) => testMCPServer(scope, id, projectId, threadId),
  });

  const toggle = useMutation({
    mutationFn: ({ id, disabled }: { id: string; disabled: boolean }) =>
      toggleInheritedServer(scope, id, disabled, projectId, threadId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  return { create, update, remove, test, toggle };
}
