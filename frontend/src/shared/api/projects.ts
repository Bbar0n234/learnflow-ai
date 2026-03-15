import { apiClient } from "./client";
import type {
  CreateProjectRequest,
  ListResponse,
  Project,
  UpdateProjectRequest,
} from "./types";

export async function getProjects(): Promise<ListResponse<Project>> {
  return (await apiClient.get("/projects")).data;
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
