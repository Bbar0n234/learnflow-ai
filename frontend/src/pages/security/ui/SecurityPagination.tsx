import { Button } from "@/shared/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
import { ChevronLeft, ChevronRight } from "lucide-react";

interface SecurityPaginationProps {
  limit: number;
  offset: number;
  total: number;
  onLimitChange: (limit: number) => void;
  onOffsetChange: (offset: number) => void;
}

export function SecurityPagination({
  limit,
  offset,
  total,
  onLimitChange,
  onOffsetChange,
}: SecurityPaginationProps) {
  const currentPage = limit > 0 ? Math.floor(offset / limit) + 1 : 1;
  const totalPages = limit > 0 ? Math.ceil(total / limit) : 1;

  const handlePrev = () => {
    if (offset >= limit) {
      onOffsetChange(offset - limit);
    }
  };

  const handleNext = () => {
    if (offset + limit < total) {
      onOffsetChange(offset + limit);
    }
  };

  return (
    <div className="flex items-center justify-between rounded-lg border border-border bg-card p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">
          Записей на странице:
        </span>
        <Select
          value={limit.toString()}
          onValueChange={(v: string | null) =>
            v !== null && onLimitChange(parseInt(v))
          }
        >
          <SelectTrigger className="w-20">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="10">10</SelectItem>
            <SelectItem value="25">25</SelectItem>
            <SelectItem value="50">50</SelectItem>
            <SelectItem value="100">100</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">
          Страница {currentPage} из {totalPages} (всего {total})
        </span>
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="icon-sm"
          onClick={handlePrev}
          disabled={offset === 0}
          aria-label="Предыдущая страница"
        >
          <ChevronLeft className="h-4 w-4" />
        </Button>
        <Button
          variant="outline"
          size="icon-sm"
          onClick={handleNext}
          disabled={offset + limit >= total}
          aria-label="Следующая страница"
        >
          <ChevronRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
