import { useEffect, useRef } from "react";
import type { Message } from "@/shared/api/types";
import type { StreamingArtifact } from "@/stores/stream-store";
import { MessageItem } from "./MessageItem";
import { MarkdownRenderer } from "@/shared/components/MarkdownRenderer";
import { ToolIndicator } from "./ToolIndicator";
import { ArtifactCard } from "./ArtifactCard";

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  streamingText: string;
  activeTool: string | null;
  streamingArtifacts: StreamingArtifact[];
  projectId: string;
  streamError: string | null;
}

export function MessageList({
  messages,
  isStreaming,
  streamingText,
  activeTool,
  streamingArtifacts,
  projectId,
  streamError,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streamingText, isStreaming]);

  return (
    <div className="flex-1 overflow-auto p-6">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {messages.map((msg) => (
          <MessageItem key={msg.id} message={msg} />
        ))}

        {isStreaming && (
          <div className="flex justify-start">
            <div className="max-w-[80%] rounded-lg bg-muted px-4 py-3 text-foreground">
              {streamingText && (
                <MarkdownRenderer isStreaming>{streamingText}</MarkdownRenderer>
              )}
              {activeTool && <ToolIndicator toolName={activeTool} />}
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
