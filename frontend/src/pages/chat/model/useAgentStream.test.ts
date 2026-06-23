import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
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
const CANCEL_URL = `/api/projects/${PROJECT_ID}/chats/${CHAT_ID}/cancel`;
const REFRESH_URL = "/api/auth/refresh";

function streamResponse(events: unknown[]): Response {
  return new HttpResponse(sseResponseStream(events.map((e) => sseFrame(e))), {
    headers: { "Content-Type": "text/event-stream" },
  }) as unknown as Response;
}

/**
 * A live SSE response whose frames are pushed from the test on demand and which
 * stays open until explicitly closed (or the reader is aborted). Lets a test
 * drive cancel/interruption timing against an in-flight stream.
 */
function liveStream() {
  const encoder = new TextEncoder();
  let ctrl!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      ctrl = c;
    },
  });
  const response = new HttpResponse(body, {
    headers: { "Content-Type": "text/event-stream" },
  }) as unknown as Response;
  return {
    response,
    push: (event: unknown) => ctrl.enqueue(encoder.encode(sseFrame(event))),
    close: () => ctrl.close(),
  };
}

function renderAgentStream(options?: Parameters<typeof useAgentStream>[2]) {
  const queryClient = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  const { result, unmount } = renderHook(
    () => useAgentStream(PROJECT_ID, CHAT_ID, options),
    { wrapper },
  );
  return { result, queryClient, unmount };
}

afterEach(() => {
  localStorage.clear();
  vi.useRealTimers();
});

async function streamingText(): Promise<string> {
  const { useStreamStore } = await import("@/stores/stream-store");
  return useStreamStore.getState().streamingText;
}

async function isStreaming(): Promise<boolean> {
  const { useStreamStore } = await import("@/stores/stream-store");
  return useStreamStore.getState().isStreaming;
}

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

  it("sends a cancel request to the server and surfaces no error on a graceful cancel", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    let cancelHit = false;
    server.use(
      http.post(MESSAGES_URL, () => live.response),
      http.post(CANCEL_URL, () => {
        cancelHit = true;
        return HttpResponse.json({ ok: true });
      }),
    );
    const onError = vi.fn();
    const onDone = vi.fn();
    const { result } = renderAgentStream({ onError, onDone });

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "partial" });
    await waitFor(async () => expect(await streamingText()).toBe("partial"));

    result.current.cancel();
    await waitFor(() => expect(cancelHit).toBe(true));

    // Server finalizes the cancelled turn with a terminal event.
    live.push({ type: "done", message_id: "m-cancel", trace_id: null });
    live.close();

    await waitFor(async () => expect(await isStreaming()).toBe(false));
    expect(onError).not.toHaveBeenCalled();
  });

  it("aborts the in-flight stream and resets the store on unmount", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const { result, unmount } = renderAgentStream();

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "partial" });
    await waitFor(async () => expect(await streamingText()).toBe("partial"));

    unmount();

    expect(await isStreaming()).toBe(false);
  });

  it("suppresses a trailing error event that arrives after cancel", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(
      http.post(MESSAGES_URL, () => live.response),
      // Server-side cancel succeeds; the reader keeps draining a final error frame.
      http.post(CANCEL_URL, () => HttpResponse.json({ ok: true })),
    );
    const onError = vi.fn();
    const { result } = renderAgentStream({ onError });

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "partial" });
    await waitFor(async () => expect(await streamingText()).toBe("partial"));

    // cancel() flips the cancelling flag synchronously, before the async
    // cancelChat round-trip; a trailing error frame must now be swallowed.
    result.current.cancel();
    live.push({ type: "error", detail: "stream torn down" });
    live.close();

    await waitFor(async () => expect(await isStreaming()).toBe(false));
    expect(onError).not.toHaveBeenCalled();
  });

  it("fires onError with the timeout message when no first byte arrives in time", async () => {
    setAccessToken(fakeJwt());
    vi.useFakeTimers();
    server.use(
      // Never responds — exercises the first-byte timeout path.
      http.post(MESSAGES_URL, () => delay("infinite")),
    );
    const onError = vi.fn();
    const { result } = renderAgentStream({ onError });

    result.current.send("hi");
    await vi.advanceTimersByTimeAsync(31000);

    expect(onError).toHaveBeenCalledWith("Превышено время ожидания");
  });

  it("retries the message POST after a 401 by refreshing the token, then completes", async () => {
    setAccessToken(fakeJwt(10)); // near expiry → proactive refresh round-trip
    let refreshCount = 0;
    let postCount = 0;
    server.use(
      http.post(REFRESH_URL, () => {
        refreshCount += 1;
        return HttpResponse.json({
          access_token: fakeJwt(3600),
          token_type: "bearer",
        });
      }),
      http.post(MESSAGES_URL, () => {
        postCount += 1;
        if (postCount === 1) {
          return HttpResponse.json({ detail: "expired" }, { status: 401 });
        }
        return streamResponse([
          { type: "text_chunk", content: "after retry" },
          { type: "done", message_id: "m-401", trace_id: null },
        ]);
      }),
    );
    const onDone = vi.fn();
    const { result } = renderAgentStream({ onDone });

    result.current.send("hi");

    await waitFor(() =>
      expect(onDone).toHaveBeenCalledWith({
        messageId: "m-401",
        traceId: null,
      }),
    );
    expect(postCount).toBe(2);
    expect(refreshCount).toBeGreaterThanOrEqual(1);
  });

  it("invalidates the artifacts query when an artifact_created event arrives", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([
          {
            type: "artifact_created",
            id: "a-1",
            title: "Notes",
            artifact_type: "markdown",
          },
          { type: "done", message_id: "m-art", trace_id: null },
        ]),
      ),
    );
    const onDone = vi.fn();
    const { result, queryClient } = renderAgentStream({ onDone });
    queryClient.setQueryData(queryKeys.projects.artifacts(PROJECT_ID), {
      items: [],
      total: 0,
      limit: 50,
      offset: 0,
    });

    result.current.send("hi");

    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(
      queryClient.getQueryState(queryKeys.projects.artifacts(PROJECT_ID))
        ?.isInvalidated,
    ).toBe(true);
  });

  it("reports a broken connection when the stream ends without a terminal event", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([{ type: "text_chunk", content: "incomplete" }]),
      ),
    );
    const onError = vi.fn();
    const onDone = vi.fn();
    const { result } = renderAgentStream({ onError, onDone });

    result.current.send("hi");

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith("Соединение прервано"),
    );
    expect(onDone).not.toHaveBeenCalled();
  });

  it("reports a connection error on a non-abort fetch failure", async () => {
    setAccessToken(fakeJwt());
    server.use(http.post(MESSAGES_URL, () => HttpResponse.error()));
    const onError = vi.fn();
    const { result } = renderAgentStream({ onError });

    result.current.send("hi");

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith("Ошибка соединения"),
    );
  });
});
