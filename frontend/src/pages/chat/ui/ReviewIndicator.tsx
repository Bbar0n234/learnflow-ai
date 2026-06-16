import { ShieldCheck } from "lucide-react";

export function ReviewIndicator() {
  return (
    <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
      <ShieldCheck className="h-3.5 w-3.5 animate-pulse" />
      <span>Проверяем ответ...</span>
    </div>
  );
}
