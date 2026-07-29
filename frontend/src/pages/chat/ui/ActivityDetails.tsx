import { useState, type ReactNode } from "react";
import { parseToolArgs, type ToolArgs } from "@/shared/config/agent-tools";
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

/**
 * Грубая оценка объёма на клиенте: числа токенов сервер не отдаёт, а усечение и
 * разметка — клиентские (аннотация мокапа). ~3 знака на токен — компромисс между
 * кириллицей (2–3) и латиницей с JSON (~4); оценка и подписана «~».
 */
const CHARS_PER_TOKEN = 3;

function estimateTokens(text: string): string {
  const tokens = Math.max(1, Math.round(text.length / CHARS_PER_TOKEN));
  return tokens.toLocaleString("ru-RU");
}

/**
 * Заголовок зоны. При усечении рядом с ним стоит маркер: показанное — не всё,
 * иначе кнопка раскрытия обещает больше, чем есть. Полные данные отдавать
 * нельзя (scope), обозначить факт — обязательно.
 */
function ZoneTitle({
  title,
  truncated,
}: {
  title: string;
  truncated: boolean;
}) {
  return (
    <div className="mb-0.5 flex items-center gap-2">
      <span className="text-[9.5px] uppercase tracking-[0.08em] opacity-60">
        {title}
      </span>
      {truncated && (
        <span className="rounded-full bg-muted px-1.5 py-px text-[10px] text-muted-foreground">
          обрезано сервером
        </span>
      )}
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
    ? `Показать всё, что пришло · ~${estimateTokens(text)} токенов`
    : `Показать полностью · ~${estimateTokens(text)} токенов`;

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

export function ToolCallDetails({ item }: { item: ToolCallFeedItem }) {
  const args = parseToolArgs(item.args, item.argsTruncated);
  const result = item.result ?? "";
  const hasResult = result !== "";

  return (
    <div className="divide-y divide-border/60">
      <Zone>
        <ZoneTitle title="Вызов" truncated={item.argsTruncated} />
        <p className="font-mono text-[11px] opacity-85">{item.tool}</p>
        {args !== null && <BigText mono text={formatArgs(args)} />}
        {args === null && item.argsTruncated && (
          <p className="mt-0.5">Аргументы оборваны сервером — не разобраны.</p>
        )}
        {/* Args не разобрались вне усечения — строка не битая обрезкой,
            показываем её сырой: это всё, что известно о входе вызова. */}
        {args === null && !item.argsTruncated && item.args !== null && (
          <BigText mono text={item.args} />
        )}
      </Zone>
      {(hasResult || item.status === "pending") && (
        <Zone>
          <ZoneTitle
            title="Результат"
            truncated={hasResult && item.resultTruncated}
          />
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

export function ReasoningDetails({ content }: { content: string }) {
  return (
    <Zone>
      <BigText text={content} />
    </Zone>
  );
}
