import { useQuery } from "@tanstack/react-query";
import { getChats } from "@/shared/api/chats";

export function useChats(projectId: string | undefined) {
  return useQuery({
    queryKey: ["projects", projectId, "chats"],
    queryFn: () => getChats(projectId!),
    enabled: !!projectId,
  });
}
