import { apiClient } from "./client";

export async function setFeedback(
  projectId: string,
  chatId: string,
  traceId: string,
  score: boolean,
): Promise<void> {
  await apiClient.put(
    `/projects/${projectId}/chats/${chatId}/feedback/${traceId}`,
    { score },
  );
}

export async function deleteFeedback(
  projectId: string,
  chatId: string,
  traceId: string,
): Promise<void> {
  await apiClient.delete(
    `/projects/${projectId}/chats/${chatId}/feedback/${traceId}`,
  );
}
