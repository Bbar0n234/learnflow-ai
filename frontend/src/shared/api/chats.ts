import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import type { Artifact } from "./artifacts";
import type { ListResponse } from "./pagination";
import { queryKeys } from "./query-keys";

// === Types ===

export interface Chat {
  thread_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  security_blocked: boolean;
}

export interface ChatDetail {
  thread_id: string;
  title: string;
  security_blocked: boolean;
  messages: Message[];
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string | null;
  artifacts: Artifact[];
  trace_id?: string | null;
  feedback_score?: boolean | null;
  redacted?: boolean;
}

export interface RecentChat {
  thread_id: string;
  title: string;
  project_id: string;
  project_name: string;
  updated_at: string;
  security_blocked: boolean;
}

export interface CreateChatRequest {
  title?: string;
}

export interface SendMessageRequest {
  content: string;
}

// === API ===

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

// === Hooks ===

export function useChats(projectId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.projects.chats(projectId),
    queryFn: () => getChats(projectId!),
    enabled: !!projectId,
  });
}

export function useChat(
  projectId: string | undefined,
  chatId: string | undefined,
  options?: { refetchOnWindowFocus?: boolean },
) {
  return useQuery({
    queryKey: queryKeys.projects.chat(projectId, chatId),
    queryFn: () => getChat(projectId!, chatId!),
    enabled: !!projectId && !!chatId,
    refetchOnWindowFocus: options?.refetchOnWindowFocus,
  });
}

export function useCreateChat() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      data,
    }: {
      projectId: string;
      data: CreateChatRequest;
    }) => createChat(projectId, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.projects.chats(variables.projectId),
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.chats.recent });
    },
  });
}

export function useRecentChats() {
  return useQuery({
    queryKey: queryKeys.chats.recent,
    queryFn: getRecentChats,
  });
}
