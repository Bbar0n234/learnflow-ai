import { useEffect, useRef } from "react";
import type { Message } from "@/shared/api/chats";
import { groupFeedBlocks, type AgentFeedItem } from "@/shared/lib/agent-feed";
import { useStreamStore, type StreamingArtifact } from "@/stores/stream-store";
import { MessageItem } from "./MessageItem";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { ActivityFeed } from "./ActivityFeed";
import { ActivityPauseRow } from "./ActivityPauseRow";
import { ReviewIndicator } from "./ReviewIndicator";
import { StreamEndNotice, type StreamEndReason } from "./StreamEndNotice";
import { ArtifactCard } from "./ArtifactCard";
import { GeneratingArtifactCard } from "./GeneratingArtifactCard";

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  /** Лента активного хода — та же структура, что рендерит история. */
  feed: AgentFeedItem[];
  streamingArtifacts: StreamingArtifact[];
  projectId: string;
  chatId: string;
  streamError: string | null;
  /** Чем закончился ход, если он закончился не ответом. */
  endNotice: StreamEndReason | null;
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
 * Число строк по всей ленте, включая вложенные: шаги субагента приезжают в
 * `children` строки его вызова, и массив верхнего уровня при этом не меняется —
 * счёта по корню для автопрокрутки не хватает.
 */
function feedSize(feed: AgentFeedItem[]): number {
  let size = 0;
  for (const item of feed) {
    size += 1;
    if (item.type === "tool_call") size += feedSize(item.children);
  }
  return size;
}

/**
 * Объём текста ленты — вторая половина сигнала роста: текст и рассуждения
 * растут внутри одного элемента, не меняя их числа. Считается по всей ленте,
 * включая рассуждения субагента внутри его вызова.
 */
function feedTextLength(feed: AgentFeedItem[]): number {
  let length = 0;
  for (const item of feed) {
    if (item.type === "text" || item.type === "reasoning") {
      length += item.content.length;
    } else if (item.type === "tool_call") {
      length += feedTextLength(item.children);
    }
  }
  return length;
}

export function MessageList({
  messages,
  isStreaming,
  feed,
  streamingArtifacts,
  projectId,
  chatId,
  streamError,
  endNotice,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const isReviewing = useStreamStore((s) => s.isReviewing);
  const liveBlocks = groupFeedBlocks(feed);
  const pendingImages = pendingImageCalls(feed);
  const size = feedSize(feed);
  const textLength = feedTextLength(feed);
  // Хвост живой ленты — единственный элемент, который поток ещё дописывает.
  const activeId = feed.at(-1)?.id ?? null;

  // Прокрутка следует за ростом всей ленты, а не за одним текстом и не за одним
  // её корнем: ход из одних tool-событий, без единого `text_chunk`, уезжал бы за
  // нижнюю границу, а работающий субагент растит только свою вложенную ленту.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, size, textLength, isStreaming, isReviewing, endNotice]);

  return (
    <div className="flex-1 overflow-auto p-6">
      <div
        className="mx-auto flex flex-col gap-4"
        style={{ maxWidth: "var(--content-max-w)" }}
      >
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
            <div className="w-full text-foreground">
              {/* Строка-пауза закрывает окно тишины от отправки сообщения до
                  первого содержательного события: молчаливого UX не бывает. */}
              {liveBlocks.length === 0 &&
                !isReviewing &&
                streamingArtifacts.length === 0 && <ActivityPauseRow />}
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
                        activeId={activeId}
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

        {endNotice !== null && !isStreaming && (
          <StreamEndNotice reason={endNotice} />
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
