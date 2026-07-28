import { describe, expect, it } from "vitest";

import { findFeedCall } from "@/shared/lib/agent-feed";
import { useStreamStore } from "./stream-store";

// Unit: стор активного стрима — аккумулятор ленты активности, артефактов и
// флагов редакции/ревью. Чистые переходы состояния через публичные экшены.
// Семантику самой ленты сторожит shared/lib/agent-feed.test.ts; здесь — что
// стор её держит и что сброс между стримами полный. Zustand-стор
// автосбрасывается между тестами (src/test/setup.ts + __mocks__/zustand.ts).

describe("stream-store", () => {
  it("starts in an idle, empty state", () => {
    const s = useStreamStore.getState();

    expect(s.isStreaming).toBe(false);
    expect(s.feed).toEqual([]);
    expect(s.streamingChatId).toBeNull();
    expect(s.streamingArtifacts).toEqual([]);
    expect(s.redacted).toBe(false);
    expect(s.isReviewing).toBe(false);
  });

  it("marks streaming active for the given chat on startStream", () => {
    useStreamStore.getState().startStream("chat-1");

    const s = useStreamStore.getState();
    expect(s.isStreaming).toBe(true);
    expect(s.streamingChatId).toBe("chat-1");
  });

  it("clears leftover state from a prior stream on startStream", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");
    store.applyEvent({ type: "text_chunk", content: "stale" });
    store.applyEvent({
      type: "tool_call_started",
      call_id: "call-1",
      tool: "get_section",
    });
    store.addArtifact({ id: "a1", title: "First", type: "doc" });
    store.setReviewing(true);
    store.redact("[hidden]");

    useStreamStore.getState().startStream("chat-2");

    const s = useStreamStore.getState();
    expect(s.feed).toEqual([]);
    expect(s.streamingArtifacts).toEqual([]);
    expect(s.streamingChatId).toBe("chat-2");
    expect(s.redacted).toBe(false);
    expect(s.isReviewing).toBe(false);
  });

  it("accumulates text chunks into a single feed item in arrival order", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");

    store.applyEvent({ type: "text_chunk", content: "Hello" });
    store.applyEvent({ type: "text_chunk", content: ", " });
    store.applyEvent({ type: "text_chunk", content: "world" });

    expect(useStreamStore.getState().feed).toEqual([
      { id: "text-0", type: "text", content: "Hello, world" },
    ]);
  });

  it("tracks parallel tool calls by call_id and closes them independently", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");

    store.applyEvent({
      type: "tool_call_started",
      call_id: "call-1",
      tool: "firecrawl_search",
    });
    store.applyEvent({
      type: "tool_call_started",
      call_id: "call-2",
      tool: "get_section",
    });
    store.applyEvent({
      type: "tool_result",
      call_id: "call-1",
      tool: "firecrawl_search",
      status: "success",
      content: "found",
      truncated: false,
    });

    const { feed } = useStreamStore.getState();
    expect(findFeedCall(feed, "call-1")?.status).toBe("success");
    expect(findFeedCall(feed, "call-2")?.status).toBe("running");
  });

  it("ignores feed events once the turn has been redacted", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");
    store.applyEvent({ type: "text_chunk", content: "secret" });
    store.redact("[hidden]");

    store.applyEvent({ type: "text_chunk", content: " more text" });

    expect(useStreamStore.getState().feed).toEqual([
      { id: "text-0", type: "text", content: "[hidden]" },
    ]);
  });

  it("appends streaming artifacts preserving order", () => {
    const store = useStreamStore.getState();

    store.addArtifact({ id: "a1", title: "First", type: "doc" });
    store.addArtifact({ id: "a2", title: "Second", type: "code" });

    expect(useStreamStore.getState().streamingArtifacts).toEqual([
      { id: "a1", title: "First", type: "doc" },
      { id: "a2", title: "Second", type: "code" },
    ]);
  });

  it("redact replaces the whole feed with a single stub and clears review", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");
    store.applyEvent({ type: "reasoning_chunk", content: "secret thoughts" });
    store.applyEvent({
      type: "tool_call_started",
      call_id: "call-1",
      tool: "firecrawl_search",
    });
    store.setReviewing(true);

    store.redact("[hidden]");

    const s = useStreamStore.getState();
    expect(s.feed).toEqual([
      { id: "text-0", type: "text", content: "[hidden]" },
    ]);
    expect(s.redacted).toBe(true);
    expect(s.isReviewing).toBe(false);
  });

  it("toggles the reviewing flag", () => {
    const store = useStreamStore.getState();

    store.setReviewing(true);
    expect(useStreamStore.getState().isReviewing).toBe(true);

    store.setReviewing(false);
    expect(useStreamStore.getState().isReviewing).toBe(false);
  });

  it("resets to the idle state on endStream", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");
    store.applyEvent({ type: "text_chunk", content: "partial" });
    store.applyEvent({
      type: "tool_call_started",
      call_id: "call-1",
      tool: "get_section",
    });
    store.addArtifact({ id: "a1", title: "First", type: "doc" });
    store.setReviewing(true);

    store.endStream();

    const s = useStreamStore.getState();
    expect(s.isStreaming).toBe(false);
    expect(s.feed).toEqual([]);
    expect(s.streamingChatId).toBeNull();
    expect(s.streamingArtifacts).toEqual([]);
    expect(s.redacted).toBe(false);
    expect(s.isReviewing).toBe(false);
  });
});
