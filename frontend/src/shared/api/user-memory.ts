import { apiClient } from "./client";
import type { Instructions, ListResponse, MemoryItem } from "./types";

export async function getInstructions(): Promise<Instructions> {
  const { data } = await apiClient.get("/users/me/instructions");
  return data;
}

export async function updateInstructions(
  content: string,
): Promise<Instructions> {
  const { data } = await apiClient.put("/users/me/instructions", { content });
  return data;
}

export async function getMemories(): Promise<ListResponse<MemoryItem>> {
  const { data } = await apiClient.get("/users/me/memories");
  return data;
}

export async function deleteMemory(key: string): Promise<void> {
  await apiClient.delete(`/users/me/memories/${encodeURIComponent(key)}`);
}
