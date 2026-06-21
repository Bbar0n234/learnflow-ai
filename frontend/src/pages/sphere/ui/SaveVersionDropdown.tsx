import { useState } from "react";
import { ChevronDown, Check } from "lucide-react";
import { Button } from "@/shared/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/ui/dropdown-menu";
import { cn } from "@/shared/lib/utils";
import {
  type SphereVersionBump,
  MOCK_AGENT_SUGGESTION,
} from "../model/mock-sphere-version";

const BUMP_LABELS: Record<
  SphereVersionBump,
  { label: string; description: string }
> = {
  патч: { label: "Патч", description: "Правки внутри записей" },
  минор: { label: "Минор", description: "Новые записи / раздел" },
  мажор: { label: "Мажор", description: "Реструктуризация / смена тезисов" },
};

/**
 * Дропдаун «Сохранить версию ▾» — T6b семвер-UI (заглушка).
 * Предложение агента предвыбрано и подсвечено лавандой.
 * Никаких сетевых вызовов (группа B, L0.5).
 */
export function SaveVersionDropdown() {
  const [saved, setSaved] = useState<SphereVersionBump | null>(null);

  function handleSave(level: SphereVersionBump) {
    // Mock save — no API call (группа B, L0.5)
    setSaved(level);
    setTimeout(() => setSaved(null), 3000);
  }

  if (saved) {
    return (
      <div className="flex items-center gap-1.5 rounded-md bg-secondary px-3 py-1.5 text-xs font-medium text-secondary-foreground">
        <Check className="h-3.5 w-3.5" />
        Сохранено · {BUMP_LABELS[saved].label.toLowerCase()}
      </div>
    );
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            className="gap-1 border-ring/60 text-ring hover:bg-accent hover:text-accent-foreground"
          />
        }
      >
        Сохранить версию
        <ChevronDown className="h-3.5 w-3.5" />
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>
          Предложение агента:{" "}
          {BUMP_LABELS[MOCK_AGENT_SUGGESTION].label.toLowerCase()}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {(["патч", "минор", "мажор"] as SphereVersionBump[]).map((level) => (
          <DropdownMenuItem
            key={level}
            onClick={() => handleSave(level)}
            className={cn(
              "flex-col items-start gap-0.5",
              level === MOCK_AGENT_SUGGESTION &&
                "bg-secondary text-secondary-foreground",
            )}
          >
            <span className="font-medium">{BUMP_LABELS[level].label}</span>
            <span
              className={cn(
                "text-[11px]",
                level === MOCK_AGENT_SUGGESTION
                  ? "text-secondary-foreground/70"
                  : "text-muted-foreground",
              )}
            >
              {BUMP_LABELS[level].description}
            </span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
