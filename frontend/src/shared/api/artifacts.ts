import { useQuery } from "@tanstack/react-query";
import { apiClient } from "./client";
import type { ListResponse } from "./pagination";
import { queryKeys } from "./query-keys";

// === Types ===

export interface Artifact {
  id: string;
  title: string;
  type: string;
  created_at: string;
}

export interface ArtifactDetail {
  id: string;
  title: string;
  type: string;
  content: string;
  thread_id: string | null;
  message_id: string | null;
  created_at: string;
}

// === API ===

export async function getArtifacts(
  projectId: string,
): Promise<ListResponse<Artifact>> {
  // UI без постраничной подгрузки: берём максимум за один запрос
  return (
    await apiClient.get(`/projects/${projectId}/artifacts`, {
      params: { limit: 200 },
    })
  ).data;
}

export async function getArtifact(
  projectId: string,
  artifactId: string,
): Promise<ArtifactDetail> {
  return (await apiClient.get(`/projects/${projectId}/artifacts/${artifactId}`))
    .data;
}

export async function downloadArtifact(
  projectId: string,
  artifactId: string,
  format: "md" | "pdf" = "md",
): Promise<void> {
  const response = await apiClient.get(
    `/projects/${projectId}/artifacts/${artifactId}/download`,
    { params: { format }, responseType: "blob" },
  );
  const blob = new Blob([response.data]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const disposition = response.headers["content-disposition"];
  const filenameMatch = disposition?.match(/filename="?(.+?)"?$/);
  a.download = filenameMatch?.[1] ?? `artifact.${format}`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

// === Hooks ===

export function useArtifacts(projectId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.projects.artifacts(projectId),
    queryFn: () => getArtifacts(projectId!),
    enabled: !!projectId,
  });
}

export function useArtifact(
  projectId: string | undefined,
  artifactId: string | undefined,
) {
  return useQuery({
    queryKey: queryKeys.projects.artifact(projectId, artifactId),
    queryFn: () => getArtifact(projectId!, artifactId!),
    enabled: !!projectId && !!artifactId,
  });
}
