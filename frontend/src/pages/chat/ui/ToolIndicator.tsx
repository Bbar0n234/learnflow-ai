interface ToolIndicatorProps {
  toolName: string;
}

export function ToolIndicator({ toolName }: ToolIndicatorProps) {
  return (
    <div className="mt-2">
      <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-3 py-1 text-xs font-medium text-secondary-foreground">
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-60" />
        {toolName}
      </span>
    </div>
  );
}
