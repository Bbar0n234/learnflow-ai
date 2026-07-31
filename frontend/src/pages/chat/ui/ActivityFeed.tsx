import type { AgentFeedItem } from "@/shared/lib/agent-feed";
import { ActivityPauseRow } from "./ActivityPauseRow";
import { ActivityRow } from "./ActivityRow";

interface ActivityFeedProps {
  items: AgentFeedItem[];
  /**
   * Элемент, который дописывается потоком прямо сейчас (хвост живой ленты).
   * История его не знает и не передаёт — сохранённый ход целиком завершён.
   */
  activeId?: string | null;
  /**
   * Дописать в конец ленты строку-паузу: все её строки завершены, а ход
   * продолжается. Живая лента, история — никогда (сохранённый ход завершён).
   */
  pause?: boolean;
}

/**
 * Лента активности: подряд идущие действия агента на общей соединительной нити.
 *
 * Компонент один для истории и для live — структура данных общая
 * (`shared/lib/agent-feed`), поэтому сохранённый ход показывает ровно тот же
 * след действий, который пользователь видел живым.
 */
export function ActivityFeed({
  items,
  activeId = null,
  pause = false,
}: ActivityFeedProps) {
  if (items.length === 0 && !pause) return null;

  return (
    <div className="flex flex-col">
      {items.map((item) => (
        <ActivityRow
          key={item.id}
          item={item}
          active={activeId !== null && item.id === activeId}
        />
      ))}
      {/* Пауза — последняя строка ленты, поэтому нить предыдущей строки
          доводится до неё: `last:before:hidden` снимается сам. */}
      {pause && <ActivityPauseRow />}
    </div>
  );
}
