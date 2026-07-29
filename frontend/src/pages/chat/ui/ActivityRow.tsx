import { useEffect, useState, type ReactNode } from "react";
import {
  Check,
  ChevronRight,
  Layers,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { describeToolCall } from "@/shared/config/agent-tools";
import type { AgentFeedItem, FeedItemStatus } from "@/shared/lib/agent-feed";
import { cn } from "@/shared/lib/utils";
import { ReasoningDetails, ToolCallDetails } from "./ActivityDetails";
import { LiveDots } from "./LiveDots";

/**
 * Строка действия ленты: иконка на соединительной нити, подпись из реестра
 * инструментов с аргументом, справа — длительность выполнения и статус, дальше
 * шеврон и разворот по клику. Строка без деталей не разворачивается и кнопкой
 * не притворяется.
 *
 * Живая строка (`status: "running"`, а у рассуждений — признак `active`)
 * дописывает к этому бегущие точки и счётчик времени: по мокапу
 * `live-timeline-v3.html` (оси «Точки» + «Метки»).
 */

/** Единственный `agent_event`, дающий строку: у компакции нет своего вызова. */
const COMPACTION_LABEL = "Сжал историю диалога";

/**
 * Порог показа счётчика времени. Короткое действие не нуждается в цифрах —
 * счётчик нужен там, где иначе начинается тишина; ровно те же ~секунды, на
 * которых сервер начинает слать `heartbeat`.
 */
const ELAPSED_VISIBLE_AFTER_MS = 3000;

interface RowView {
  icon: LucideIcon;
  label: string;
  arg: string | null;
  /** `null` — у строки нет статуса выполнения (рассуждения, системное событие). */
  status: FeedItemStatus | null;
  durationMs: number | null;
  details: ReactNode | null;
}

function rowView(item: AgentFeedItem, active: boolean): RowView | null {
  switch (item.type) {
    case "tool_call": {
      const described = describeToolCall(item.tool, {
        args: item.args,
        truncated: item.argsTruncated,
      });
      return {
        icon: described.icon,
        label: described.label,
        arg: described.arg,
        status: item.status,
        durationMs: item.durationMs,
        details: <ToolCallDetails item={item} />,
      };
    }
    case "reasoning":
      return {
        icon: Sparkles,
        // Пока чанки идут — процесс, дальше — его след.
        label: active ? "Рассуждает" : "Рассуждения",
        arg: null,
        status: null,
        durationMs: null,
        details:
          item.content === "" ? null : (
            <ReasoningDetails content={item.content} />
          ),
      };
    case "agent_event":
      return {
        icon: Layers,
        label: COMPACTION_LABEL,
        arg: null,
        status: null,
        durationMs: null,
        details: null,
      };
    case "text":
      // Текст ассистента — отдельный блок прозы (`groupFeedBlocks`), строкой
      // ленты он не рендерится: строки «Ответил» ради симметрии нет.
      return null;
  }
}

/** Длительность выполнения — мета справа у завершённой строки. */
function formatDuration(ms: number): string {
  const seconds = ms / 1000;
  if (seconds < 10) return `${seconds.toFixed(1).replace(".", ",")} с`;
  if (seconds < 60) return `${Math.round(seconds)} с`;
  const total = Math.round(seconds);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/** Счётчик идущего действия — всегда `m:ss`, как в мокапе. */
function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000);
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/**
 * Тикающее «сколько уже идёт». Живёт только пока действие идёт: закрытая строка
 * показывает зафиксированную моделью длительность и таймера не держит.
 */
function useElapsed(startedAt: number | null, running: boolean): number | null {
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!running || startedAt === null) return;
    setNow(Date.now());
    const tick = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(tick);
  }, [running, startedAt]);

  if (!running || startedAt === null) return null;
  return Math.max(0, now - startedAt);
}

/** Статус читается текстом, а не одним цветом. */
function StatusMeta({ status }: { status: FeedItemStatus }) {
  switch (status) {
    case "success":
      return (
        <>
          <Check aria-hidden="true" className="size-3.5" />
          <span className="sr-only">успешно</span>
        </>
      );
    case "error":
      return <span className="text-destructive">ошибка</span>;
    case "pending":
      return <span>не завершён</span>;
    case "cancelled":
      return <span>отменено</span>;
    case "running":
      return null;
  }
}

interface ActivityRowProps {
  item: AgentFeedItem;
  /**
   * Элемент, который прямо сейчас дописывается потоком. Нужен только строке
   * рассуждений: у вызова живость видна по `status`, а у `reasoning_chunk`
   * своего статуса нет — рассуждение закончилось ровно тогда, когда за ним
   * пришло что-то ещё.
   */
  active?: boolean;
}

export function ActivityRow({ item, active = false }: ActivityRowProps) {
  const [manualOpen, setManualOpen] = useState<boolean | null>(null);

  const running =
    item.type === "tool_call"
      ? item.status === "running"
      : item.type === "reasoning" && active;
  const elapsedMs = useElapsed(
    item.type === "tool_call" ? item.startedAt : null,
    running,
  );

  const view = rowView(item, active);
  if (view === null) return null;

  const expandable = view.details !== null;
  // Рассуждение развёрнуто, пока идёт, и сворачивается по завершении; решение
  // пользователя, если оно было, старше автоматики.
  const open = manualOpen ?? (item.type === "reasoning" && active);

  const meta = running
    ? elapsedMs !== null && elapsedMs >= ELAPSED_VISIBLE_AFTER_MS
      ? formatElapsed(elapsedMs)
      : null
    : view.durationMs !== null
      ? formatDuration(view.durationMs)
      : null;

  const row = (
    <>
      <span
        className={cn(
          "z-10 flex size-[19px] shrink-0 items-center justify-center rounded-full bg-background",
          running ? "text-primary" : "text-muted-foreground",
        )}
      >
        <view.icon aria-hidden="true" className="size-[15px]" />
      </span>
      <span
        className={cn(
          "min-w-0 truncate text-[13.5px]",
          running ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {view.label}
        {view.arg !== null && (
          <span className="text-muted-foreground"> · {view.arg}</span>
        )}
      </span>
      {running && <LiveDots />}
      <span className="ml-auto flex shrink-0 items-center gap-[7px] text-xs text-muted-foreground">
        {meta !== null && <span className="font-mono text-[11px]">{meta}</span>}
        {view.status !== null && <StatusMeta status={view.status} />}
        {expandable && (
          <ChevronRight
            aria-hidden="true"
            className={cn(
              "size-3 opacity-70 transition-transform",
              open && "rotate-90",
            )}
          />
        )}
      </span>
    </>
  );

  return (
    <div className="relative before:absolute before:bottom-[-2px] before:left-[9px] before:top-[26px] before:w-px before:bg-border before:content-[''] last:before:hidden">
      {expandable ? (
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setManualOpen(!open)}
          className="flex w-full items-center gap-2.5 rounded-lg py-1 pr-1.5 text-left hover:bg-muted/55"
        >
          {row}
        </button>
      ) : (
        <div className="flex w-full items-center gap-2.5 py-1 pr-1.5">
          {row}
        </div>
      )}
      {expandable && open && (
        <div className="mb-1.5 ml-[29px] mt-0.5 border-l-2 border-border pl-3 text-xs leading-relaxed text-muted-foreground">
          {view.details}
        </div>
      )}
    </div>
  );
}
