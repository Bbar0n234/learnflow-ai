import { useCallback, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { cancelChat } from "@/shared/api/chats";
import { ensureFreshToken } from "@/shared/api/client";
import { queryKeys } from "@/shared/api/query-keys";
import type { Chat, ChatDetail, RecentChat } from "@/shared/api/chats";
import type { ListResponse } from "@/shared/api/pagination";
import type { SSEEvent } from "@/shared/api/sse";
import { logger } from "@/shared/lib/logger";
import { getProblemMessageFromBody } from "@/shared/lib/api-error";
import { useStreamStore } from "@/stores/stream-store";

/**
 * Таймаут первого байта SSE-стрима (мс) — страховка от мёртвого соединения,
 * не лимит на ответ агента: заголовки ответа приходят только после
 * pre-stream guard-проверки, а прогоны с субагентами легитимно молчат
 * минуты до первого события. Пользовательский контроль над долгим прогоном —
 * мгновенный ThinkingIndicator и кнопка отмены, не этот таймаут.
 * Fallback на VITE_API_TIMEOUT_MS убран: это лимит обычного REST-запроса,
 * для SSE он давал ложные «Превышено время ожидания» на легитимных прогонах.
 */
const FIRST_BYTE_TIMEOUT_MS =
  Number(import.meta.env.VITE_SSE_FIRST_BYTE_TIMEOUT_MS) || 300000;

interface DoneInfo {
  messageId: string | null;
  traceId: string | null;
}

interface UseAgentStreamOptions {
  onDone?: (info: DoneInfo) => void;
  onError?: (detail: string) => void;
  onSecurityBlock?: () => void;
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

  // Cleanup on unmount — hard kill + reset store
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
      useStreamStore.getState().endStream();
    };
  }, []);

  const send = useCallback(
    (content: string) => {
      const {
        startStream,
        appendText,
        addArtifact,
        replaceWithRedacted,
        setReviewing,
        endStream,
      } = useStreamStore.getState();

      startStream(chatId);
      isCancellingRef.current = false;
      let hasText = false;

      const controller = new AbortController();
      abortRef.current = controller;

      (async () => {
        // First-byte timeout: fires if server doesn't respond within the limit.
        // Cleared immediately after a valid (ok) response is received.
        let timedOut = false;
        const firstByteTimer = setTimeout(() => {
          timedOut = true;
          controller.abort();
          endStream();
          optionsRef.current?.onError?.("Превышено время ожидания");
        }, FIRST_BYTE_TIMEOUT_MS);

        try {
          const token = await ensureFreshToken();
          if (!token) {
            clearTimeout(firstByteTimer);
            endStream();
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
              clearTimeout(firstByteTimer);
              endStream();
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
            clearTimeout(firstByteTimer);
            endStream();
            let body: unknown = null;
            try {
              body = await response.json();
            } catch {
              // Тело не JSON — используем категорию по статусу
            }
            optionsRef.current?.onError?.(
              getProblemMessageFromBody(response.status, body),
            );
            return;
          }

          // Got valid SSE response — first byte received, cancel timeout.
          clearTimeout(firstByteTimer);

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
              let event: SSEEvent;
              try {
                event = JSON.parse(line.slice(6)) as SSEEvent;
              } catch {
                logger.warn("[SSE] Malformed frame, skipping");
                continue;
              }

              switch (event.type) {
                case "text_chunk":
                  hasText = true;
                  appendText(event.content);
                  break;
                case "artifact_created":
                  addArtifact({
                    id: event.id,
                    title: event.title,
                    type: event.artifact_type,
                  });
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.projects.artifacts(projectId),
                  });
                  break;
                case "final_output_review_started":
                  setReviewing(true);
                  break;
                case "final_output_review_complete":
                  setReviewing(false);
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
                  endStream();
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
                  optionsRef.current?.onDone?.({ messageId, traceId });
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
                  if (hasText) {
                    replaceWithRedacted(
                      "[Сообщение скрыто в целях безопасности]",
                    );
                  } else {
                    // No transient error banner — persisted placeholder + disabled input
                    // are the single source of truth, identical before and after reload.
                    endStream();
                  }
                  optionsRef.current?.onSecurityBlock?.();
                  break;
                }
                case "error":
                  terminated = true;
                  endStream();
                  if (!isCancellingRef.current) {
                    optionsRef.current?.onError?.(event.detail);
                  }
                  break;
              }
            }
          }

          if (!terminated) {
            endStream();
            optionsRef.current?.onError?.("Соединение прервано");
          }
        } catch (err) {
          clearTimeout(firstByteTimer);
          if (err instanceof DOMException && err.name === "AbortError") {
            if (timedOut) {
              // Таймаут уже обработан в колбэке firstByteTimer
            } else if (isCancellingRef.current) {
              endStream();
            }
            return;
          }
          logger.error("[SSE stream error]", err);
          endStream();
          optionsRef.current?.onError?.("Ошибка соединения");
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
