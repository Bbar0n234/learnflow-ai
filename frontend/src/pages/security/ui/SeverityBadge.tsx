import { Severity } from "@/shared/api/security";
import { Badge } from "@/shared/ui/badge";
import { clsx } from "clsx";

interface SeverityBadgeProps {
  severity: Severity;
  className?: string;
}

const SEVERITY_CONFIG: Record<Severity, { label: string; className: string }> =
  {
    info: {
      label: "Информация",
      className: "bg-accent/50 text-accent-foreground border-accent",
    },
    warning: {
      label: "Предупреждение",
      className: "bg-muted text-muted-foreground border-border",
    },
    critical: {
      label: "Критично",
      className: "bg-destructive/15 text-destructive border-destructive/30",
    },
  };

export function SeverityBadge({ severity, className }: SeverityBadgeProps) {
  const config = SEVERITY_CONFIG[severity];
  return (
    <Badge className={clsx(config.className, className, "border")}>
      {config.label}
    </Badge>
  );
}
