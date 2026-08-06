import { useEffect, useState, type ReactNode } from "react";
import {
  Check,
  ChevronRight,
  Layers,
  Sparkles,
  X,
  type LucideIcon,
} from "lucide-react";
import {
  describeToolCall,
  SUBAGENT_TOOL_NAME,
} from "@/shared/config/agent-tools";
import type { AgentFeedItem, FeedItemStatus } from "@/shared/lib/agent-feed";
import { cn } from "@/shared/lib/utils";
import {
  ReasoningDetails,
  SubagentDetails,
  ToolCallDetails,
} from "./ActivityDetails";
import { LiveDots } from "./LiveDots";

/**
 * Строка действия ленты: иконка на соединительной нити, подпись из реестра
 * инструментов с аргументом, справа — длительность выполнения и статус, дальше
 * шеврон и разворот по клику. Строка без деталей не разворачивается и кнопкой
 * не притворяется.
 *
 * Живая строка (`status: "running"`, а у рассуждений — пара признаков
 * `active` + `live`) дописывает к этому бегущие точки и счётчик времени: по
 * мокапу `live-timeline-v3.html` (оси «Точки» + «Метки»).
 *
 * Строка `run_subagent` — та же грамматика в лавандовом тоне: в развороте, кроме
 * задания и ответа, живёт вложенная лента шагов субагента (`.act.sub` мокапа).
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
  /** Строка субагента: лавандовая нить и своя лента шагов в развороте. */
  subagent: boolean;
}

function rowView(item: AgentFeedItem, active: boolean): RowView | null {
  switch (item.type) {
    case "tool_call": {
      const described = describeToolCall(item.tool, {
        args: item.args,
        truncated: item.argsTruncated,
      });
      const subagent = item.tool === SUBAGENT_TOOL_NAME;
      return {
        icon: described.icon,
        label: described.label,
        arg: described.arg,
        status: item.status,
        durationMs: item.durationMs,
        subagent,
        details: subagent ? (
          <SubagentDetails item={item}>
            <SubagentSteps items={item.children} />
          </SubagentDetails>
        ) : (
          <ToolCallDetails item={item} />
        ),
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
        subagent: false,
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
        subagent: false,
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
      return (
        <>
          <X aria-hidden="true" className="size-3.5 text-destructive" />
          <span className="sr-only">ошибка</span>
        </>
      );
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
   * Хвост живой ленты: элемент, в который поток дописывает чанки. Нужен только
   * строке рассуждений — у вызова живость видна по `status`, а у
   * `reasoning_chunk` своего статуса в контракте нет.
   */
  active?: boolean;
  /**
   * Идут ли данные в хвост прямо сейчас. Позиция говорит, куда придёт
   * следующий чанк, но не о том, что он идёт: рассуждение замолкает раньше,
   * чем за ним встанет следующая строка, и на это время оно такой же
   * законченный след, как рассуждение в истории. Разворот при этом остаётся
   * открытым (`open` ниже) — прятать уже показанный текст на паузе значило бы
   * отнимать у пользователя то, что он читает.
   */
  live?: boolean;
  /**
   * Строка вложенной ленты субагента: своей соединительной нити не рисует —
   * нить вложенной ленты одна, лавандовая, и её держит подложка разворота.
   */
  nested?: boolean;
}

/**
 * Вложенная лента субагента: его шаги теми же строками, что и у основного
 * агента. Рендерится рекурсией самой строки — вложенность приезжает единственным
 * признаком `parent_call_id`, и модель уже разложила её в `children`.
 *
 * Синтетической первой строки («получил задание») здесь нет: события под неё в
 * контракте нет, лента начинается с первого реального шага.
 */
function SubagentSteps({ items }: { items: AgentFeedItem[] }) {
  if (items.length === 0) return null;

  return (
    <div className="my-1 flex flex-col">
      {items.map((child) => (
        <ActivityRow key={child.id} item={child} nested />
      ))}
    </div>
  );
}

export function ActivityRow({
  item,
  active = false,
  live = true,
  nested = false,
}: ActivityRowProps) {
  const [manualOpen, setManualOpen] = useState<boolean | null>(null);

  // Строку дописывают прямо сейчас: она хвост ленты и данные в неё идут.
  const writing = active && live;
  const running =
    item.type === "tool_call"
      ? item.status === "running"
      : item.type === "reasoning" && writing;
  const elapsedMs = useElapsed(
    item.type === "tool_call" ? item.startedAt : null,
    running,
  );

  const view = rowView(item, writing);
  if (view === null) return null;

  const expandable = view.details !== null;
  // Развёрнуто, пока лента стоит на этой строке: у рассуждения — чтобы видеть
  // поток чанков, у субагента — чтобы его шаги были видны в момент работы, а не
  // по клику. У рассуждения условие позиционное (`active`), а не `writing`:
  // пауза в потоке гасит подпись и точки, но схлопывать при этом уже
  // показанный текст — прятать от пользователя то, что он читает, и раскрывать
  // обратно на следующем чанке. Решение пользователя старше автоматики.
  const open =
    manualOpen ??
    ((item.type === "reasoning" && active) || (view.subagent && running));

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
          "z-10 flex size-[19px] shrink-0 items-center justify-center rounded-full",
          nested ? "bg-transparent" : "bg-background",
          running
            ? view.subagent
              ? "text-brand-lavender"
              : "text-primary"
            : "text-muted-foreground",
        )}
      >
        <view.icon aria-hidden="true" className="size-[15px]" />
      </span>
      <span
        className={cn(
          "min-w-0 truncate",
          nested ? "text-[12.5px]" : "text-[13.5px]",
          running ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {view.label}
        {view.arg !== null && (
          <span className="text-muted-foreground"> · {view.arg}</span>
        )}
      </span>
      {running && <LiveDots tone={view.subagent ? "lavender" : "primary"} />}
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

  const rowClass = cn(
    "flex w-full items-center gap-2.5 pr-1.5",
    nested ? "py-0.5" : "py-1",
  );

  return (
    <div
      className={cn(
        "relative",
        // Соединительная нить корневой ленты; у вложенной её роль играет
        // лавандовая подложка разворота субагента.
        !nested &&
          "before:absolute before:bottom-[-2px] before:left-[9px] before:top-[26px] before:w-px before:bg-border before:content-[''] last:before:hidden",
      )}
    >
      {expandable ? (
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setManualOpen(!open)}
          className={cn(rowClass, "rounded-lg text-left hover:bg-muted/55")}
        >
          {row}
        </button>
      ) : (
        <div className={rowClass}>{row}</div>
      )}
      {expandable && open && (
        <div
          className={cn(
            "mb-1.5 ml-[29px] mt-0.5 border-l-2 text-xs leading-relaxed text-muted-foreground",
            view.subagent
              ? "rounded-r-lg border-brand-lavender bg-brand-lavender/[0.06] px-3 py-[7px]"
              : "border-border pl-3",
          )}
        >
          {view.details}
        </div>
      )}
    </div>
  );
}
