import { Paperclip } from "lucide-react";

/**
 * Оверлей drag&drop композера (мокап `mockups/attachments-artifacts.html`,
 * блок 1, `.drag-overlay`) — рисуется поверх композера, пока `useFileDrop`
 * держит `isDragging`. `pointer-events-none`: события drag продолжает ловить
 * контейнер композера (`dragHandlers` навешаны на него, не на оверлей), иначе
 * оверлей перекрыл бы их собственным элементом и `dragleave`/`drop` перестали
 * бы доходить до контейнера.
 */
export function DragOverlay() {
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center gap-2 rounded-[var(--radius)] border-2 border-dashed border-ring bg-background/85 text-sm font-medium text-secondary-foreground"
    >
      <Paperclip className="h-[18px] w-[18px]" />
      Отпустите, чтобы прикрепить
    </div>
  );
}
