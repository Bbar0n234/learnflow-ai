import { useQuery } from "@tanstack/react-query";
import { getSphere } from "@/shared/api/sphere";

export function useSphere(projectId: string | undefined) {
  return useQuery({
    queryKey: ["projects", projectId, "sphere"],
    queryFn: () => getSphere(projectId!),
    enabled: !!projectId,
  });
}
