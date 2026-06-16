import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import type { ListResponse } from "./pagination";
import { queryKeys } from "./query-keys";

// === Types ===

export interface Instructions {
  content: string;
}

export interface MemoryItem {
  key: string;
  description: string;
  content: string;
  created_at: string;
}

// === API ===

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

// === Hooks ===

export function useInstructions() {
  return useQuery({
    queryKey: queryKeys.instructions,
    queryFn: getInstructions,
  });
}

export function useUpdateInstructions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (content: string) => updateInstructions(content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.instructions });
    },
  });
}

export function useMemories() {
  return useQuery({
    queryKey: queryKeys.memories,
    queryFn: getMemories,
  });
}
