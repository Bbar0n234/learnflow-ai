import type { Message } from "@/shared/api/chats";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { fromMessageParts, groupFeedBlocks } from "@/shared/lib/agent-feed";
import { cn } from "@/shared/lib/utils";
import { ActivityFeed } from "./ActivityFeed";
import { ArtifactCard } from "./ArtifactCard";
import { FeedbackButtons } from "./FeedbackButtons";

interface MessageItemProps {
  message: Message;
  projectId: string;
  chatId: string;
}

export function MessageItem({ message, projectId, chatId }: MessageItemProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-[14px_4px_14px_14px] bg-bubble-user px-4 py-3 text-foreground dark:border dark:border-border">
          {message.redacted ? (
            <p className="whitespace-pre-wrap text-sm italic opacity-70">
              [Сообщение скрыто в целях безопасности]
            </p>
          ) : (
            <p className="whitespace-pre-wrap text-sm">{message.content}</p>
          )}
        </div>
      </div>
    );
  }

  // След работы агента из истории (streaming.md § История: typed parts). Пусто —
  // старый кэш или degraded-ответ: рендерим плоский `content`, как до итерации.
  // Ход из одного текста тоже даёт единственный текстовый блок и ленты не
  // получает — ни пустого контейнера, ни строки «Ответил» ради симметрии.
  const blocks = groupFeedBlocks(fromMessageParts(message.parts));

  return (
    <div className={cn("flex justify-start")}>
      <div className="w-full text-foreground">
        {message.redacted ? (
          <p className="whitespace-pre-wrap text-sm italic opacity-70">
            [Сообщение скрыто в целях безопасности]
          </p>
        ) : blocks.length > 0 ? (
          <div className="flex flex-col gap-2">
            {blocks.map((block, index) =>
              block.type === "text" ? (
                <MarkdownRenderer key={block.item.id}>
                  {block.item.content}
                </MarkdownRenderer>
              ) : (
                <ActivityFeed
                  key={block.items[0]?.id ?? `feed-${index}`}
                  items={block.items}
                />
              ),
            )}
          </div>
        ) : (
          <MarkdownRenderer>{message.content}</MarkdownRenderer>
        )}
        {message.artifacts.map((artifact) => (
          <ArtifactCard
            key={artifact.id}
            artifact={artifact}
            projectId={projectId}
          />
        ))}
        {message.trace_id && (
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
