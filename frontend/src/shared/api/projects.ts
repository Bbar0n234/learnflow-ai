import type {
  CreateProjectRequest,
  ListResponse,
  Project,
  UpdateProjectRequest,
} from "./types";

// --- Mock data (mutable for create/delete support) ---

let mockProjects: Project[] = [
  {
    id: "proj-1",
    name: "Distributed Systems Lecture",
    created_at: "2025-12-01T10:00:00Z",
    updated_at: "2025-12-15T14:30:00Z",
  },
  {
    id: "proj-2",
    name: "ML Fundamentals Workshop",
    created_at: "2025-11-20T09:00:00Z",
    updated_at: "2025-12-10T16:45:00Z",
  },
  {
    id: "proj-3",
    name: "API Design Best Practices",
    created_at: "2025-12-05T11:00:00Z",
    updated_at: "2025-12-14T12:00:00Z",
  },
];

// --- API functions ---

export async function getProjects(): Promise<ListResponse<Project>> {
  // TODO: return (await apiClient.get("/projects")).data
  return { items: mockProjects };
}

export async function getProject(id: string): Promise<Project> {
  // TODO: return (await apiClient.get(`/projects/${id}`)).data
  const project = mockProjects.find((p) => p.id === id);
  if (!project) throw new Error(`Project not found: ${id}`);
  return project;
}

export async function createProject(
  data: CreateProjectRequest,
): Promise<Project> {
  // TODO: return (await apiClient.post("/projects", data)).data
  const now = new Date().toISOString();
  const project: Project = {
    id: crypto.randomUUID(),
    name: data.name,
    created_at: now,
    updated_at: now,
  };
  mockProjects.push(project);
  return project;
}

export async function updateProject(
  id: string,
  data: UpdateProjectRequest,
): Promise<Project> {
  // TODO: return (await apiClient.put(`/projects/${id}`, data)).data
  return {
    id,
    name: data.name,
    created_at: "2025-12-01T10:00:00Z",
    updated_at: new Date().toISOString(),
  };
}

export async function deleteProject(id: string): Promise<void> {
  // TODO: await apiClient.delete(`/projects/${id}`)
  mockProjects = mockProjects.filter((p) => p.id !== id);
}
