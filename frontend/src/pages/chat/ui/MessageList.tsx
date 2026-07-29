import { Fragment, useEffect, useRef } from "react";
import type { Message } from "@/shared/api/chats";
import { groupFeedBlocks, type AgentFeedItem } from "@/shared/lib/agent-feed";
import { useStreamStore, type StreamingArtifact } from "@/stores/stream-store";
import { MessageItem } from "./MessageItem";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { ActivityFeed } from "./ActivityFeed";
import { ReviewIndicator } from "./ReviewIndicator";
import { ThinkingIndicator } from "./ThinkingIndicator";
import { ArtifactCard } from "./ArtifactCard";
import { GeneratingArtifactCard } from "./GeneratingArtifactCard";
import { SphereWriteCard } from "./SphereWriteCard";
import { MOCK_SPHERE_WRITES } from "../model/mock-sphere-writes";
import { SHOW_GROUP_B_STUBS } from "@/shared/config/feature-flags";

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  /** Лента активного хода — та же структура, что рендерит история. */
  feed: AgentFeedItem[];
  streamingArtifacts: StreamingArtifact[];
  projectId: string;
  chatId: string;
  streamError: string | null;
  onOpenLens: () => void;
}

/** Инструмент, чей вызов показывается плейсхолдер-карточкой артефакта. */
const IMAGE_TOOL = "generate_image";

/**
 * `call_id` идущих прямо сейчас генераций изображений — карточка-плейсхолдер
 * живёт ровно столько, сколько вызов остаётся незакрытым (`tool_result` /
 * `artifact_created` того же вызова переводят строку из `running`).
 */
function pendingImageCalls(feed: AgentFeedItem[]): string[] {
  const calls: string[] = [];
  for (const item of feed) {
    if (item.type !== "tool_call") continue;
    if (item.tool === IMAGE_TOOL && item.status === "running") {
      calls.push(item.callId);
    }
    calls.push(...pendingImageCalls(item.children));
  }
  return calls;
}

/**
 * Объём хвоста ленты — сигнал роста для автопрокрутки: текст и рассуждения
 * растут внутри одного элемента, не меняя их числа.
 */
function feedTailLength(feed: AgentFeedItem[]): number {
  const last = feed.at(-1);
  if (last === undefined) return 0;
  return last.type === "text" || last.type === "reasoning"
    ? last.content.length
    : 0;
}

export function MessageList({
  messages,
  isStreaming,
  feed,
  streamingArtifacts,
  projectId,
  chatId,
  streamError,
  onOpenLens,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const isReviewing = useStreamStore((s) => s.isReviewing);
  const liveBlocks = groupFeedBlocks(feed);
  const pendingImages = pendingImageCalls(feed);
  const tailLength = feedTailLength(feed);

  // Прокрутка следует за ростом ленты, а не за одним текстом: ход из одних
  // tool-событий, без единого `text_chunk`, тоже уезжал бы за нижнюю границу.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, feed.length, tailLength, isStreaming, isReviewing]);

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
              {liveBlocks.length === 0 &&
                !isReviewing &&
                streamingArtifacts.length === 0 && <ThinkingIndicator />}
              {/* Живой ход рисует тот же компонент ленты, что и история:
                  структура данных общая, поэтому перезагрузка страницы
                  показывает ровно то, что пользователь уже видел. */}
              {liveBlocks.length > 0 && (
                <div className="flex flex-col gap-2">
                  {liveBlocks.map((block, index) =>
                    block.type === "text" ? (
                      <MarkdownRenderer key={block.item.id} isStreaming>
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
              )}
              {isReviewing && <ReviewIndicator />}
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
