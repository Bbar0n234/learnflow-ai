import { useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
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
    <div className="mt-1 flex gap-1">
      <button
        type="button"
        onClick={() => handleClick(true)}
        className={cn(
          "cursor-pointer rounded p-1 transition-colors hover:bg-muted-foreground/10",
          feedback === true ? "text-primary" : "text-muted-foreground/50",
        )}
        aria-label="Like"
      >
        <ThumbsUp className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        onClick={() => handleClick(false)}
        className={cn(
          "cursor-pointer rounded p-1 transition-colors hover:bg-muted-foreground/10",
          feedback === false ? "text-destructive" : "text-muted-foreground/50",
        )}
        aria-label="Dislike"
      >
        <ThumbsDown className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
