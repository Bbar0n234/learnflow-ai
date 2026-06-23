import { useState } from "react";
import { useEvents } from "@/shared/api/security";
import { SecurityFilter } from "./SecurityFilter";
import { SecurityPagination } from "./SecurityPagination";
import { SeverityBadge } from "./SeverityBadge";
import { SecurityEvent, Severity } from "@/shared/api/security";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { Button } from "@/shared/ui/button";
import { getApiErrorMessage } from "@/shared/lib/api-error";

interface EventsFilterState {
  event_type?: string;
  severity?: Severity;
  from_timestamp?: string;
  to_timestamp?: string;
}

export function SecurityEvents() {
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const [filters, setFilters] = useState<EventsFilterState>({});
  const [selectedEvent, setSelectedEvent] = useState<SecurityEvent | null>(
    null,
  );

  const { data, isLoading, error } = useEvents(limit, offset, filters);

  const handleFilterChange = (newFilters: EventsFilterState) => {
    setFilters(newFilters);
    setOffset(0); // Reset to first page
  };

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
        Ошибка загрузки событий: {getApiErrorMessage(error)}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <SecurityFilter
        onFilterChange={handleFilterChange}
        showEventType={true}
      />

      {isLoading ? (
        <div className="text-center py-8 text-muted-foreground">
          Загрузка события...
        </div>
      ) : !data || data.items.length === 0 ? (
        <div className="rounded-lg border border-border bg-card p-8 text-center text-muted-foreground">
          События не найдены
        </div>
      ) : (
        <>
          <div className="rounded-lg border border-border overflow-hidden bg-card">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-muted/40 text-sm font-semibold">
                    <th className="px-4 py-3 text-left">Время</th>
                    <th className="px-4 py-3 text-left">Тип события</th>
                    <th className="px-4 py-3 text-left">Серьезность</th>
                    <th className="px-4 py-3 text-left">Идентификаторы</th>
                    <th className="px-4 py-3 text-left">Действие</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {data.items.map((event) => (
                    <tr
                      key={event.id}
                      className="hover:bg-muted/40 transition-colors"
                    >
                      <td className="px-4 py-3 text-sm">
                        {new Date(event.event_timestamp).toLocaleString(
                          "ru-RU",
                        )}
                      </td>
                      <td className="px-4 py-3 text-sm font-mono">
                        {event.event_type}
                      </td>
                      <td className="px-4 py-3">
                        <SeverityBadge severity={event.severity} />
                      </td>
                      <td className="px-4 py-3 text-sm text-muted-foreground">
                        {event.identifiers.ip && (
                          <div>IP: {event.identifiers.ip}</div>
                        )}
                        {event.identifiers.user_id && (
                          <div>User: {event.identifiers.user_id}</div>
                        )}
                        {!event.identifiers.ip &&
                          !event.identifiers.user_id && (
                            <span className="text-xs">-</span>
                          )}
                      </td>
                      <td className="px-4 py-3">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setSelectedEvent(event)}
                        >
                          Детали
                        </Button>
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

      {/* Detail modal */}
      {selectedEvent && (
        <Dialog
          open={!!selectedEvent}
          onOpenChange={() => setSelectedEvent(null)}
        >
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle>Детали события</DialogTitle>
              <DialogDescription>{selectedEvent.event_type}</DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div className="min-w-0">
                  <span className="font-semibold">Event ID:</span>
                  <p className="text-muted-foreground font-mono text-xs break-all">
                    {selectedEvent.event_id}
                  </p>
                </div>
                <div className="min-w-0">
                  <span className="font-semibold">Тип:</span>
                  <p className="text-muted-foreground">
                    {selectedEvent.event_type}
                  </p>
                </div>
                <div className="min-w-0">
                  <span className="font-semibold">Серьезность:</span>
                  <div className="mt-1">
                    <SeverityBadge severity={selectedEvent.severity} />
                  </div>
                </div>
                <div className="min-w-0">
                  <span className="font-semibold">Время события:</span>
                  <p className="text-muted-foreground">
                    {new Date(selectedEvent.event_timestamp).toLocaleString(
                      "ru-RU",
                    )}
                  </p>
                </div>
              </div>

              <div>
                <span className="font-semibold text-sm">Идентификаторы:</span>
                <pre className="text-xs bg-muted p-3 rounded mt-2 overflow-auto max-h-40 whitespace-pre-wrap break-all">
                  {JSON.stringify(selectedEvent.identifiers, null, 2)}
                </pre>
              </div>

              <div>
                <span className="font-semibold text-sm">Метаданные:</span>
                <pre className="text-xs bg-muted p-3 rounded mt-2 overflow-auto max-h-40 whitespace-pre-wrap break-all">
                  {JSON.stringify(selectedEvent.metadata, null, 2)}
                </pre>
              </div>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}
