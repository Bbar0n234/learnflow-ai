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
      className: "bg-blue-100 text-blue-800 border-blue-200",
    },
    warning: {
      label: "Предупреждение",
      className: "bg-yellow-100 text-yellow-800 border-yellow-200",
    },
    critical: {
      label: "Критично",
      className: "bg-red-100 text-red-800 border-red-200",
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
