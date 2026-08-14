import { Trash2 } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemories } from "@/shared/api/user-memory";
import { deleteMemory } from "@/shared/api/user-memory";
import { queryKeys } from "@/shared/api/query-keys";
import { Button } from "@/shared/ui/button";
import { LoadingState } from "@/shared/ui/StateScreen";

export function AgentMemorySection() {
  const { data, isLoading } = useMemories();
  const queryClient = useQueryClient();

  const removeMutation = useMutation({
    mutationFn: (key: string) => deleteMemory(key),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: queryKeys.memories }),
  });

  if (isLoading) {
    return <LoadingState label="Загрузка памяти…" className="py-6" />;
  }

  const items = data?.items ?? [];

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <label className="text-sm font-medium text-foreground">
          Память агента
        </label>
        {items.length > 0 && (
          <span className="text-xs text-muted-foreground">
            {items.length} {items.length === 1 ? "запись" : "записей"}
          </span>
        )}
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Факты, которые агент сохранил о вас в ходе общения.
      </p>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Нет записей. Агент будет сохранять важные факты по мере общения.
        </p>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <div
              key={item.key}
              className="rounded-lg border border-border bg-background p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <span className="text-sm font-medium text-foreground">
                    {item.key}
                  </span>
                  <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">
                    {item.description}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  onClick={() => removeMutation.mutate(item.key)}
                  title="Удалить запись"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
              <p className="mt-1 text-sm text-foreground">{item.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
