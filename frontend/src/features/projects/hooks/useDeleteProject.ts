import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteProject } from "@/shared/api/projects";

export function useDeleteProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
