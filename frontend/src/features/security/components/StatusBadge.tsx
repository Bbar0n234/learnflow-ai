import { AlertStatus } from "@/types/security";
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
      className: "bg-blue-100 text-blue-800 border-blue-200",
    },
    acknowledged: {
      label: "Подтверждено",
      className: "bg-yellow-100 text-yellow-800 border-yellow-200",
    },
    resolved: {
      label: "Решено",
      className: "bg-green-100 text-green-800 border-green-200",
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
