import type { Message } from "@/shared/api/types";
import { MarkdownRenderer } from "@/shared/components/MarkdownRenderer";
import { cn } from "@/shared/lib/utils";
import { ArtifactCard } from "./ArtifactCard";
import { FeedbackButtons } from "./FeedbackButtons";

interface MessageItemProps {
  message: Message;
  projectId: string;
}

export function MessageItem({ message, projectId }: MessageItemProps) {
  const isUser = message.role === "user";

  return (
    <div className={cn("flex", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-lg px-4 py-3",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-muted text-foreground",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap text-sm">{message.content}</p>
        ) : (
          <MarkdownRenderer>{message.content}</MarkdownRenderer>
        )}
        {!isUser &&
          message.artifacts.map((artifact) => (
            <ArtifactCard
              key={artifact.id}
              artifact={artifact}
              projectId={projectId}
            />
          ))}
        {!isUser && message.trace_id && (
          <FeedbackButtons
            traceId={message.trace_id}
            initialScore={message.feedback_score}
          />
        )}
      </div>
    </div>
  );
}
