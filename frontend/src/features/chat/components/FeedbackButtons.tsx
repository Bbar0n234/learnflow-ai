import { useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { submitFeedback } from "@/shared/api/feedback";
import { logger } from "@/shared/lib/logger";
import { cn } from "@/shared/lib/utils";

interface FeedbackButtonsProps {
  traceId: string;
  initialScore?: boolean | null;
}

export function FeedbackButtons({
  traceId,
  initialScore = null,
}: FeedbackButtonsProps) {
  const [feedback, setFeedback] = useState<boolean | null>(initialScore);

  function handleClick(value: boolean) {
    const next = feedback === value ? null : value;
    setFeedback(next);
    submitFeedback(traceId, next).catch((err) => {
      logger.warn("[feedback error]", err);
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
