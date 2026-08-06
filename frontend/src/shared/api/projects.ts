import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import type { ListResponse } from "./pagination";
import { queryKeys } from "./query-keys";

// === Types ===

export interface Project {
  id: string;
  name: string;
  created_at: string;
  updated_at: string;
}

export interface CreateProjectRequest {
  name: string;
}

export interface UpdateProjectRequest {
  name: string;
}

// === API ===

export async function getProjects(): Promise<ListResponse<Project>> {
  // UI без постраничной подгрузки: берём максимум за один запрос
  return (await apiClient.get("/projects", { params: { limit: 200 } })).data;
}

export async function getProject(id: string): Promise<Project> {
  return (await apiClient.get(`/projects/${id}`)).data;
}

export async function createProject(
  data: CreateProjectRequest,
): Promise<Project> {
  return (await apiClient.post("/projects", data)).data;
}

export async function updateProject(
  id: string,
  data: UpdateProjectRequest,
): Promise<Project> {
  return (await apiClient.put(`/projects/${id}`, data)).data;
}

export async function deleteProject(id: string): Promise<void> {
  await apiClient.delete(`/projects/${id}`);
}

// === Hooks ===

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects.all,
    queryFn: getProjects,
  });
}

export function useProject(id: string) {
  return useQuery({
    queryKey: queryKeys.projects.detail(id),
    queryFn: () => getProject(id),
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
    },
  });
}

export function useUpdateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateProjectRequest }) =>
      updateProject(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
    },
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.projects.all });
    },
  });
}
