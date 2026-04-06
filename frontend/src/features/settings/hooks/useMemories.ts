import { useQuery } from "@tanstack/react-query";
import { getMemories } from "@/shared/api/user-memory";

export function useMemories() {
  return useQuery({
    queryKey: ["memories"],
    queryFn: getMemories,
  });
}
