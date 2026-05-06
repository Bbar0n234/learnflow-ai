import { Severity } from "@/types/security";
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
      className:
        "bg-blue-500/15 text-blue-700 border-blue-500/30 dark:text-blue-400",
    },
    warning: {
      label: "Предупреждение",
      className:
        "bg-yellow-500/15 text-yellow-700 border-yellow-500/30 dark:text-yellow-400",
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
