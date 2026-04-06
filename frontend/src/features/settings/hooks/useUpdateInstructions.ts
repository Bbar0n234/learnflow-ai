import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateInstructions } from "@/shared/api/user-memory";

export function useUpdateInstructions() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (content: string) => updateInstructions(content),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["instructions"] });
    },
  });
}
