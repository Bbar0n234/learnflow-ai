import { useCallback, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { cancelChat } from "@/shared/api/chats";
import { ensureFreshToken } from "@/shared/api/client";
import type { ChatDetail, SSEEvent } from "@/shared/api/types";
import { logger } from "@/shared/lib/logger";
import { useStreamStore } from "@/stores/stream-store";

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
        try {
          const token = await ensureFreshToken();
          if (!token) {
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
            endStream();
            optionsRef.current?.onError?.(`HTTP ${response.status}`);
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

              const event: SSEEvent = JSON.parse(line.slice(6));

              switch (event.type) {
                case "text_chunk":
                  hasText = true;
                  appendText(event.content);
                  break;
                case "tool_start":
                  setTool(event.tool);
                  break;
                case "tool_end":
                  setTool(null);
                  break;
                case "artifact_created":
                  addArtifact({
                    id: event.id,
                    title: event.title,
                    type: event.artifact_type,
                  });
                  queryClient.invalidateQueries({
                    queryKey: ["projects", projectId, "artifacts"],
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
                    queryKey: ["projects", projectId, "chats", chatId],
                  });
                  queryClient.invalidateQueries({
                    queryKey: ["chats", "recent"],
                  });
                  optionsRef.current?.onDone?.({ messageId, traceId });
                  break;
                }
                case "security_block": {
                  terminated = true;
                  // Optimistic cache patch: disable input immediately, no wait for refetch.
                  queryClient.setQueryData<ChatDetail | undefined>(
                    ["projects", projectId, "chats", chatId],
                    (prev) =>
                      prev ? { ...prev, security_blocked: true } : prev,
                  );
                  // Pull persisted user message + redacted placeholder from server.
                  queryClient.invalidateQueries({
                    queryKey: ["projects", projectId, "chats", chatId],
                  });
                  queryClient.invalidateQueries({
                    queryKey: ["chats", "recent"],
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
            optionsRef.current?.onError?.("Connection lost");
          }
        } catch (err) {
          if (err instanceof DOMException && err.name === "AbortError") {
            if (isCancellingRef.current) endStream();
            return;
          }
          logger.error("[SSE stream error]", err);
          endStream();
          optionsRef.current?.onError?.(
            err instanceof Error ? err.message : "Connection error",
          );
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
