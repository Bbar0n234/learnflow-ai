import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createChat } from "@/shared/api/chats";
import type { CreateChatRequest } from "@/shared/api/types";

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
        queryKey: ["projects", variables.projectId, "chats"],
      });
      queryClient.invalidateQueries({ queryKey: ["chats", "recent"] });
    },
  });
}
