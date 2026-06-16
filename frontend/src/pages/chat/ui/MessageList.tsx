import { useEffect, useRef } from "react";
import type { Message } from "@/shared/api/chats";
import { useStreamStore, type StreamingArtifact } from "@/stores/stream-store";
import { MessageItem } from "./MessageItem";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { ToolIndicator } from "./ToolIndicator";
import { ReviewIndicator } from "./ReviewIndicator";
import { ArtifactCard } from "./ArtifactCard";

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  streamingText: string;
  activeTool: string | null;
  streamingArtifacts: StreamingArtifact[];
  projectId: string;
  chatId: string;
  streamError: string | null;
}

export function MessageList({
  messages,
  isStreaming,
  streamingText,
  activeTool,
  streamingArtifacts,
  projectId,
  chatId,
  streamError,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const isReviewing = useStreamStore((s) => s.isReviewing);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streamingText, isStreaming, isReviewing]);

  return (
    <div className="flex-1 overflow-auto p-6">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {messages.map((msg) => (
          <MessageItem
            key={msg.id}
            message={msg}
            projectId={projectId}
            chatId={chatId}
          />
        ))}

        {isStreaming && (
          <div className="flex justify-start">
            <div className="max-w-[80%] rounded-lg bg-muted px-4 py-3 text-foreground">
              {streamingText && (
                <MarkdownRenderer isStreaming>{streamingText}</MarkdownRenderer>
              )}
              {activeTool && <ToolIndicator toolName={activeTool} />}
              {isReviewing && !activeTool && <ReviewIndicator />}
              {streamingArtifacts.map((artifact) => (
                <ArtifactCard
                  key={artifact.id}
                  artifact={artifact}
                  projectId={projectId}
                />
              ))}
            </div>
          </div>
        )}

        {streamError && !isStreaming && (
          <div className="flex justify-start">
            <div className="max-w-[80%] rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {streamError}
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>
    </div>
  );
}
