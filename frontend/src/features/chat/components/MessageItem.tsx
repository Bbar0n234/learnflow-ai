import type { Message } from "@/shared/api/types";
import { MarkdownRenderer } from "@/shared/components/MarkdownRenderer";
import { cn } from "@/shared/lib/utils";

interface MessageItemProps {
  message: Message;
}

export function MessageItem({ message }: MessageItemProps) {
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
      </div>
    </div>
  );
}
