import { useState } from "react";
import {
  useAlerts,
  useAcknowledgeAlert,
  useResolveAlert,
} from "@/shared/api/security";
import { SecurityFilter } from "./SecurityFilter";
import { SecurityPagination } from "./SecurityPagination";
import { SeverityBadge } from "./SeverityBadge";
import { StatusBadge } from "./StatusBadge";
import { AlertStatus, Severity } from "@/shared/api/security";
import { Button } from "@/shared/ui/button";
import { ErrorCard } from "@/shared/ui/StateScreen";
import { Skeleton } from "@/shared/ui/skeleton";
import { logger } from "@/shared/lib/logger";
import { getApiErrorMessage } from "@/shared/lib/api-error";

interface AlertsFilterState {
  severity?: Severity;
  status?: AlertStatus;
}

const STATUS_OPTIONS = [
  { value: "new", label: "Новое" },
  { value: "acknowledged", label: "Подтверждено" },
  { value: "resolved", label: "Решено" },
];

export function SecurityAlerts() {
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<AlertsFilterState>({});
  const [successMessage, setSuccessMessage] = useState("");

  const { data, isLoading, error, refetch } = useAlerts(limit, offset, {
    severity: filters.severity,
    status: filters.status,
  });
  const acknowledgeMutation = useAcknowledgeAlert();
  const resolveMutation = useResolveAlert();

  const handleFilterChange = (newFilters: AlertsFilterState) => {
    setFilters(newFilters);
    setOffset(0);
  };

  const handleAcknowledge = async (id: number) => {
    try {
      await acknowledgeMutation.mutateAsync(id);
      setSuccessMessage("Алерт подтвержден");
      setTimeout(() => setSuccessMessage(""), 3000);
    } catch (err) {
      logger.error("Failed to acknowledge alert", err);
    }
  };

  const handleResolve = async (id: number) => {
    try {
      await resolveMutation.mutateAsync(id);
      setSuccessMessage("Алерт решен");
      setTimeout(() => setSuccessMessage(""), 3000);
    } catch (err) {
      logger.error("Failed to resolve alert", err);
    }
  };

  if (error) {
    return (
      <ErrorCard
        message={`Не удалось загрузить алерты: ${getApiErrorMessage(error)}`}
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <div className="space-y-4">
      {successMessage && (
        <div className="rounded-lg border border-border bg-muted p-4 text-foreground">
          {successMessage}
        </div>
      )}

      <SecurityFilter
        onFilterChange={handleFilterChange}
        showStatus={true}
        statusOptions={STATUS_OPTIONS}
      />

      {isLoading ? (
        <div className="rounded-lg border border-border bg-card">
          <div className="divide-y divide-border">
            <div className="flex items-center gap-4 px-4 py-3">
              <Skeleton className="h-3 w-28" />
              <Skeleton className="h-3 w-40" />
              <Skeleton className="h-4 w-16 rounded-full" />
              <Skeleton className="h-3 w-24" />
            </div>
            <div className="flex items-center gap-4 px-4 py-3">
              <Skeleton className="h-3 w-36" />
              <Skeleton className="h-3 w-32" />
              <Skeleton className="h-4 w-16 rounded-full" />
              <Skeleton className="h-3 w-20" />
            </div>
            <div className="flex items-center gap-4 px-4 py-3">
              <Skeleton className="h-3 w-24" />
              <Skeleton className="h-3 w-44" />
              <Skeleton className="h-4 w-16 rounded-full" />
              <Skeleton className="h-3 w-28" />
            </div>
          </div>
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center text-muted-foreground">
          Алерты не найдены
        </div>
      ) : (
        <>
          <div className="rounded-lg border border-border overflow-hidden bg-card">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-muted/40 text-sm font-semibold">
                    <th className="px-4 py-3 text-left">Правило</th>
                    <th className="px-4 py-3 text-left">Серьезность</th>
                    <th className="px-4 py-3 text-left">Статус</th>
                    <th className="px-4 py-3 text-left">Группа</th>
                    <th className="px-4 py-3 text-left">События</th>
                    <th className="px-4 py-3 text-left">Создано</th>
                    <th className="px-4 py-3 text-left">Действия</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.items.map((alert) => (
                    <tr
                      key={alert.id}
                      className="hover:bg-muted/40 transition-colors"
                    >
                      <td className="px-4 py-3 text-sm font-medium">
                        Rule #{alert.rule_id}
                      </td>
                      <td className="px-4 py-3">
                        <SeverityBadge severity={alert.severity} />
                      </td>
                      <td className="px-4 py-3">
                        <StatusBadge status={alert.status} />
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {alert.group_key || "-"}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {alert.matched_events_count}
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {new Date(alert.created_at).toLocaleString("ru-RU")}
                      </td>
                      <td className="px-4 py-3 space-x-2">
                        {alert.status === "new" && (
                          <>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleAcknowledge(alert.id)}
                              disabled={acknowledgeMutation.isPending}
                            >
                              Подтвердить
                            </Button>
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleResolve(alert.id)}
                              disabled={resolveMutation.isPending}
                            >
                              Решить
                            </Button>
                          </>
                        )}
                        {alert.status !== "new" && (
                          <span className="text-xs text-muted-foreground">
                            {alert.status === "acknowledged"
                              ? `Подтверждено ${alert.acknowledged_at ? new Date(alert.acknowledged_at).toLocaleString("ru-RU") : ""}`
                              : `Решено ${alert.resolved_at ? new Date(alert.resolved_at).toLocaleString("ru-RU") : ""}`}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <SecurityPagination
            limit={limit}
            offset={offset}
            total={data.total}
            onLimitChange={setLimit}
            onOffsetChange={setOffset}
          />
        </>
      )}
    </div>
  );
}
