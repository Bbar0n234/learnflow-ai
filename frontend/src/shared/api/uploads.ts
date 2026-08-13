import { apiClient } from "./client";

// === Types ===

export interface UploadedFile {
  path: string;
}

// === API ===

/**
 * Загружает файл вложения в `uploads/` проекта (design-brief § Вложения
 * пользователя). Только запись: REST-чтения `uploads/` в контракте нет,
 * поэтому data-хука не заводим — вызов императивный, из композера в момент
 * отправки сообщения (§ Тайминг: ничего не уходит на сервер до отправки).
 * Путь в ответе кладётся в тело `POST /messages` рядом с текстом.
 */
export async function uploadFile(
  projectId: string,
  file: File,
): Promise<UploadedFile> {
  const formData = new FormData();
  formData.append("file", file);
  return (await apiClient.post(`/projects/${projectId}/uploads`, formData))
    .data;
}
