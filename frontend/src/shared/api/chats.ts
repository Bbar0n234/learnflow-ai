import { apiClient } from "./client";
import type {
  Chat,
  ChatDetail,
  CreateChatRequest,
  ListResponse,
  RecentChat,
} from "./types";

export async function getChats(projectId: string): Promise<ListResponse<Chat>> {
  // UI без постраничной подгрузки: берём максимум за один запрос
  return (
    await apiClient.get(`/projects/${projectId}/chats`, {
      params: { limit: 200 },
    })
  ).data;
}

export async function getChat(
  projectId: string,
  chatId: string,
): Promise<ChatDetail> {
  return (await apiClient.get(`/projects/${projectId}/chats/${chatId}`)).data;
}

export async function createChat(
  projectId: string,
  data: CreateChatRequest,
): Promise<Chat> {
  return (await apiClient.post(`/projects/${projectId}/chats`, data)).data;
}

export async function getRecentChats(): Promise<ListResponse<RecentChat>> {
  return (await apiClient.get("/chats/recent", { params: { limit: 10 } })).data;
}

export async function cancelChat(
  projectId: string,
  chatId: string,
): Promise<{ ok: boolean }> {
  return (await apiClient.post(`/projects/${projectId}/chats/${chatId}/cancel`))
    .data;
}
