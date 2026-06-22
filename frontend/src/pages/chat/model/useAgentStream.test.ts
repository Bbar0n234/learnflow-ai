import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { setAccessToken } from "@/shared/api/client";
import { queryKeys } from "@/shared/api/query-keys";
import type { ChatDetail } from "@/shared/api/chats";
import { server } from "@/test/msw/server";
import { createTestQueryClient } from "@/test/test-utils";
import { fakeJwt, sseFrame, sseResponseStream } from "@/test/sse-stream";

import { useAgentStream } from "./useAgentStream";

// Integration: the agent SSE stream consumer. The hook POSTs to the messages
// endpoint and reads a text/event-stream body frame by frame, driving the
// stream store and lifecycle callbacks. Network is mocked with MSW's native
// streaming response; a non-expired JWT in localStorage lets ensureFreshToken
// resolve without a refresh round-trip.

const PROJECT_ID = "p1";
const CHAT_ID = "c1";
const MESSAGES_URL = `/api/projects/${PROJECT_ID}/chats/${CHAT_ID}/messages`;

function streamResponse(events: unknown[]): Response {
  return new HttpResponse(sseResponseStream(events.map((e) => sseFrame(e))), {
    headers: { "Content-Type": "text/event-stream" },
  }) as unknown as Response;
}

function renderAgentStream(options?: Parameters<typeof useAgentStream>[2]) {
  const queryClient = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  const { result } = renderHook(
    () => useAgentStream(PROJECT_ID, CHAT_ID, options),
    { wrapper },
  );
  return { result, queryClient };
}

afterEach(() => {
  localStorage.clear();
});

describe("useAgentStream", () => {
  it("invokes onDone with the message and trace ids on a done event", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([
          { type: "text_chunk", content: "Hello" },
          { type: "done", message_id: "m-1", trace_id: "t-1" },
        ]),
      ),
    );
    const onDone = vi.fn();
    const { result } = renderAgentStream({ onDone });

    result.current.send("hi");

    await waitFor(() =>
      expect(onDone).toHaveBeenCalledWith({
        messageId: "m-1",
        traceId: "t-1",
      }),
    );
  });

  it("redacts accumulated text on a security_block after streamed text", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([
          { type: "text_chunk", content: "leaking secret" },
          { type: "security_block", reason: "injection" },
        ]),
      ),
    );
    const onSecurityBlock = vi.fn();
    const { result } = renderAgentStream({ onSecurityBlock });

    result.current.send("hi");

    await waitFor(() => expect(onSecurityBlock).toHaveBeenCalledTimes(1));
    const { useStreamStore } = await import("@/stores/stream-store");
    const state = useStreamStore.getState();
    expect(state.redacted).toBe(true);
    expect(state.streamingText).toBe("[Сообщение скрыто в целях безопасности]");
  });

  it("optimistically marks the chat security_blocked when blocked before any text", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([{ type: "security_block", reason: "injection" }]),
      ),
    );
    const onSecurityBlock = vi.fn();
    const { result, queryClient } = renderAgentStream({ onSecurityBlock });
    queryClient.setQueryData<ChatDetail>(
      queryKeys.projects.chat(PROJECT_ID, CHAT_ID),
      {
        thread_id: CHAT_ID,
        title: "t",
        security_blocked: false,
        messages: [],
      },
    );

    result.current.send("hi");

    await waitFor(() => expect(onSecurityBlock).toHaveBeenCalledTimes(1));
    const cached = queryClient.getQueryData<ChatDetail>(
      queryKeys.projects.chat(PROJECT_ID, CHAT_ID),
    );
    expect(cached?.security_blocked).toBe(true);
  });

  it("forwards an error event detail to onError", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([{ type: "error", detail: "model exploded" }]),
      ),
    );
    const onError = vi.fn();
    const { result } = renderAgentStream({ onError });

    result.current.send("hi");

    await waitFor(() => expect(onError).toHaveBeenCalledWith("model exploded"));
  });

  it("reports a problem message when the POST returns a non-ok status", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        HttpResponse.json({ detail: "Доступ запрещён" }, { status: 403 }),
      ),
    );
    const onError = vi.fn();
    const { result } = renderAgentStream({ onError });

    result.current.send("hi");

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith("Доступ запрещён"),
    );
  });

  it("skips a malformed SSE frame and still completes the stream", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(
        MESSAGES_URL,
        () =>
          new HttpResponse(
            sseResponseStream([
              "data: {not valid json}\n\n",
              sseFrame({ type: "text_chunk", content: "ok" }),
              sseFrame({ type: "done", message_id: "m-9", trace_id: null }),
            ]),
            { headers: { "Content-Type": "text/event-stream" } },
          ),
      ),
    );
    const onDone = vi.fn();
    const onError = vi.fn();
    const { result } = renderAgentStream({ onDone, onError });

    result.current.send("hi");

    await waitFor(() =>
      expect(onDone).toHaveBeenCalledWith({ messageId: "m-9", traceId: null }),
    );
    expect(onError).not.toHaveBeenCalled();
  });
});
