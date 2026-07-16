import { describe, expect, it } from "vitest";

import { useStreamStore } from "./stream-store";

// Unit: the streaming store is the SSE accumulator — text chunks, active tool,
// artifacts, redaction and review flags. Pure state transitions, exercised
// through the public actions. Zustand store auto-resets between tests
// (src/test/setup.ts + __mocks__/zustand.ts).

describe("stream-store", () => {
  it("starts in an idle, empty state", () => {
    const s = useStreamStore.getState();

    expect(s.isStreaming).toBe(false);
    expect(s.streamingText).toBe("");
    expect(s.activeTool).toBeNull();
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
    store.appendText("stale");
    store.setReviewing(true);

    useStreamStore.getState().startStream("chat-2");

    const s = useStreamStore.getState();
    expect(s.streamingText).toBe("");
    expect(s.streamingChatId).toBe("chat-2");
    expect(s.isReviewing).toBe(false);
  });

  it("concatenates text chunks in arrival order via appendText", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");

    store.appendText("Hello");
    store.appendText(", ");
    store.appendText("world");

    expect(useStreamStore.getState().streamingText).toBe("Hello, world");
  });

  it("ignores appendText once the message has been redacted", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");
    store.appendText("secret");
    store.replaceWithRedacted("[hidden]");

    store.appendText(" more text");

    expect(useStreamStore.getState().streamingText).toBe("[hidden]");
  });

  it("tracks the active tool and clears it on null", () => {
    const store = useStreamStore.getState();

    store.setTool("web_search");
    expect(useStreamStore.getState().activeTool).toBe("web_search");

    store.setTool(null);
    expect(useStreamStore.getState().activeTool).toBeNull();
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

  it("replaceWithRedacted swaps text and clears tool and review flags", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");
    store.setTool("web_search");
    store.setReviewing(true);

    store.replaceWithRedacted("[hidden]");

    const s = useStreamStore.getState();
    expect(s.streamingText).toBe("[hidden]");
    expect(s.redacted).toBe(true);
    expect(s.activeTool).toBeNull();
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
    store.appendText("partial");
    store.setTool("web_search");
    store.addArtifact({ id: "a1", title: "First", type: "doc" });

    store.endStream();

    const s = useStreamStore.getState();
    expect(s.isStreaming).toBe(false);
    expect(s.streamingText).toBe("");
    expect(s.activeTool).toBeNull();
    expect(s.streamingChatId).toBeNull();
    expect(s.streamingArtifacts).toEqual([]);
    expect(s.redacted).toBe(false);
  });

  // feat-010: pending image generations tracked by call_id.
  it("tracks a pending image generation by call_id", () => {
    const store = useStreamStore.getState();

    store.addPendingImage("call-1");
    store.addPendingImage("call-2");

    expect(useStreamStore.getState().pendingImages).toEqual([
      "call-1",
      "call-2",
    ]);
  });

  it("does not duplicate a call_id added twice", () => {
    const store = useStreamStore.getState();

    store.addPendingImage("call-1");
    store.addPendingImage("call-1");

    expect(useStreamStore.getState().pendingImages).toEqual(["call-1"]);
  });

  it("removes a pending image by call_id", () => {
    const store = useStreamStore.getState();
    store.addPendingImage("call-1");
    store.addPendingImage("call-2");

    store.removePendingImage("call-1");

    expect(useStreamStore.getState().pendingImages).toEqual(["call-2"]);
  });

  it("removePendingImage is a no-op for an unknown call_id", () => {
    const store = useStreamStore.getState();
    store.addPendingImage("call-1");

    store.removePendingImage("nope");

    expect(useStreamStore.getState().pendingImages).toEqual(["call-1"]);
  });

  it("clears pending images on startStream", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");
    store.addPendingImage("call-1");

    store.startStream("chat-2");

    expect(useStreamStore.getState().pendingImages).toEqual([]);
  });

  it("clears pending images on endStream", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");
    store.addPendingImage("call-1");

    store.endStream();

    expect(useStreamStore.getState().pendingImages).toEqual([]);
  });
});
