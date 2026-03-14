import { useQuery } from "@tanstack/react-query";
import { getProject } from "@/shared/api/projects";

export function useProject(id: string) {
  return useQuery({
    queryKey: ["projects", id],
    queryFn: () => getProject(id),
  });
}
