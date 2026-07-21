/**
 * Мгновенная обратная связь «агент думает»: три пульсирующие точки в позиции
 * будущего ответа ассистента. Показывается с момента отправки сообщения и до
 * первого рендеримого контента стрима (текст, инструмент, review, артефакт) —
 * закрывает окно молчания, пока guard и reasoning-модель работают до первого
 * SSE-события. Чисто клиентское состояние, SSE-контракт не меняется.
 */
export function ThinkingIndicator() {
  return (
    <div
      role="status"
      aria-label="Агент думает"
      className="flex items-center gap-1.5 py-1 text-muted-foreground"
    >
      <span className="thinking-dot h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
      <span className="thinking-dot h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
      <span className="thinking-dot h-1.5 w-1.5 shrink-0 rounded-full bg-current" />
    </div>
  );
}
