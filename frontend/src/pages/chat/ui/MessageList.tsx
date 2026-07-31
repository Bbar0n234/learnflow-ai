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
 * Идёт ли прямо сейчас хоть один вызов — по всей ленте, включая шаги субагента
 * внутри его строки.
 */
function hasRunningCall(feed: AgentFeedItem[]): boolean {
  return feed.some(
    (item) =>
      item.type === "tool_call" &&
      (item.status === "running" || hasRunningCall(item.children)),
  );
}

/**
 * Есть ли в ленте строка, которая прямо сейчас идёт, — признак того, что
 * пользователю уже видно работу агента (бегущие точки, счётчик времени,
 * прибывающий текст).
 *
 * У вызова живость лежит в модели (`status: "running"`), у рассуждения и текста
 * статуса нет вовсе: поток дописывает ровно хвостовой элемент ленты — то же
 * правило, по которому строка рассуждений подписывается «Рассуждает»
 * (`activeId` ниже).
 */
function hasLiveRow(feed: AgentFeedItem[]): boolean {
  const tail = feed.at(-1);
  if (
    tail !== undefined &&
    (tail.type === "reasoning" || tail.type === "text")
  ) {
    return true;
  }
  return hasRunningCall(feed);
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
  // Пауза закрывает любой промежуток живого хода, в котором на экране нет ни
  // одной идущей строки, — не только окно до первого события. Между шагами
  // агент может думать десятки секунд (на проводе в это время идёт heartbeat),
  // и признак «лента пуста» такой промежуток не ловил вовсе: строки были, но
  // все завершённые, то есть неподвижные. Ревью — собственный живой элемент,
  // рядом с ним пауза не нужна.
  const showPause = !hasLiveRow(feed) && !isReviewing;
  const lastBlock = liveBlocks.at(-1);
  // Пауза встаёт последней строкой ленты, когда лента заканчивается блоком
  // действий: тогда она висит на той же соединительной нити, что и шаги до неё.
  // Иначе (лента пуста или заканчивается прозой ответа) — отдельной строкой.
  const pauseInFeed = showPause && lastBlock?.type === "feed";

  // Прокрутка следует за ростом всей ленты, а не за одним текстом и не за одним
  // её корнем: ход из одних tool-событий, без единого `text_chunk`, уезжал бы за
  // нижнюю границу, а работающий субагент растит только свою вложенную ленту.
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [
    messages.length,
    size,
    textLength,
    isStreaming,
    isReviewing,
    showPause,
    endNotice,
  ]);

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
                        pause={pauseInFeed && index === liveBlocks.length - 1}
                      />
                    ),
                  )}
                </div>
              )}
              {/* Строка-пауза вне ленты: до первого события её ещё не к чему
                  прицепить, после прозы ответа — нити тоже нет. */}
              {showPause && !pauseInFeed && <ActivityPauseRow />}
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
