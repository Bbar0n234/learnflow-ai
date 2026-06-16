import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import { queryKeys } from "./query-keys";

// === Types ===

export interface Sphere {
  project_id: string;
  content: string;
  updated_at: string;
}

export interface UpdateSphereRequest {
  content: string;
}

// === API ===

export async function getSphere(projectId: string): Promise<Sphere> {
  return (await apiClient.get(`/projects/${projectId}/sphere`)).data;
}

export async function updateSphere(
  projectId: string,
  data: UpdateSphereRequest,
): Promise<Sphere> {
  return (await apiClient.put(`/projects/${projectId}/sphere`, data)).data;
}

// === Hooks ===

export function useSphere(projectId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.projects.sphere(projectId),
    queryFn: () => getSphere(projectId!),
    enabled: !!projectId,
  });
}

export function useUpdateSphere() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      data,
    }: {
      projectId: string;
      data: UpdateSphereRequest;
    }) => updateSphere(projectId, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.projects.sphere(variables.projectId),
      });
    },
  });
}
