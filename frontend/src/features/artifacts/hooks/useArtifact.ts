import { useQuery } from "@tanstack/react-query";
import { getArtifact } from "@/shared/api/artifacts";

export function useArtifact(
  projectId: string | undefined,
  artifactId: string | undefined,
) {
  return useQuery({
    queryKey: ["projects", projectId, "artifacts", artifactId],
    queryFn: () => getArtifact(projectId!, artifactId!),
    enabled: !!projectId && !!artifactId,
  });
}
