import { useState, type ReactNode } from "react";
import {
  parseToolArgs,
  SUBAGENT_TASK_ARG,
  type ToolArgs,
} from "@/shared/config/agent-tools";
import type { ToolCallFeedItem } from "@/shared/lib/agent-feed";
import { cn } from "@/shared/lib/utils";

/**
 * Разворот строки действия: зоны «Вызов» и «Результат» под микро-заголовками с
 * тонким разделителем (вариант «Метки» мокапа `live-timeline-v3.html`).
 *
 * Содержимое результатов — только raw-текст: rich-рендер по типам вне scope
 * итерации (design-brief § Scope boundaries). Большие значения свёрнуты в три
 * строки с кнопкой раскрытия в прокручиваемую зону.
 */

/** Длина, с которой текст сворачивается в три строки с кнопкой раскрытия. */
const CLAMP_THRESHOLD_CHARS = 160;

/** Заголовок зоны. Факт серверного усечения бейджем не выносится (решение
 * архитектора на приёмке): честность раскрытия несёт формулировка кнопки —
 * «Показать всё, что пришло» не обещает недостающего. */
function ZoneTitle({ title }: { title: string }) {
  return (
    <div className="mb-0.5 flex items-center gap-2">
      <span className="text-[9.5px] uppercase tracking-[0.08em] opacity-60">
        {title}
      </span>
    </div>
  );
}

function Zone({ children }: { children: ReactNode }) {
  return <div className="px-2.5 py-[7px]">{children}</div>;
}

interface BigTextProps {
  text: string;
  /** Текст оборван сервером — кнопка раскрытия не обещает недостающего. */
  truncated?: boolean;
  mono?: boolean;
}

/**
 * Большие данные: clamp в три строки с fade, раскрытие — в прокручиваемую зону
 * фиксированной высоты. Короткий текст показывается целиком без кнопки.
 */
function BigText({ text, truncated = false, mono = false }: BigTextProps) {
  const [full, setFull] = useState(false);
  const textClass = cn(
    "whitespace-pre-wrap break-words",
    mono && "font-mono text-[11px] opacity-85",
  );

  if (text.length <= CLAMP_THRESHOLD_CHARS) {
    return <p className={textClass}>{text}</p>;
  }

  const expandLabel = truncated
    ? "Показать всё, что пришло"
    : "Показать полностью";

  return (
    <div>
      <div className="relative">
        <p
          className={cn(
            textClass,
            full ? "max-h-60 overflow-auto pr-1.5" : "line-clamp-3",
          )}
        >
          {text}
        </p>
        {!full && (
          <span
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 bottom-0 h-6 bg-gradient-to-b from-transparent to-background"
          />
        )}
      </div>
      <button
        type="button"
        onClick={() => setFull((value) => !value)}
        className="mt-0.5 text-[11.5px] text-secondary-foreground hover:underline"
      >
        {full ? "Свернуть" : expandLabel}
      </button>
    </div>
  );
}

/** Аргументы построчно: `ключ: значение`, строки — как есть, остальное — JSON. */
function formatArgs(args: ToolArgs): string {
  return Object.entries(args)
    .map(
      ([key, value]) =>
        `${key}: ${typeof value === "string" ? value : JSON.stringify(value)}`,
    )
    .join("\n");
}

/**
 * Аргументы разобрать не удалось. Обрезанные сервером на экран не идут вовсе —
 * оборванный посреди JSON текст читать нечем; аргументы нештатной формы
 * (обрезки в них нет) показываются сырыми: это всё, что известно о входе.
 */
function UnparsedArgs({ item }: { item: ToolCallFeedItem }) {
  if (item.argsTruncated) {
    return (
      <p className="mt-0.5">Аргументы оборваны сервером — не разобраны.</p>
    );
  }
  if (item.args === null) return null;
  return <BigText mono text={item.args} />;
}

export function ToolCallDetails({ item }: { item: ToolCallFeedItem }) {
  const args = parseToolArgs(item.args, item.argsTruncated);
  const result = item.result ?? "";
  const hasResult = result !== "";

  return (
    <div className="divide-y divide-border/60">
      <Zone>
        <ZoneTitle title="Вызов" />
        <p className="font-mono text-[11px] opacity-85">{item.tool}</p>
        {args !== null ? (
          <BigText mono text={formatArgs(args)} />
        ) : (
          <UnparsedArgs item={item} />
        )}
      </Zone>
      {(hasResult || item.status === "pending") && (
        <Zone>
          <ZoneTitle title="Результат" />
          {hasResult ? (
            <BigText text={result} truncated={item.resultTruncated} />
          ) : (
            <p>Вызов не завершён — результата нет.</p>
          )}
        </Zone>
      )}
    </div>
  );
}

/**
 * Разворот строки субагента: задание на входе, вложенная лента его шагов и
 * ответ на выходе (`.act.sub` мокапа — зоны «вызов» и «ответ субагента» вокруг
 * вложенного `.feed`).
 *
 * Вход и ответ — это args и result самого вызова `run_subagent`, отдельного
 * канала под них в контракте нет. Шаги приходят событиями с `parent_call_id`,
 * поэтому в истории их не бывает вовсе: вложенная лента там пуста и не
 * рисуется, а строка остаётся законченной — задание и вердикт на месте.
 */
export function SubagentDetails({
  item,
  children,
}: {
  item: ToolCallFeedItem;
  /** Вложенная лента шагов; в истории — пусто. */
  children?: ReactNode;
}) {
  const args = parseToolArgs(item.args, item.argsTruncated);
  const taskValue = args?.[SUBAGENT_TASK_ARG];
  const task = typeof taskValue === "string" ? taskValue : null;
  // Остальные аргументы (`agent_type`, вложенные документы) — моношириной
  // рядом с сырым именем: задание идёт прозой, а не парой ключ-значение.
  const rest =
    args === null
      ? null
      : Object.fromEntries(
          Object.entries(args).filter(([key]) => key !== SUBAGENT_TASK_ARG),
        );
  const verdict = item.result ?? "";
  const hasVerdict = verdict !== "";

  return (
    <div className="flex flex-col gap-1">
      <Zone>
        <ZoneTitle title="Вызов" />
        <p className="font-mono text-[11px] opacity-85">{item.tool}</p>
        {rest !== null && Object.keys(rest).length > 0 && (
          <BigText mono text={formatArgs(rest)} />
        )}
        {task !== null && <BigText text={task} />}
        {args === null && <UnparsedArgs item={item} />}
      </Zone>
      {children}
      {(hasVerdict || item.status === "pending") && (
        <Zone>
          <ZoneTitle title="Ответ субагента" />
          {hasVerdict ? (
            <BigText text={verdict} truncated={item.resultTruncated} />
          ) : (
            <p>Субагент не ответил — вызов не завершён.</p>
          )}
        </Zone>
      )}
    </div>
  );
}

export function ReasoningDetails({ content }: { content: string }) {
  return (
    <Zone>
      <BigText text={content} />
    </Zone>
  );
}
