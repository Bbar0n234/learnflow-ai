/**
 * Проверка ответа перед выдачей — строка ленты того же ряда, что действия
 * агента. Рендерится только по факту пришедшего `final_output_review_started`:
 * пары review-событий на ходе может не быть вовсе, и её отсутствие не должно
 * оставлять ленту в подвешенном состоянии.
 */
export function ReviewIndicator() {
  return (
    <div className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
      <span className="h-4 w-2 shrink-0 animate-pulse rounded-[2px] bg-primary motion-reduce:animate-none" />
      <span>Проверяем ответ...</span>
    </div>
  );
}
