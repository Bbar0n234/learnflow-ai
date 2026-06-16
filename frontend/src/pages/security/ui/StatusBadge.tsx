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
      className:
        "bg-blue-500/15 text-blue-700 border-blue-500/30 dark:text-blue-400",
    },
    acknowledged: {
      label: "Подтверждено",
      className:
        "bg-yellow-500/15 text-yellow-700 border-yellow-500/30 dark:text-yellow-400",
    },
    resolved: {
      label: "Решено",
      className:
        "bg-green-500/15 text-green-700 border-green-500/30 dark:text-green-400",
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
