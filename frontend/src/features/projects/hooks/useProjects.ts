import { useQuery } from "@tanstack/react-query";
import { getProjects } from "@/shared/api/projects";

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: getProjects,
  });
}
