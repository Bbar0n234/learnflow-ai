import { useEffect, useRef, useState } from "react";
import type { Message } from "@/shared/api/chats";
import { groupFeedBlocks, type AgentFeedItem } from "@/shared/lib/agent-feed";
import { useStreamStore } from "@/stores/stream-store";
import { MessageItem } from "./MessageItem";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { ActivityFeed } from "./ActivityFeed";
import { ActivityPauseRow } from "./ActivityPauseRow";
import { ReviewIndicator } from "./ReviewIndicator";
import { StreamEndNotice, type StreamEndReason } from "./StreamEndNotice";

interface MessageListProps {
  messages: Message[];
  isStreaming: boolean;
  /** Лента активного хода — та же структура, что рендерит история. */
  feed: AgentFeedItem[];
  projectId: string;
  chatId: string;
  streamError: string | null;
  /** Чем закончился ход, если он закончился не ответом. */
  endNotice: StreamEndReason | null;
}

/**
 * Порог тишины ленты: столько миллисекунд без единого прибывшего данного — и
 * хвостовой элемент, который поток дописывал чанками, перестаёт считаться
 * идущим.
 *
 * Порог зажат между двумя измеренными величинами. Сверху — heartbeat сервера,
 * 5,00 с: окно, которое сервер сам считает достаточно долгим, чтобы напомнить о
 * себе, экран не должен проживать немым, поэтому порог заметно меньше шага
 * биения. Снизу — темп чанков живого потока, десятки миллисекунд: порог на два
 * порядка выше, поэтому нормальная генерация паузу не зажигает и мигания не
 * даёт. Обе границы наблюдались на живом ходе (кейсы Layer 3, `test-cases.md`).
 */
const FEED_SILENCE_MS = 2000;

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
 * Хвост ленты, если это текст или рассуждение, — единственный элемент, в
 * который поток дописывает чанки. Позиция отвечает только на вопрос «куда
 * придёт следующий чанк»; идут ли данные прямо сейчас, она не знает — это
 * отдельный наблюдаемый признак (`useFeedSilence`).
 */
function chunkTail(feed: AgentFeedItem[]): AgentFeedItem | null {
  const tail = feed.at(-1);
  if (tail === undefined) return null;
  return tail.type === "reasoning" || tail.type === "text" ? tail : null;
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

/**
 * Молчит ли лента дольше порога.
 *
 * Признак наблюдаемый, а не выводимый: «поток дописывает хвост» — это факт
 * прихода данных, и другого носителя у него нет. Статуса у рассуждения и текста
 * в контракте нет (streaming.md § События), а позиция элемента в ленте о
 * поступлении данных не говорит ничего — хвост остаётся хвостом и после того,
 * как в него перестали писать.
 *
 * Носитель факта — идентичность самой ленты. Редьюсер модели иммутабелен и
 * пересоздаёт массив ровно тогда, когда событие в ленте что-то изменило, а
 * событие, её не касающееся (`heartbeat`, `done`), возвращает прежнее состояние
 * и подписчиков не будит вовсе. «Приехали данные» и «приехала новая лента» —
 * одно и то же событие, поэтому отдельного счётчика заводить не нужно.
 *
 * Состояние пишется **только таймером**, то есть отдельной задачей после
 * коммита; на рендере оно лишь сравнивается с текущей лентой. Отсюда оба
 * нужных свойства. Первое: правок состояния на фазе рендера нет — пачка
 * событий, пришедшая вплотную (поток, придержанный дольше порога, отдаёт
 * накопленное разом), остаётся обычной чередой перерисовок и не собирается в
 * цепочку вложенных обновлений. Второе: тишина снимается **тем же кадром**,
 * которым приехали данные, — новая лента отметке уже не равна, и промежуточного
 * кадра с паузой не бывает.
 *
 * Тик — не интервал раз в секунду, а единственный таймер ровно на момент
 * истечения порога: между приходом чанков перерисовывать нечего.
 */
function useFeedSilence(feed: AgentFeedItem[], silenceMs: number): boolean {
  // Лента, на которой отсчёт тишины успел истечь. `null` — ещё ни разу.
  const [silentFeed, setSilentFeed] = useState<AgentFeedItem[] | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => setSilentFeed(feed), silenceMs);
    return () => clearTimeout(timer);
  }, [feed, silenceMs]);

  return silentFeed === feed;
}

export function MessageList({
  messages,
  isStreaming,
  feed,
  projectId,
  chatId,
  streamError,
  endNotice,
}: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const isReviewing = useStreamStore((s) => s.isReviewing);
  const liveBlocks = groupFeedBlocks(feed);
  const size = feedSize(feed);
  const textLength = feedTextLength(feed);
  // Признак поступления данных: новая лента приезжает ровно на событии, которое
  // в ней что-то изменило.
  const silent = useFeedSilence(feed, FEED_SILENCE_MS);
  // Хвост живой ленты — элемент, куда поток дописывает чанки; дописывает ли он
  // в него прямо сейчас, говорит `silent`, а не позиция элемента.
  const activeId = chunkTail(feed)?.id ?? null;
  const writingTail = activeId !== null && !silent;
  // Пауза закрывает любой промежуток живого хода, в котором на экране нет ни
  // одной идущей строки, — не только окно до первого события и не только
  // промежуток между вызовами. Между шагами агент может думать десятки секунд
  // (на проводе в это время идёт heartbeat), и замолчать может как лента
  // целиком, так и её хвостовой текст: строка есть, но в неё уже не пишут.
  // Живость вызова лежит в модели (`status: "running"`), живость хвоста —
  // в факте прихода данных. Ревью — собственный живой элемент, рядом с ним
  // пауза не нужна.
  const showPause = !writingTail && !hasRunningCall(feed) && !isReviewing;
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
                        activeLive={!silent}
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
              {/* Карточек артефактов в живом ходе нет: факт создания виден
                  строкой ленты («Сохраняю артефакт…» со статусом), а полная
                  карточка приезжает после завершения хода из истории
                  (`MessageItem`). Стоя после живых блоков, карточка «плыла» бы
                  вниз с каждым чанком текста. */}
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
