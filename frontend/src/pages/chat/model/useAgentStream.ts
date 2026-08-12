import { useCallback, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { cancelChat } from "@/shared/api/chats";
import { ensureFreshToken } from "@/shared/api/client";
import { queryKeys } from "@/shared/api/query-keys";
import type { Chat, ChatDetail, RecentChat } from "@/shared/api/chats";
import type { ListResponse } from "@/shared/api/pagination";
import type { SSEFrame } from "@/shared/api/sse";
import { isKnownSSEEvent } from "@/shared/api/sse";
import { logger } from "@/shared/lib/logger";
import { getProblemMessageFromBody } from "@/shared/lib/api-error";
import { useStreamStore } from "@/stores/stream-store";

/**
 * Сторож тишины на проводе: соединение считается потерянным после трёх
 * пропущенных heartbeat подряд (streaming.md § Лимиты — сервер шлёт `heartbeat`
 * на каждые 5 с молчания в любой точке рана, включая исполнение инструмента и
 * ревью ответа). Это не лимит на длительность хода: пока heartbeat идёт,
 * сторож перезаводится и молчаливый час работы агента законен.
 */
const SILENCE_TIMEOUT_MS = 15000;

/**
 * Заглушка вместо содержимого хода, заблокированного защитой: тот же текст, что
 * `MessageItem` рисует у redacted-сообщения истории, — на экране пользователь
 * читает именно её, историческую (`shared/lib/agent-feed` → `redactFeed`).
 */
const REDACTED_STUB = "[Сообщение скрыто в целях безопасности]";

/**
 * Уступка макрозадаче между чтениями тела потока.
 *
 * Кадры одного чтения диспетчер разбирает синхронно, и React сводит их в одну
 * перерисовку. Но когда сервер отдаёт накопленное разом, `reader.read()`
 * резолвится уже готовыми данными — то есть микрозадачей, а не задачей
 * ввода-вывода, — и чтения идут вплотную. Каждое из них обновляет стор по
 * sync-lane (`useSyncExternalStore`), поэтому у React после каждого коммита
 * остаётся незакрытая работа: сторож вложенных обновлений (`react-dom`,
 * `NESTED_UPDATE_LIMIT = 50`) не обнуляется ни разу и на пятом десятке чтений
 * подряд бросает исключение. Оно вылетает из применения события, диспетчер
 * принимает его за обрыв соединения — и ход теряется целиком вместе с ответом.
 *
 * Уступка размыкает цепочку: React успевает закоммитить кадр до следующего
 * чтения, счётчик обнуляется. При нормальном стриминге чтения и так упираются в
 * ввод-вывод, и цена уступки — те же миллисекунды, что и без неё.
 *
 * Носитель — `MessageChannel`, а не `setTimeout`: это макрозадача, которую не
 * подменяют фейковые таймеры, поэтому транспорт остаётся независим от того, чем
 * тест двигает время (сторож тишины меряется именно так). Тем же приёмом
 * уступает планировщик самого React.
 */
function yieldToEventLoop(): Promise<void> {
  return new Promise((resolve) => {
    const channel = new MessageChannel();
    channel.port1.onmessage = () => {
      channel.port1.close();
      resolve();
    };
    channel.port2.postMessage(null);
  });
}

interface DoneInfo {
  chatId: string;
  messageId: string | null;
  traceId: string | null;
}

/**
 * Владелец во всех терминальных колбэках: потребитель хука (`ChatThread`) не
 * перемонтируется при смене чата, поэтому колбэки, замкнутые на текущий
 * рендер, не могут сами отличить, какому чату принадлежит завершившийся ход.
 * Владелец — тот `chatId`, что был передан хуку в момент вызова `send()`, а не
 * актуальный проп на момент срабатывания колбэка. Несут его все ветки без
 * исключения, включая не-SSE (таймаут сторожа тишины, не-ok ответ, обрыв без
 * терминального события, исключение в catch) — источник владельца один и тот
 * же везде.
 */
interface UseAgentStreamOptions {
  onDone?: (info: DoneInfo) => void;
  onError?: (ownerChatId: string, detail: string) => void;
  onSecurityBlock?: (ownerChatId: string) => void;
  onCancelled?: (ownerChatId: string) => void;
}

export function useAgentStream(
  projectId: string,
  chatId: string,
  options?: UseAgentStreamOptions,
) {
  const queryClient = useQueryClient();
  const abortRef = useRef<AbortController | null>(null);
  const isCancellingRef = useRef(false);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  // Cleanup on unmount — hard kill + reset store. Неохраняемый сброс: экран
  // ушёл, эфемерное состояние чистится безусловно, без сверки владельца
  // (owner-guard — только для терминалов потока, см. stream-store.ts).
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      useStreamStore.getState().reset();
    };
  }, []);

  const send = useCallback(
    (content: string) => {
      const { startStream, applyEvent, redact, setReviewing, endStream } =
        useStreamStore.getState();

      startStream(chatId);
      isCancellingRef.current = false;

      const controller = new AbortController();
      abortRef.current = controller;

      // Сторож тишины взводится здесь, синхронно и до `fetch`: если ставить его
      // на первое пришедшее событие, сценарий «сервер не вернул даже
      // заголовков» останется без таймаута вовсе — бесконечным ожиданием
      // вместо ошибки. Дальше его перезаводит любое событие потока.
      let timedOut = false;
      let silenceTimer: ReturnType<typeof setTimeout> | undefined;
      const armSilenceWatch = () => {
        clearTimeout(silenceTimer);
        silenceTimer = setTimeout(() => {
          timedOut = true;
          controller.abort();
          endStream(chatId);
          optionsRef.current?.onError?.(chatId, "Превышено время ожидания");
        }, SILENCE_TIMEOUT_MS);
      };
      armSilenceWatch();

      (async () => {
        try {
          const token = await ensureFreshToken();
          if (!token) {
            clearTimeout(silenceTimer);
            endStream(chatId);
            return;
          }

          let response = await fetch(
            `/api/projects/${projectId}/chats/${chatId}/messages`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${token}`,
              },
              body: JSON.stringify({ content }),
              signal: controller.signal,
            },
          );

          // Reactive fallback: 401 → refresh → retry once
          if (response.status === 401) {
            const freshToken = await ensureFreshToken();
            if (!freshToken) {
              clearTimeout(silenceTimer);
              endStream(chatId);
              return;
            }
            response = await fetch(
              `/api/projects/${projectId}/chats/${chatId}/messages`,
              {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  Authorization: `Bearer ${freshToken}`,
                },
                body: JSON.stringify({ content }),
                signal: controller.signal,
              },
            );
          }

          if (!response.ok) {
            clearTimeout(silenceTimer);
            endStream(chatId);
            let body: unknown = null;
            try {
              body = await response.json();
            } catch {
              // Тело не JSON — используем категорию по статусу
            }
            optionsRef.current?.onError?.(
              chatId,
              getProblemMessageFromBody(response.status, body),
            );
            return;
          }

          const reader = response.body!.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          let terminated = false;

          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split("\n\n");
            buffer = parts.pop() ?? "";

            for (const part of parts) {
              const line = part.trim();
              if (!line.startsWith("data: ")) continue;

              // Protect against malformed SSE frames — skip bad frame, keep stream alive.
              let frame: SSEFrame;
              try {
                frame = JSON.parse(line.slice(6)) as SSEFrame;
              } catch {
                logger.warn("[SSE] Malformed frame, skipping");
                continue;
              }

              // Любое событие — свидетельство живого соединения, включая
              // `heartbeat` и событие неизвестного типа.
              armSilenceWatch();

              // Forward-compat (streaming.md § Forward-compat): контракт растёт
              // без версионирования пути — неизвестный тип логируется и
              // пропускается, поток продолжает читаться.
              if (!isKnownSSEEvent(frame)) {
                logger.warn("[SSE] Неизвестный тип события", frame.type);
                continue;
              }
              const event = frame;

              switch (event.type) {
                case "stream_started":
                case "heartbeat":
                  // Содержимого не несут — их работа в том, что они пришли:
                  // сторож тишины уже перезаведён выше.
                  break;
                case "reasoning_chunk":
                case "text_chunk":
                case "tool_call_started":
                case "tool_call_args":
                case "tool_call_cancelled":
                case "tool_result":
                case "agent_event":
                  // Нормализация контракта в ленту — знание модели
                  // (`shared/lib/agent-feed`), а не диспетчера.
                  applyEvent(chatId, event);
                  break;
                case "artifact_created":
                  // В живом ходе карточка не рисуется: факт создания виден
                  // строкой ленты, а полную карточку рисует история после
                  // завершения хода. Здесь — только инвалидация списка
                  // артефактов проекта, чтобы он открылся уже с новым.
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.projects.artifacts(projectId),
                  });
                  break;
                case "final_output_review_started":
                  setReviewing(chatId, true);
                  break;
                case "final_output_review_complete":
                  setReviewing(chatId, false);
                  break;
                case "title_updated": {
                  // Только точечный патч кэша — без invalidateQueries, чтобы не
                  // задеть detail открытого чата посреди активного стрима
                  // (оптимистичная копия user-сообщения в localMessages задвоилась бы).
                  const title = event.title;
                  queryClient.setQueryData<ListResponse<Chat> | undefined>(
                    queryKeys.projects.chats(projectId),
                    (prev) =>
                      prev
                        ? {
                            ...prev,
                            items: prev.items.map((chat) =>
                              chat.thread_id === chatId
                                ? { ...chat, title }
                                : chat,
                            ),
                          }
                        : prev,
                  );
                  queryClient.setQueryData<
                    ListResponse<RecentChat> | undefined
                  >(queryKeys.chats.recent, (prev) =>
                    prev
                      ? {
                          ...prev,
                          items: prev.items.map((chat) =>
                            chat.thread_id === chatId
                              ? { ...chat, title }
                              : chat,
                          ),
                        }
                      : prev,
                  );
                  queryClient.setQueryData<ChatDetail | undefined>(
                    queryKeys.projects.chat(projectId, chatId),
                    (prev) => (prev ? { ...prev, title } : prev),
                  );
                  break;
                }
                case "done": {
                  terminated = true;
                  const traceId = event.trace_id ?? null;
                  const messageId = event.message_id ?? null;
                  endStream(chatId);
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.projects.chat(projectId, chatId),
                  });
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.projects.chats(projectId),
                    exact: true,
                  });
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.chats.recent,
                  });
                  optionsRef.current?.onDone?.({ chatId, messageId, traceId });
                  break;
                }
                case "cancelled": {
                  terminated = true;
                  endStream(chatId);
                  // Отмена во время исполнения инструмента — основной поставщик
                  // вызовов со статусом `pending`: без рефетча detail
                  // незавершённый вызов виден только после перезагрузки
                  // страницы. Оптимистичную копию user-сообщения снимает
                  // `onCancelled` — иначе после рефетча она задвоится.
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.projects.chat(projectId, chatId),
                  });
                  // Автозаголовок пишется в БД fire-and-forget, независимо от
                  // того, чем закончился ход, — та же страховка, что на `done`.
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.projects.chats(projectId),
                    exact: true,
                  });
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.chats.recent,
                  });
                  // Отмена — не ошибка: error-баннера здесь нет.
                  optionsRef.current?.onCancelled?.(chatId);
                  break;
                }
                case "security_block": {
                  terminated = true;
                  // Optimistic cache patch: disable input immediately, no wait for refetch.
                  queryClient.setQueryData<ChatDetail | undefined>(
                    queryKeys.projects.chat(projectId, chatId),
                    (prev) =>
                      prev ? { ...prev, security_blocked: true } : prev,
                  );
                  // Pull persisted user message + redacted placeholder from server.
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.projects.chat(projectId, chatId),
                  });
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.chats.recent,
                  });
                  // Списки чатов не инвалидируются: на заблокированном вводе
                  // генерация заголовка не запускается вовсе
                  // (streaming.md § Уточнения → `title_updated`).
                  //
                  // Редакция терминальна: лента хода схлопывается в заглушку и
                  // запирается, живой регион гаснет вместе со стримом. На экране
                  // не остаётся ни строки рассуждений, ни строк вызовов
                  // заблокированного хода, а саму заглушку показывает
                  // отрефетченная история — одну и ту же и сразу, и после
                  // перезагрузки. Транзиентного error-баннера нет: источник
                  // правды — сохранённая заглушка и заблокированный ввод.
                  redact(chatId, REDACTED_STUB);
                  optionsRef.current?.onSecurityBlock?.(chatId);
                  break;
                }
                case "error":
                  terminated = true;
                  endStream(chatId);
                  // Та же fallback-инвалидация списков, что на `done`: title мог
                  // успеть записаться до исключения.
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.projects.chats(projectId),
                    exact: true,
                  });
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.chats.recent,
                  });
                  if (!isCancellingRef.current) {
                    optionsRef.current?.onError?.(chatId, event.detail);
                  }
                  break;
              }

              if (terminated) clearTimeout(silenceTimer);
            }

            // Кадры прочитанного куска разобраны — уступаем событийному циклу,
            // прежде чем читать следующий (см. `yieldToEventLoop`).
            if (!terminated) await yieldToEventLoop();
          }

          clearTimeout(silenceTimer);

          if (!terminated) {
            endStream(chatId);
            optionsRef.current?.onError?.(chatId, "Соединение прервано");
          }
        } catch (err) {
          clearTimeout(silenceTimer);
          if (err instanceof DOMException && err.name === "AbortError") {
            if (timedOut) {
              // Таймаут уже обработан в колбэке сторожа тишины
            } else if (isCancellingRef.current) {
              endStream(chatId);
            }
            return;
          }
          logger.error("[SSE stream error]", err);
          endStream(chatId);
          optionsRef.current?.onError?.(chatId, "Ошибка соединения");
        }
      })();
    },
    [projectId, chatId, queryClient],
  );

  const cancel = useCallback(() => {
    isCancellingRef.current = true;
    cancelChat(projectId, chatId)
      .then(({ ok }) => {
        if (!ok) abortRef.current?.abort();
      })
      .catch((err) => {
        logger.error("[cancel error]", err);
        abortRef.current?.abort();
      });
  }, [projectId, chatId]);

  return { send, cancel };
}
