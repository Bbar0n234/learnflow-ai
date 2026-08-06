import { AlertStatus } from "@/shared/api/security";
import { Badge } from "@/shared/ui/badge";
import { clsx } from "clsx";

interface StatusBadgeProps {
  status: AlertStatus;
  className?: string;
}

const STATUS_CONFIG: Record<AlertStatus, { label: string; className: string }> =
  {
    new: {
      label: "Новое",
      className: "bg-accent/50 text-accent-foreground border-accent",
    },
    acknowledged: {
      label: "Подтверждено",
      className: "bg-muted text-muted-foreground border-border",
    },
    resolved: {
      label: "Решено",
      className: "bg-muted/60 text-foreground border-border",
    },
  };

export function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  return (
    <Badge className={clsx(config.className, className, "border")}>
      {config.label}
    </Badge>
  );
}
