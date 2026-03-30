import { useQuery } from "@tanstack/react-query";
import { getChat } from "@/shared/api/chats";

export function useChat(
  projectId: string | undefined,
  chatId: string | undefined,
  options?: { refetchOnWindowFocus?: boolean },
) {
  return useQuery({
    queryKey: ["projects", projectId, "chats", chatId],
    queryFn: () => getChat(projectId!, chatId!),
    enabled: !!projectId && !!chatId,
    refetchOnWindowFocus: options?.refetchOnWindowFocus,
  });
}
