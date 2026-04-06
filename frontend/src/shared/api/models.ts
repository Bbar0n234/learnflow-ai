import { apiClient } from "./client";
import type { AvailableModel, ListResponse } from "./types";

export async function getModels(): Promise<ListResponse<AvailableModel>> {
  const { data } = await apiClient.get("/models");
  return data;
}
