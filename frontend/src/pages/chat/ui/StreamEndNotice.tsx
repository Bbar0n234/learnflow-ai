import { ShieldAlert, Square } from "lucide-react";

/**
 * Чем закончился ход, когда он закончился не ответом. Уведомление живёт рядом с
 * лентой, а не внутри неё: лента — содержимое хода, которое после терминального
 * события отдаёт история, а причина остановки в историю не сохраняется вовсе.
 *
 * Обе причины намеренно не красные: ошибка стрима рисуется `destructive`-
 * плашкой в `MessageList`, и отмена с блокировкой обязаны быть отличимы от неё
 * и друг от друга.
 */
export type StreamEndReason = "cancelled" | "blocked";

export function StreamEndNotice({ reason }: { reason: StreamEndReason }) {
  if (reason === "cancelled") {
    return (
      <div
        role="status"
        className="flex items-center gap-2 py-0.5 text-sm text-muted-foreground"
      >
        <Square aria-hidden="true" className="size-2.5 fill-current" />
        <span>Генерация остановлена</span>
      </div>
    );
  }

  // Деталей блокировки нет и быть не может: `security_block` приходит пустым —
  // ни причины, ни слоя детекции на провод не идёт (они остаются в Langfuse и
  // SIEM). Карточка объясняет, почему ход схлопнулся в заглушку и почему ввод
  // заблокирован, и ничего сверх этого не обещает.
  return (
    <div
      role="status"
      className="flex items-start gap-2.5 rounded-lg border border-border bg-muted/40 px-3.5 py-3 text-sm text-muted-foreground"
    >
      <ShieldAlert aria-hidden="true" className="mt-px size-4 shrink-0" />
      <div className="min-w-0">
        <p className="font-medium text-foreground">
          Ход остановлен системой безопасности
        </p>
        <p className="mt-0.5 text-xs">
          Содержимое хода скрыто. Подробности блокировки не раскрываются.
        </p>
      </div>
    </div>
  );
}
