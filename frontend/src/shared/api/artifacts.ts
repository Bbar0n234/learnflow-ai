import { useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";
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

/**
 * Бинарь image-артефакта с media-endpoint. `Blob.type` уже несёт mime
 * (браузер выставляет его из `Content-Type` при `responseType: "blob"`) —
 * отдельно извлекать заголовок не нужно.
 */
export async function getArtifactMedia(
  projectId: string,
  artifactId: string,
): Promise<Blob> {
  return (
    await apiClient.get(
      `/projects/${projectId}/artifacts/${artifactId}/media`,
      { responseType: "blob" },
    )
  ).data;
}

/**
 * Различает «блоба нет» (404 — легитимное пустое состояние вьюера/карточки)
 * от сетевой/серверной ошибки. Ретраи и так исключены глобальной политикой
 * QueryProvider для всех 4xx (shouldRetryQuery) — здесь только классификация.
 */
export function isArtifactMediaNotFound(error: unknown): boolean {
  return error instanceof AxiosError && error.response?.status === 404;
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

/**
 * Media-ключ общий для карточки ленты (ArtifactCard) и вьюера (ImageViewer):
 * react-query дедуплицирует один запрос на обоих потребителей. Blob
 * иммутабелен по построению (перегенерация создаёт новый артефакт/id) —
 * `staleTime: Infinity`, инвалидация не требуется.
 */
export function useArtifactMedia(
  projectId: string | undefined,
  artifactId: string | undefined,
) {
  return useQuery({
    queryKey: queryKeys.projects.artifactMedia(projectId, artifactId),
    queryFn: () => getArtifactMedia(projectId!, artifactId!),
    enabled: !!projectId && !!artifactId,
    staleTime: Infinity,
  });
}
