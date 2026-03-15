import { useCallback, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { cancelChat } from "@/shared/api/chats";
import { getUsername } from "@/shared/api/client";
import type { SSEEvent } from "@/shared/api/types";
import { useStreamStore } from "@/stores/stream-store";

interface UseAgentStreamOptions {
  onDone?: () => void;
  onError?: (detail: string) => void;
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
      const { startStream, appendText, setTool, addArtifact, endStream } =
        useStreamStore.getState();

      startStream(chatId);
      isCancellingRef.current = false;

      const controller = new AbortController();
      abortRef.current = controller;

      (async () => {
        try {
          const response = await fetch(
            `/api/projects/${projectId}/chats/${chatId}/messages`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-User-Name": getUsername(),
              },
              body: JSON.stringify({ content }),
              signal: controller.signal,
            },
          );

          if (!response.ok) {
            endStream();
            optionsRef.current?.onError?.(`HTTP ${response.status}`);
            return;
          }

          const reader = response.body!.getReader();
          const decoder = new TextDecoder();
          let buffer = "";

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
                case "done":
                  endStream();
                  queryClient.invalidateQueries({
                    queryKey: ["projects", projectId, "chats", chatId],
                  });
                  queryClient.invalidateQueries({
                    queryKey: ["chats", "recent"],
                  });
                  optionsRef.current?.onDone?.();
                  break;
                case "error":
                  endStream();
                  if (!isCancellingRef.current) {
                    optionsRef.current?.onError?.(event.detail);
                  }
                  break;
              }
            }
          }
        } catch (err) {
          if (err instanceof DOMException && err.name === "AbortError") return;
          console.error("[SSE stream error]", err);
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
    cancelChat(projectId, chatId);
  }, [projectId, chatId]);

  return { send, cancel };
}
