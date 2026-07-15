import { useCallback, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { cancelChat } from "@/shared/api/chats";
import { ensureFreshToken } from "@/shared/api/client";
import { queryKeys } from "@/shared/api/query-keys";
import type { ChatDetail } from "@/shared/api/chats";
import type { SSEEvent } from "@/shared/api/sse";
import { logger } from "@/shared/lib/logger";
import { getProblemMessageFromBody } from "@/shared/lib/api-error";
import { useStreamStore } from "@/stores/stream-store";

/**
 * Таймаут первого байта SSE-стрима (мс).
 * Отдельная env (семантически первый байт ≠ полный REST-запрос).
 * Fallback на VITE_API_TIMEOUT_MS, затем 30 000 мс.
 */
const FIRST_BYTE_TIMEOUT_MS =
  Number(import.meta.env.VITE_SSE_FIRST_BYTE_TIMEOUT_MS) ||
  Number(import.meta.env.VITE_API_TIMEOUT_MS) ||
  30000;

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
        setTool,
        addArtifact,
        addPendingImage,
        removePendingImage,
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
                case "tool_start":
                  setTool(event.tool);
                  if (event.tool === "generate_image") {
                    addPendingImage(event.call_id);
                  }
                  break;
                case "tool_end":
                  setTool(null);
                  if (event.tool === "generate_image") {
                    removePendingImage(event.call_id);
                  }
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
                case "done": {
                  terminated = true;
                  const traceId = event.trace_id ?? null;
                  const messageId = event.message_id ?? null;
                  endStream();
                  queryClient.invalidateQueries({
                    queryKey: queryKeys.projects.chat(projectId, chatId),
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
