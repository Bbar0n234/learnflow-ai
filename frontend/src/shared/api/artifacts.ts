import { apiClient } from "./client";
import type { Artifact, ArtifactDetail, ListResponse } from "./types";

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
