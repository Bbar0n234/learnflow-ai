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

  const { data, isLoading, error } = useAlerts(limit, offset, {
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
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
        Ошибка загрузки алертов: {getApiErrorMessage(error)}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {successMessage && (
        <div className="rounded-lg border border-green-200 bg-green-50 p-4 text-green-800">
          {successMessage}
        </div>
      )}

      <SecurityFilter
        onFilterChange={handleFilterChange}
        showStatus={true}
        statusOptions={STATUS_OPTIONS}
      />

      {isLoading ? (
        <div className="text-center py-8 text-muted-foreground">
          Загрузка алертов...
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
