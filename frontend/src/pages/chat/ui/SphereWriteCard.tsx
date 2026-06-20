import { useState } from "react";
import { ChevronDown, ChevronUp, ExternalLink, Pencil } from "lucide-react";
import type { SphereWriteEntry } from "../model/mock-sphere-writes";

interface SphereWriteCardProps {
  entry: SphereWriteEntry;
  onOpenLens?: () => void;
}

export function SphereWriteCard({ entry, onOpenLens }: SphereWriteCardProps) {
  const [expanded, setExpanded] = useState(true);
  const [reverted, setReverted] = useState(false);

  return (
    <div className="overflow-hidden rounded-xl border border-secondary">
      {/* Header — lavender bg */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 bg-secondary px-4 py-2.5 text-left transition-colors hover:bg-secondary/80"
      >
        <span className="min-w-0 flex-1 text-xs font-medium text-secondary-foreground">
          Записано в сферу →{" "}
          <span className="font-semibold">{entry.section}</span>
        </span>
        <span className="shrink-0 rounded-sm bg-secondary-foreground/10 px-2 py-0.5 font-mono text-[10px] text-secondary-foreground">
          {entry.versionFrom} → {entry.versionTo} · {entry.bumpType}
        </span>
        {expanded ? (
          <ChevronUp className="h-3.5 w-3.5 shrink-0 text-secondary-foreground/70" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 shrink-0 text-secondary-foreground/70" />
        )}
      </button>

      {/* Body — diff + actions */}
      {expanded && (
        <div className="bg-card">
          {reverted && (
            <div className="border-b border-border px-4 py-2 text-xs text-muted-foreground">
              Изменение откачено до{" "}
              <span className="font-mono">{entry.versionFrom}</span>
            </div>
          )}
          <div className="overflow-x-auto px-4 py-3">
            {entry.diff.map((line, i) => (
              <div
                key={i}
                className="font-mono text-[11px] leading-5 text-muted-foreground"
              >
                <span className="mr-2 text-mcp-connected font-semibold">+</span>
                {line.replace(/^\+ /, "")}
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2 border-t border-border px-4 py-2.5">
            <button
              onClick={onOpenLens}
              className="inline-flex items-center gap-1 text-xs font-medium text-primary transition-colors hover:text-primary/80"
            >
              <ExternalLink className="h-3 w-3" />
              Открыть в сфере
            </button>
            <span className="text-border select-none">·</span>
            <button className="inline-flex items-center gap-0.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground">
              <Pencil className="h-3 w-3" />
              Подправить
            </button>
            <span className="text-border select-none">·</span>
            <button
              onClick={() => setReverted((v) => !v)}
              className="text-xs font-medium text-destructive-warm transition-colors hover:text-destructive-warm/80"
            >
              {reverted ? "Восстановить" : "Откатить"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
