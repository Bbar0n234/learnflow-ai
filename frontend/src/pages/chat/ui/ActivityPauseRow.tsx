import { Sparkles } from "lucide-react";

import { LiveDots } from "./LiveDots";

/**
 * Строка-пауза ленты: живёт с нулевой секунды отправки сообщения до первого
 * содержательного события стрима — окно, в котором работают guard и reasoning-
 * модель, а на проводе ещё тишина. Закрывает принцип «молчаливого UX не
 * существует»: в любой момент генерации на экране что-то живёт.
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
      <LiveDots muted />
    </div>
  );
}
