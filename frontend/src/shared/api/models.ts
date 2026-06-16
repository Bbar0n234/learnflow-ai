import { useQuery } from "@tanstack/react-query";
import { apiClient } from "./client";
import type { ListResponse } from "./pagination";
import { queryKeys } from "./query-keys";

// === Types ===

export interface AvailableModel {
  name: string;
  display_name: string;
}

// === API ===

export async function getModels(): Promise<ListResponse<AvailableModel>> {
  const { data } = await apiClient.get("/models");
  return data;
}

// === Hooks ===

export function useModels() {
  return useQuery({
    queryKey: queryKeys.models,
    queryFn: getModels,
    staleTime: 5 * 60 * 1000,
  });
}
