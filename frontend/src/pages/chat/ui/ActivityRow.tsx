import { useState, type ReactNode } from "react";
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

/**
 * Строка действия ленты: иконка на соединительной нити, подпись из реестра
 * инструментов с аргументом, справа — длительность выполнения и статус, дальше
 * шеврон и разворот по клику. Строка без деталей не разворачивается и кнопкой
 * не притворяется.
 *
 * Разметка — по мокапу `live-timeline-v3.html` (оси «Точки» + «Метки»); живые
 * состояния (бегущие точки, счётчик времени) поверх этой строки добавляет T2.5.
 */

/** Единственный `agent_event`, дающий строку: у компакции нет своего вызова. */
const COMPACTION_LABEL = "Сжал историю диалога";

interface RowView {
  icon: LucideIcon;
  label: string;
  arg: string | null;
  /** `null` — у строки нет статуса выполнения (рассуждения, системное событие). */
  status: FeedItemStatus | null;
  durationMs: number | null;
  details: ReactNode | null;
}

function rowView(item: AgentFeedItem): RowView | null {
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
        label: "Рассуждения",
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

export function ActivityRow({ item }: { item: AgentFeedItem }) {
  const [open, setOpen] = useState(false);
  const view = rowView(item);
  if (view === null) return null;

  const expandable = view.details !== null;
  const duration =
    view.durationMs === null || view.status === "running"
      ? null
      : formatDuration(view.durationMs);

  const row = (
    <>
      <span className="z-10 flex size-[19px] shrink-0 items-center justify-center rounded-full bg-background text-muted-foreground">
        <view.icon aria-hidden="true" className="size-[15px]" />
      </span>
      <span className="min-w-0 truncate text-[13.5px] text-muted-foreground">
        {view.label}
        {view.arg !== null && <span> · {view.arg}</span>}
      </span>
      <span className="ml-auto flex shrink-0 items-center gap-[7px] text-xs text-muted-foreground">
        {duration !== null && (
          <span className="font-mono text-[11px]">{duration}</span>
        )}
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
          onClick={() => setOpen((value) => !value)}
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
