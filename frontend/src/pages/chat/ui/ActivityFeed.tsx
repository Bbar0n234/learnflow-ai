import type { AgentFeedItem } from "@/shared/lib/agent-feed";
import { ActivityRow } from "./ActivityRow";

/**
 * Лента активности: подряд идущие действия агента на общей соединительной нити.
 *
 * Компонент один для истории и для live — структура данных общая
 * (`shared/lib/agent-feed`), поэтому сохранённый ход показывает ровно тот же
 * след действий, который пользователь видел живым.
 */
export function ActivityFeed({ items }: { items: AgentFeedItem[] }) {
  if (items.length === 0) return null;

  return (
    <div className="flex flex-col">
      {items.map((item) => (
        <ActivityRow key={item.id} item={item} />
      ))}
    </div>
  );
}
