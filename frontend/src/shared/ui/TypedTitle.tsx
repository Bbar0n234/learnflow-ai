import { useEffect, useRef, useState } from "react";
import { cn } from "@/shared/lib/utils";

// Тайминги и оформление — из мокапа (chat-ux.html: applyTitle/typeInto,
// .type-caret): ~38 мс на символ, подсветка `--primary` держится ~0.7с после
// конца печати и гаснет через `transition-colors`.
const TYPE_INTERVAL_MS = 38;
const HIGHLIGHT_HOLD_MS = 700;

interface TypedTitleProps {
  /** Актуальное значение title из кэша — единственный источник истины. */
  text: string;
  /**
   * Значение, с которого запускается печать (обычно доменный плейсхолдер,
   * например `DEFAULT_CHAT_TITLE`). Печать анимирует ровно переход
   * `animateFrom → text`; любой другой переход (rename, обычный рендер уже
   * готового названия) отображается мгновенно, без анимации.
   */
  animateFrom: string;
  className?: string;
  /** HTML-тег обёртки — компонент домен-нейтрален, хосты используют разную семантику. */
  as?: "span" | "p";
}

/**
 * TypedTitle — презентационная надстройка над кэшем title чата.
 *
 * Не читает и не пишет кэш сам: только отрисовывает переход между двумя
 * переданными пропами значениями. Атомарность обновления кэша обеспечивают
 * `title_updated`/`useUpdateChat` (см. design-brief § Доставка title на
 * фронт) — эта анимация лишь презентационный слой поверх них.
 */
export function TypedTitle({
  text,
  animateFrom,
  className,
  as: Tag = "span",
}: TypedTitleProps) {
  const [displayed, setDisplayed] = useState(text);
  const [typing, setTyping] = useState(false);
  const [highlighted, setHighlighted] = useState(false);
  const prevTextRef = useRef(text);

  useEffect(() => {
    const prev = prevTextRef.current;
    prevTextRef.current = text;
    if (prev === text) return;

    // Печать запускается только на замене плейсхолдера сгенерированным
    // названием (prev === animateFrom); rename и прочие переходы — мгновенно.
    if (prev !== animateFrom) {
      setDisplayed(text);
      setTyping(false);
      setHighlighted(false);
      return;
    }

    const reduceMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) {
      setDisplayed(text);
      setTyping(false);
      setHighlighted(false);
      return;
    }

    let i = 0;
    let highlightTimeout: ReturnType<typeof setTimeout> | undefined;
    setDisplayed("");
    setTyping(true);
    setHighlighted(true);
    const interval = setInterval(() => {
      i++;
      setDisplayed(text.slice(0, i));
      if (i >= text.length) {
        clearInterval(interval);
        setTyping(false);
        highlightTimeout = setTimeout(
          () => setHighlighted(false),
          HIGHLIGHT_HOLD_MS,
        );
      }
    }, TYPE_INTERVAL_MS);

    return () => {
      clearInterval(interval);
      if (highlightTimeout) clearTimeout(highlightTimeout);
    };
  }, [text, animateFrom]);

  return (
    <Tag
      className={cn(
        "transition-colors duration-[400ms]",
        typing && "typed-title-caret",
        className,
        // `text-primary` идёт после `className` хоста намеренно: классы
        // собираются `twMerge`, а он из конфликтующих утилит одной группы
        // оставляет последнюю. Хосты задают собственный цвет текста
        // (`text-foreground` в шапке чата и в списке чатов проекта), поэтому
        // подсветка, стоящая перед ним, вырезалась бы из разметки ещё до DOM —
        // печать оставалась бы неподсвеченной везде, кроме хостов без явного
        // цвета. Каретка (`typed-title-caret`) конфликта не имеет: её цвет
        // задан в CSS, а не утилитой.
        highlighted && "text-primary",
      )}
    >
      {displayed}
    </Tag>
  );
}
