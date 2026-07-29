import { cn } from "@/shared/lib/utils";

/**
 * Бегущие точки живого элемента ленты — утверждённая ось «Точки»
 * (`body.live-dots` мокапа `live-timeline-v3.html`): три точки сразу после
 * подписи активной строки. Приглушённый вариант (`muted`) носит строка-пауза,
 * у которой подписи ещё нет.
 *
 * Анимация — keyframe `feed-dot-bounce` в `index.css`, выключается под
 * `prefers-reduced-motion: reduce`. Декоративны: живость строки читается её
 * подписью и статусом, поэтому точки скрыты от скринридера.
 */
export function LiveDots({ muted = false }: { muted?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className="ml-0.5 flex shrink-0 items-center gap-[3px]"
    >
      {[0, 1, 2].map((index) => (
        <span
          key={index}
          className={cn(
            "feed-dot size-1 rounded-full",
            muted ? "bg-muted-foreground" : "bg-primary",
          )}
        />
      ))}
    </span>
  );
}
