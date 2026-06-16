import { Trash2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemories } from "@/shared/api/user-memory";
import { deleteMemory } from "@/shared/api/user-memory";
import { queryKeys } from "@/shared/api/query-keys";
import { Button } from "@/shared/ui/button";

export function AgentMemorySection() {
  const { data, isLoading } = useMemories();
  const queryClient = useQueryClient();

  const removeMutation = useMutation({
    mutationFn: (key: string) => deleteMemory(key),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.memories }),
  });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading memories...</p>;
  }

  const items = data?.items ?? [];

  return (
    <div>
      <label className="mb-1 block text-sm font-medium">Agent Memory</label>
      <p className="mb-2 text-xs text-muted-foreground">
        Memories the agent has saved about you.
      </p>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No memories yet. The agent will save notable facts as you interact.
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div key={item.key} className="rounded-md border border-border p-3">
              <div className="flex items-start justify-between">
                <span className="text-sm font-medium">{item.key}</span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => removeMutation.mutate(item.key)}
                  title="Delete memory"
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                {item.description}
              </p>
              <p className="mt-1 text-sm">{item.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
