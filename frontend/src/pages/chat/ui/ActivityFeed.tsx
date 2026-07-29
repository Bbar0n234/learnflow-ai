import type { AgentFeedItem } from "@/shared/lib/agent-feed";
import { ActivityRow } from "./ActivityRow";

interface ActivityFeedProps {
  items: AgentFeedItem[];
  /**
   * Элемент, который дописывается потоком прямо сейчас (хвост живой ленты).
   * История его не знает и не передаёт — сохранённый ход целиком завершён.
   */
  activeId?: string | null;
}

/**
 * Лента активности: подряд идущие действия агента на общей соединительной нити.
 *
 * Компонент один для истории и для live — структура данных общая
 * (`shared/lib/agent-feed`), поэтому сохранённый ход показывает ровно тот же
 * след действий, который пользователь видел живым.
 */
export function ActivityFeed({ items, activeId = null }: ActivityFeedProps) {
  if (items.length === 0) return null;

  return (
    <div className="flex flex-col">
      {items.map((item) => (
        <ActivityRow
          key={item.id}
          item={item}
          active={activeId !== null && item.id === activeId}
        />
      ))}
    </div>
  );
}
