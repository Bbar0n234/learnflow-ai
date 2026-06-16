import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import type { ListResponse } from "./pagination";
import { queryKeys } from "./query-keys";

type Scope = "user" | "project" | "thread";

// === Types ===

export interface MCPServer {
  id: string;
  name: string;
  transport: string;
  url: string;
  has_api_key: boolean;
  api_key_hint: string | null;
  allowed_tools: string[];
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface InheritedMCPServer {
  id: string;
  name: string;
  transport: string;
  url: string;
  has_api_key: boolean;
  api_key_hint: string | null;
  is_active: boolean;
  is_disabled: boolean;
}

export interface MCPServerListResponse extends ListResponse<MCPServer> {
  inherited: InheritedMCPServer[];
}

export interface MCPServerCreate {
  name: string;
  transport: "http" | "sse";
  url: string;
  api_key?: string;
}

export interface MCPServerUpdate {
  name?: string;
  transport?: "http" | "sse";
  url?: string;
  api_key?: string;
  is_active?: boolean;
}

export interface TestConnectionResult {
  success: boolean;
  tools: string[];
  error?: string;
}

// === API ===

function buildBase(
  scope: Scope,
  projectId?: string,
  threadId?: string,
): string {
  if (scope === "user") return "/users/me/mcp-servers";
  if (scope === "project") return `/projects/${projectId}/mcp-servers`;
  return `/projects/${projectId}/chats/${threadId}/mcp-servers`;
}

export async function getMCPServers(
  scope: Scope,
  projectId?: string,
  threadId?: string,
  includeInherited?: boolean,
): Promise<MCPServerListResponse> {
  const params = includeInherited ? { include_inherited: true } : {};
  const { data } = await apiClient.get(buildBase(scope, projectId, threadId), {
    params,
  });
  return data;
}

export async function createMCPServer(
  scope: Scope,
  body: MCPServerCreate,
  projectId?: string,
  threadId?: string,
): Promise<MCPServer> {
  const { data } = await apiClient.post(
    buildBase(scope, projectId, threadId),
    body,
  );
  return data;
}

export async function updateMCPServer(
  scope: Scope,
  serverId: string,
  body: MCPServerUpdate,
  projectId?: string,
  threadId?: string,
): Promise<MCPServer> {
  const { data } = await apiClient.put(
    `${buildBase(scope, projectId, threadId)}/${serverId}`,
    body,
  );
  return data;
}

export async function deleteMCPServer(
  scope: Scope,
  serverId: string,
  projectId?: string,
  threadId?: string,
): Promise<void> {
  await apiClient.delete(
    `${buildBase(scope, projectId, threadId)}/${serverId}`,
  );
}

export async function testMCPServer(
  scope: Scope,
  serverId: string,
  projectId?: string,
  threadId?: string,
): Promise<TestConnectionResult> {
  const { data } = await apiClient.post(
    `${buildBase(scope, projectId, threadId)}/${serverId}/test`,
  );
  return data;
}

export async function toggleInheritedServer(
  scope: Scope,
  serverId: string,
  disabled: boolean,
  projectId?: string,
  threadId?: string,
): Promise<void> {
  await apiClient.put(
    `${buildBase(scope, projectId, threadId)}/inherited/${serverId}/toggle`,
    { disabled },
  );
}

// === Hooks ===

export function useMCPServers(
  scope: Scope,
  projectId?: string,
  threadId?: string,
) {
  const includeInherited = scope !== "user";
  return useQuery({
    queryKey: queryKeys.mcpServers(scope, projectId, threadId),
    queryFn: () => getMCPServers(scope, projectId, threadId, includeInherited),
  });
}

export function useMCPServerMutations(
  scope: Scope,
  projectId?: string,
  threadId?: string,
) {
  const queryClient = useQueryClient();
  const queryKey = queryKeys.mcpServers(scope, projectId, threadId);

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
