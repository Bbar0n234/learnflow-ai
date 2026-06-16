import type { Message } from "@/shared/api/chats";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { cn } from "@/shared/lib/utils";
import { ArtifactCard } from "./ArtifactCard";
import { FeedbackButtons } from "./FeedbackButtons";

interface MessageItemProps {
  message: Message;
  projectId: string;
  chatId: string;
}

export function MessageItem({ message, projectId, chatId }: MessageItemProps) {
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
        {message.redacted ? (
          <p className="whitespace-pre-wrap text-sm italic opacity-70">
            [Сообщение скрыто в целях безопасности]
          </p>
        ) : isUser ? (
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
            projectId={projectId}
            chatId={chatId}
            traceId={message.trace_id}
            initialScore={message.feedback_score}
          />
        )}
      </div>
    </div>
  );
}
