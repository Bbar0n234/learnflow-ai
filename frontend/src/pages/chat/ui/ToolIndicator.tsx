import { Loader2 } from "lucide-react";

interface ToolIndicatorProps {
  toolName: string;
}

export function ToolIndicator({ toolName }: ToolIndicatorProps) {
  return (
    <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
      <Loader2 className="h-3.5 w-3.5 animate-spin" />
      <span>Using {toolName}...</span>
    </div>
  );
}
