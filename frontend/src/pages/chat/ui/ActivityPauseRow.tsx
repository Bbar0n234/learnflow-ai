import { Sparkles } from "lucide-react";

import { LiveDots } from "./LiveDots";

/**
 * Строка-пауза ленты: живёт в любом промежутке хода, где на экране нет идущей
 * строки. Таких промежутков два рода — окно от отправки сообщения до первого
 * события (работают guard и reasoning-модель) и пауза между шагами, когда все
 * строки ленты уже завершились, а следующий шаг ещё не начался. На проводе в
 * это время идёт `heartbeat`, то есть агент работает. Закрывает принцип
 * «молчаливого UX не существует»: в любой момент генерации на экране что-то
 * живёт.
 *
 * Наследует роль снятого индикатора «агент думает», но грамматику берёт у ленты
 * (`.act.pause` мокапа): иконка в кружке плюс приглушённые бегущие точки на
 * месте будущей подписи.
 */
export function ActivityPauseRow() {
  return (
    <div
      role="status"
      aria-label="Агент думает"
      className="flex w-full items-center gap-2.5 py-1 pr-1.5"
    >
      <span className="flex size-[19px] shrink-0 items-center justify-center rounded-full bg-background text-muted-foreground">
        <Sparkles aria-hidden="true" className="size-[15px]" />
      </span>
      <LiveDots tone="muted" />
    </div>
  );
}
