import { useQuery } from "@tanstack/react-query";
import { AxiosError } from "axios";
import { apiClient } from "./client";
import type { ListResponse } from "./pagination";
import { queryKeys } from "./query-keys";

// === Types ===

export interface Artifact {
  path: string;
  title: string;
  type: string;
  updated_at: string;
}

export interface ArtifactDetail {
  path: string;
  title: string;
  type: string;
  updated_at: string;
  // Отсутствует у бинарного файла (изображение и т.п.) — детали такого
  // артефакта отдают только метаданные, тело берётся с media-endpoint.
  content?: string;
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
  path: string,
): Promise<ArtifactDetail> {
  return (
    await apiClient.get(`/projects/${projectId}/artifacts`, {
      params: { path },
    })
  ).data;
}

export async function downloadArtifact(
  projectId: string,
  path: string,
): Promise<void> {
  const response = await apiClient.get(
    `/projects/${projectId}/artifacts/download`,
    { params: { path }, responseType: "blob" },
  );
  const blob = new Blob([response.data]);
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  const disposition = response.headers["content-disposition"];
  const filenameMatch = disposition?.match(/filename="?(.+?)"?$/);
  // Фолбэк — basename пути (последний сегмент), не жёсткое расширение:
  // путь-идентичность не несёт формата экспорта (`format` из REST уходит).
  a.download = filenameMatch?.[1] ?? (path.split("/").pop() || path);
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
  path: string,
): Promise<Blob> {
  return (
    await apiClient.get(`/projects/${projectId}/artifacts/media`, {
      params: { path },
      responseType: "blob",
    })
  ).data;
}

/**
 * Различает «файла/блоба больше нет» (404 — легитимное пустое состояние
 * вьюера/карточки: путь-идентичность перезаписываема и переименовываема)
 * от сетевой/серверной ошибки. Общий предикат для detail и media — обеим
 * нужна одна и та же классификация. Ретраи и так исключены глобальной
 * политикой QueryProvider для всех 4xx (shouldRetryQuery) — здесь только
 * классификация.
 */
export function isArtifactNotFound(error: unknown): boolean {
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
  path: string | undefined,
) {
  return useQuery({
    queryKey: queryKeys.projects.artifact(projectId, path),
    queryFn: () => getArtifact(projectId!, path!),
    enabled: !!projectId && !!path,
  });
}

/**
 * Media-ключ общий для карточки ленты (ArtifactCard) и вьюера (ImageViewer):
 * react-query дедуплицирует один запрос на обоих потребителей. Путь —
 * перезаписываемая идентичность (в отличие от бывшего UUID), поэтому без
 * `staleTime: Infinity`: свежесть держат точечная инвалидация по SSE
 * (`artifact_created`/`artifact_updated`) и ETag/Last-Modified-ревалидация
 * браузера на media-endpoint.
 */
export function useArtifactMedia(
  projectId: string | undefined,
  path: string | undefined,
) {
  return useQuery({
    queryKey: queryKeys.projects.artifactMedia(projectId, path),
    queryFn: () => getArtifactMedia(projectId!, path!),
    enabled: !!projectId && !!path,
  });
}
