import { useState } from "react";
import { ThumbsUp, ThumbsDown, RotateCcw } from "lucide-react";
import {
  deleteFeedback,
  setFeedback as putFeedback,
} from "@/shared/api/feedback";
import { logger } from "@/shared/lib/logger";
import { cn } from "@/shared/lib/utils";

interface FeedbackButtonsProps {
  projectId: string;
  chatId: string;
  traceId: string;
  initialScore?: boolean | null;
}

export function FeedbackButtons({
  projectId,
  chatId,
  traceId,
  initialScore = null,
}: FeedbackButtonsProps) {
  const [feedback, setFeedback] = useState<boolean | null>(initialScore);

  function handleClick(value: boolean) {
    const prevFeedback = feedback;
    const next = feedback === value ? null : value;
    // Optimistic update: set immediately, roll back on error.
    setFeedback(next);
    const request =
      next === null
        ? deleteFeedback(projectId, chatId, traceId)
        : putFeedback(projectId, chatId, traceId, next);
    request.catch((err) => {
      logger.warn("[feedback error]", err);
      setFeedback(prevFeedback); // rollback to previous state
    });
  }

  return (
    <div className="mt-2 flex items-center gap-1">
      <button
        type="button"
        onClick={() => handleClick(true)}
        className={cn(
          "inline-flex cursor-pointer items-center gap-1 rounded px-2 py-1 text-xs transition-colors hover:bg-muted-foreground/10",
          feedback === true ? "text-primary" : "text-muted-foreground",
        )}
        aria-label="Полезно"
      >
        <ThumbsUp className="h-3 w-3" />
        Полезно
      </button>
      <button
        type="button"
        onClick={() => handleClick(false)}
        className={cn(
          "inline-flex cursor-pointer items-center gap-1 rounded px-2 py-1 text-xs transition-colors hover:bg-muted-foreground/10",
          feedback === false ? "text-destructive" : "text-muted-foreground",
        )}
        aria-label="Не то"
      >
        <ThumbsDown className="h-3 w-3" />
        Не то
      </button>
      <button
        type="button"
        onClick={() => {}}
        className="inline-flex cursor-pointer items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-muted-foreground/10"
        aria-label="Перегенерировать"
      >
        <RotateCcw className="h-3 w-3" />
        Перегенерировать
      </button>
    </div>
  );
}
