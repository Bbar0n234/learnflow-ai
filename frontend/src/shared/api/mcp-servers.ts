import { apiClient } from "./client";
import type {
  MCPServer,
  MCPServerCreate,
  MCPServerListResponse,
  MCPServerUpdate,
  TestConnectionResult,
} from "./types";

type Scope = "user" | "project" | "thread";

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
