import { Fragment, useEffect, useRef } from "react";
import type { Message } from "@/shared/api/chats";
import { useStreamStore, type StreamingArtifact } from "@/stores/stream-store";
import { MessageItem } from "./MessageItem";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { ToolIndicator } from "./ToolIndicator";
import { ReviewIndicator } from "./ReviewIndicator";
import { ArtifactCard } from "./ArtifactCard";
import { GeneratingArtifactCard } from "./GeneratingArtifactCard";
import { SphereWriteCard } from "./SphereWriteCard";
import { MOCK_SPHERE_WRITES } from "../model/mock-sphere-writes";
import { SHOW_GROUP_B_STUBS } from "@/shared/config/feature-flags";

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  streamingText: string;
  activeTool: string | null;
  streamingArtifacts: StreamingArtifact[];
  projectId: string;
  chatId: string;
  streamError: string | null;
  onOpenLens: () => void;
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
  onOpenLens,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const isReviewing = useStreamStore((s) => s.isReviewing);
  const pendingImages = useStreamStore((s) => s.pendingImages);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, streamingText, isStreaming, isReviewing]);

  return (
    <div className="flex-1 overflow-auto p-6">
      <div
        className="mx-auto flex flex-col gap-4"
        style={{ maxWidth: "var(--content-max-w)" }}
      >
        {messages.map((msg, i) => (
          <Fragment key={msg.id}>
            <MessageItem message={msg} projectId={projectId} chatId={chatId} />
            {/* Inject mock sphere write peek card after 2nd message (group B stub) */}
            {SHOW_GROUP_B_STUBS &&
              i === 1 &&
              MOCK_SPHERE_WRITES.map((entry) => (
                <SphereWriteCard
                  key={entry.id}
                  entry={entry}
                  onOpenLens={onOpenLens}
                />
              ))}
          </Fragment>
        ))}

        {/* When fewer than 2 messages, show demo peek card at end (group B stub) */}
        {SHOW_GROUP_B_STUBS &&
          messages.length < 2 &&
          MOCK_SPHERE_WRITES.map((entry) => (
            <SphereWriteCard
              key={`demo-${entry.id}`}
              entry={entry}
              onOpenLens={onOpenLens}
            />
          ))}

        {isStreaming && (
          <div className="flex justify-start">
            <div className="w-full text-foreground">
              {streamingText && (
                <MarkdownRenderer isStreaming>{streamingText}</MarkdownRenderer>
              )}
              {activeTool && activeTool !== "generate_image" && (
                <ToolIndicator toolName={activeTool} />
              )}
              {isReviewing && !activeTool && <ReviewIndicator />}
              {pendingImages.map((callId) => (
                <GeneratingArtifactCard key={callId} />
              ))}
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
