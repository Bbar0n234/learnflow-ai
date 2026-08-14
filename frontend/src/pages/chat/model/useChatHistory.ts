import { useChat } from "@/shared/api/chats";
import { useStreamStore } from "@/stores/stream-store";

/**
 * История чата с гейтом фоновых рефетчей на время активного хода в этом чате.
 *
 * Пока ход идёт, историю не должен обновлять ни один фоновый канал React
 * Query (фокус, mount, reconnect): рефетч привозит серверную копию только что
 * отправленного user-сообщения, пока оптимистичная копия в `ChatThread` ещё
 * висит, — сообщение и лента активности задваиваются на экране до конца хода.
 * Все обновления истории стримящего чата приходят терминальной инвалидацией
 * из `useAgentStream` (done/cancelled/blocked).
 *
 * Гейт живёт здесь, а не в вызывающих компонентах, потому что подписчиков у
 * query двое (`ChatThread` и `ChatHeader`): любой из них рефетчит общий query
 * в обход гейта соседа — так дубль и просачивался через заголовок.
 *
 * Механизм — `staleTime: Infinity`, а не `refetchOn*`-флаги: возврат в
 * стримящий чат из соседнего — это смена queryKey у живого observer'а, а не
 * mount, и `refetchOnMount`-гейт на неё не действует (проверено регрессионным
 * кейсом в `ChatThread.test.tsx`). Freshness же RQ уважает на всех
 * автоматических каналах разом; `invalidateQueries` терминалов помечает
 * stale явно, поэтому обновление после done/cancelled/blocked работает.
 */
export function useChatHistory(
  projectId: string | undefined,
  chatId: string | undefined,
) {
  const isStreaming = useStreamStore(
    (s) => s.streamingChatId === chatId && s.isStreaming,
  );
  return useChat(projectId, chatId, {
    staleTime: isStreaming ? Infinity : 0,
  });
}
