import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateSphere } from "@/shared/api/sphere";
import type { UpdateSphereRequest } from "@/shared/api/types";

export function useUpdateSphere() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      projectId,
      data,
    }: {
      projectId: string;
      data: UpdateSphereRequest;
    }) => updateSphere(projectId, data),
    onSuccess: (_data, variables) => {
      queryClient.invalidateQueries({
        queryKey: ["projects", variables.projectId, "sphere"],
      });
    },
  });
}
