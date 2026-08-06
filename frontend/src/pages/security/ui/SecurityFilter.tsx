import { useState } from "react";
import { Input } from "@/shared/ui/input";
import { Button } from "@/shared/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
import { Severity } from "@/shared/api/security";

interface FilterState {
  event_type?: string;
  severity?: Severity;
  from_timestamp?: string;
  to_timestamp?: string;
}

interface SecurityFilterProps {
  onFilterChange: (filters: FilterState) => void;
  showEventType?: boolean;
  showStatus?: boolean;
  statusOptions?: Array<{ value: string; label: string }>;
}

const SEVERITY_OPTIONS = [
  { value: "info", label: "Информация" },
  { value: "warning", label: "Предупреждение" },
  { value: "critical", label: "Критично" },
];

export function SecurityFilter({
  onFilterChange,
  showEventType = true,
  showStatus = false,
  statusOptions = [],
}: SecurityFilterProps) {
  const [eventType, setEventType] = useState("");
  const [severity, setSeverity] = useState<string>("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [status, setStatus] = useState<string>("");

  const handleFilterChange = () => {
    const filters: FilterState = {};
    if (eventType) filters.event_type = eventType;
    if (severity) filters.severity = severity as Severity;
    if (fromDate) filters.from_timestamp = fromDate;
    if (toDate) filters.to_timestamp = toDate;
    onFilterChange(filters);
  };

  const handleReset = () => {
    setEventType("");
    setSeverity("");
    setFromDate("");
    setToDate("");
    setStatus("");
    onFilterChange({});
  };

  return (
    <div className="space-y-4 rounded-lg border border-border bg-card p-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        {showEventType && (
          <div>
            <label
              htmlFor="filter-event-type"
              className="block text-sm font-medium text-foreground mb-2"
            >
              Тип события
            </label>
            <Input
              id="filter-event-type"
              placeholder="auth.login.failed"
              value={eventType}
              onChange={(e) => setEventType(e.target.value)}
            />
          </div>
        )}

        <div>
          <label
            htmlFor="filter-severity"
            className="block text-sm font-medium text-foreground mb-2"
          >
            Серьезность
          </label>
          <Select
            value={severity}
            onValueChange={(v: string | null) => v !== null && setSeverity(v)}
          >
            <SelectTrigger id="filter-severity">
              <SelectValue placeholder="Все">
                {(value) =>
                  SEVERITY_OPTIONS.find((opt) => opt.value === value)?.label ??
                  "Все"
                }
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">Все</SelectItem>
              {SEVERITY_OPTIONS.map((opt) => (
                <SelectItem key={opt.value} value={opt.value}>
                  {opt.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {showStatus && (
          <div>
            <label
              htmlFor="filter-status"
              className="block text-sm font-medium text-foreground mb-2"
            >
              Статус
            </label>
            <Select
              value={status}
              onValueChange={(v: string | null) => v !== null && setStatus(v)}
            >
              <SelectTrigger id="filter-status">
                <SelectValue placeholder="Все">
                  {(value) =>
                    statusOptions.find((opt) => opt.value === value)?.label ??
                    "Все"
                  }
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="">Все</SelectItem>
                {statusOptions.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        <div>
          <label
            htmlFor="filter-from"
            className="block text-sm font-medium text-foreground mb-2"
          >
            От
          </label>
          <Input
            id="filter-from"
            type="datetime-local"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
          />
        </div>

        <div>
          <label
            htmlFor="filter-to"
            className="block text-sm font-medium text-foreground mb-2"
          >
            До
          </label>
          <Input
            id="filter-to"
            type="datetime-local"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
          />
        </div>
      </div>

      <div className="flex gap-2 justify-end">
        <Button variant="outline" onClick={handleReset}>
          Сброс
        </Button>
        <Button onClick={handleFilterChange}>Применить</Button>
      </div>
    </div>
  );
}
