import { useQuery } from "@tanstack/react-query";
import { getArtifacts } from "@/shared/api/artifacts";

export function useArtifacts(projectId: string | undefined) {
  return useQuery({
    queryKey: ["projects", projectId, "artifacts"],
    queryFn: () => getArtifacts(projectId!),
    enabled: !!projectId,
  });
}
