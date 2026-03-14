import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateProject } from "@/shared/api/projects";
import type { UpdateProjectRequest } from "@/shared/api/types";

export function useUpdateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: UpdateProjectRequest }) =>
      updateProject(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
