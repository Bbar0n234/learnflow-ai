import { apiClient } from "./client";
import type { Sphere, UpdateSphereRequest } from "./types";

export async function getSphere(projectId: string): Promise<Sphere> {
  return (await apiClient.get(`/projects/${projectId}/sphere`)).data;
}

export async function updateSphere(
  projectId: string,
  data: UpdateSphereRequest,
): Promise<Sphere> {
  return (await apiClient.put(`/projects/${projectId}/sphere`, data)).data;
}
