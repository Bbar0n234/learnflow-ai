import { useQuery } from "@tanstack/react-query";
import { getInstructions } from "@/shared/api/user-memory";

export function useInstructions() {
  return useQuery({
    queryKey: ["instructions"],
    queryFn: getInstructions,
  });
}
