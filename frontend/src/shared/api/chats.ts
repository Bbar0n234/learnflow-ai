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

/**
 * Typed parts ассистентского сообщения — след работы агента, собранный из
 * чекпоинтера (streaming.md § История: typed parts). Один ход агента = одно
 * сообщение с упорядоченной последовательностью частей.
 *
 * `status: "pending"` — третье значение, которого нет в SSE-контракте: вызов
 * без парного результата, ход оборвался (отмена, ошибка). `args` — JSON-строка,
 * а не объект, и при `args_truncated: true` она обрезана посреди JSON и
 * невалидна. Аргументы и результат усекаются независимо, поэтому флага два.
 */
export type MessagePart =
  | { type: "reasoning"; content: string }
  | { type: "text"; content: string }
  | {
      type: "tool_call";
      call_id: string;
      tool: string;
      args: string;
      args_truncated: boolean;
      status: "success" | "error" | "pending";
      result_preview: string;
      result_truncated: boolean;
    };

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string | null;
  artifacts: Artifact[];
  trace_id?: string | null;
  feedback_score?: boolean | null;
  redacted?: boolean;
  /**
   * Поле обязано переживать отсутствие в ответе: старые кэши и degraded-случаи
   * дают пустой список, и сообщение рендерится по плоскому `content`.
   */
  parts?: MessagePart[];
}

export interface RecentChat {
  thread_id: string;
  title: string;
  project_id: string;
  project_name: string;
  updated_at: string;
  security_blocked: boolean;
}

export interface UpdateChatRequest {
  title: string;
}

export interface SendMessageRequest {
  content: string;
}

// === Domain constants ===

// Плейсхолдер названия нового чата — пользователь его больше не задаёт,
// сервер ставит то же значение при создании (§ Целевой UX design-brief'а).
export const DEFAULT_CHAT_TITLE = "Новый чат";

// Предел длины названия чата — согласован с серверной Pydantic-валидацией (T1).
export const CHAT_TITLE_MAX_LENGTH = 100;

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

export async function createChat(projectId: string): Promise<Chat> {
  return (await apiClient.post(`/projects/${projectId}/chats`)).data;
}

export async function updateChat(
  projectId: string,
  chatId: string,
  data: UpdateChatRequest,
): Promise<Chat> {
  return (await apiClient.put(`/projects/${projectId}/chats/${chatId}`, data))
    .data;
}

export async function deleteChat(
  projectId: string,
  chatId: string,
): Promise<void> {
  await apiClient.delete(`/projects/${projectId}/chats/${chatId}`);
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
    mutationFn: (projectId: string) => createChat(projectId),
    onSuccess: (_data, projectId) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.projects.chats(projectId),
        exact: true,
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.chats.recent });
    },
  });
}

export function useUpdateChat() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      chatId,
      data,
    }: {
      projectId: string;
      chatId: string;
      data: UpdateChatRequest;
    }) => updateChat(projectId, chatId, data),
    onSuccess: (updated, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.projects.chats(variables.projectId),
        exact: true,
      });
      queryClient.invalidateQueries({ queryKey: queryKeys.chats.recent });
      // Detail открытого чата — точечный патч поля title, не инвалидация:
      // симметрично title_updated (T2.2), чтобы не задеть активный стрим.
      queryClient.setQueryData<ChatDetail>(
        queryKeys.projects.chat(variables.projectId, variables.chatId),
        (prev) => (prev ? { ...prev, title: updated.title } : prev),
      );
    },
  });
}

export function useDeleteChat() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      chatId,
    }: {
      projectId: string;
      chatId: string;
    }) => deleteChat(projectId, chatId),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: queryKeys.projects.chats(variables.projectId),
        exact: true,
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
