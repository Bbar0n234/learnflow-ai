import { useQuery } from "@tanstack/react-query";
import { getRecentChats } from "@/shared/api/chats";

export function useRecentChats() {
  return useQuery({
    queryKey: ["chats", "recent"],
    queryFn: getRecentChats,
  });
}
