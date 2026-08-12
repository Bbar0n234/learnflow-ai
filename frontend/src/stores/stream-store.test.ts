import { describe, expect, it, vi } from "vitest";

import { findFeedCall } from "@/shared/lib/agent-feed";
import { useStreamStore } from "./stream-store";

type StreamActions = ReturnType<typeof useStreamStore.getState>;

// Unit: стор активного стрима — аккумулятор ленты активности и флагов
// редакции/ревью. Чистые переходы состояния через публичные экшены.
// Семантику самой ленты сторожит shared/lib/agent-feed.test.ts; здесь — что
// стор её держит и что сброс между стримами полный. Zustand-стор
// автосбрасывается между тестами (src/test/setup.ts + __mocks__/zustand.ts).

describe("stream-store", () => {
  it("starts in an idle, empty state", () => {
    const s = useStreamStore.getState();

    expect(s.isStreaming).toBe(false);
    expect(s.feed).toEqual([]);
    expect(s.streamingChatId).toBeNull();
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
    store.applyEvent("chat-1", { type: "text_chunk", content: "stale" });
    store.applyEvent("chat-1", {
      type: "tool_call_started",
      call_id: "call-1",
      tool: "get_section",
    });
    store.setReviewing("chat-1", true);
    store.redact("chat-1", "[hidden]");

    useStreamStore.getState().startStream("chat-2");

    const s = useStreamStore.getState();
    expect(s.feed).toEqual([]);
    expect(s.streamingChatId).toBe("chat-2");
    expect(s.redacted).toBe(false);
    expect(s.isReviewing).toBe(false);
  });

  it("accumulates text chunks into a single feed item in arrival order", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");

    store.applyEvent("chat-1", { type: "text_chunk", content: "Hello" });
    store.applyEvent("chat-1", { type: "text_chunk", content: ", " });
    store.applyEvent("chat-1", { type: "text_chunk", content: "world" });

    expect(useStreamStore.getState().feed).toEqual([
      { id: "text-0", type: "text", content: "Hello, world" },
    ]);
  });

  it("tracks parallel tool calls by call_id and closes them independently", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");

    store.applyEvent("chat-1", {
      type: "tool_call_started",
      call_id: "call-1",
      tool: "firecrawl_search",
    });
    store.applyEvent("chat-1", {
      type: "tool_call_started",
      call_id: "call-2",
      tool: "get_section",
    });
    store.applyEvent("chat-1", {
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
    store.applyEvent("chat-1", { type: "text_chunk", content: "secret" });
    store.redact("chat-1", "[hidden]");

    store.applyEvent("chat-1", { type: "text_chunk", content: " more text" });

    expect(useStreamStore.getState().feed).toEqual([
      { id: "text-0", type: "text", content: "[hidden]" },
    ]);
  });

  it("redact replaces the whole feed with a single stub and clears review", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");
    store.applyEvent("chat-1", {
      type: "reasoning_chunk",
      content: "secret thoughts",
    });
    store.applyEvent("chat-1", {
      type: "tool_call_started",
      call_id: "call-1",
      tool: "firecrawl_search",
    });
    store.setReviewing("chat-1", true);

    store.redact("chat-1", "[hidden]");

    const s = useStreamStore.getState();
    expect(s.feed).toEqual([
      { id: "text-0", type: "text", content: "[hidden]" },
    ]);
    expect(s.redacted).toBe(true);
    expect(s.isReviewing).toBe(false);
  });

  it("redact closes the stream without wiping the redacted feed", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");
    store.applyEvent("chat-1", { type: "text_chunk", content: "secret" });

    store.redact("chat-1", "[hidden]");

    // Блокировка терминальна: ход закончился, поэтому живой регион гаснет — а
    // заглушку показывает история. Иначе она видна дважды.
    const s = useStreamStore.getState();
    expect(s.isStreaming).toBe(false);
    expect(s.streamingChatId).toBeNull();
    expect(s.feed).toEqual([
      { id: "text-0", type: "text", content: "[hidden]" },
    ]);
  });

  it("toggles the reviewing flag", () => {
    const store = useStreamStore.getState();
    // setReviewing зовёт guard: без владельца стрима вызов — no-op (owner-guard,
    // stream-store.ts).
    store.startStream("chat-1");

    store.setReviewing("chat-1", true);
    expect(useStreamStore.getState().isReviewing).toBe(true);

    store.setReviewing("chat-1", false);
    expect(useStreamStore.getState().isReviewing).toBe(false);
  });

  it("resets to the idle state on endStream", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-1");
    store.applyEvent("chat-1", { type: "text_chunk", content: "partial" });
    store.applyEvent("chat-1", {
      type: "tool_call_started",
      call_id: "call-1",
      tool: "get_section",
    });
    store.setReviewing("chat-1", true);

    store.endStream("chat-1");

    const s = useStreamStore.getState();
    expect(s.isStreaming).toBe(false);
    expect(s.feed).toEqual([]);
    expect(s.streamingChatId).toBeNull();
    expect(s.redacted).toBe(false);
    expect(s.isReviewing).toBe(false);
  });
});

// Owner-guard: стор — держатель инварианта «пишет только владелец текущего
// стрима». Поток чата A при переключении на B не абортится (cleanup хука висит
// на unmount), поэтому его события и терминал продолжают идти в стор уже после
// `startStream("chat-b")`. Ниже — что стор делает с этими запоздалыми записями:
// каждая охраняемая запись чужого владельца обязана быть no-op, а сама попытка
// — не будить подписчиков.
describe("stream-store: owner-guard", () => {
  it("не применяет событие чужого потока и не будит подписчиков", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-b");
    store.applyEvent("chat-b", { type: "text_chunk", content: "ответ B" });
    const notified = vi.fn();
    const unsubscribe = useStreamStore.subscribe(notified);

    store.applyEvent("chat-a", { type: "text_chunk", content: " хвост A" });
    store.applyEvent("chat-a", {
      type: "tool_call_started",
      call_id: "call-a",
      tool: "firecrawl_search",
    });

    unsubscribe();
    expect(useStreamStore.getState().feed).toEqual([
      { id: "text-0", type: "text", content: "ответ B" },
    ]);
    // Подписчик не разбужен вовсе — no-op возвращает то же состояние, а не
    // пересобранное: иначе лента чата B перерисовывалась бы на каждом событии
    // догорающего чужого хода.
    expect(notified).not.toHaveBeenCalled();
  });

  it("не гасит живой стрим терминалом чужого потока", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-b");
    store.applyEvent("chat-b", { type: "text_chunk", content: "ответ B" });

    store.endStream("chat-a");

    // Главный симптом, ради которого guard заведён: `done` часового хода в
    // соседнем чате гасил живой стрим открытого.
    const s = useStreamStore.getState();
    expect(s.isStreaming).toBe(true);
    expect(s.streamingChatId).toBe("chat-b");
    expect(s.feed).toEqual([
      { id: "text-0", type: "text", content: "ответ B" },
    ]);
  });

  it("не схлопывает ленту в заглушку по редакции чужого потока", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-b");
    store.applyEvent("chat-b", { type: "text_chunk", content: "ответ B" });

    store.redact("chat-a", "[hidden]");

    const s = useStreamStore.getState();
    expect(s.feed).toEqual([
      { id: "text-0", type: "text", content: "ответ B" },
    ]);
    expect(s.redacted).toBe(false);
    expect(s.isStreaming).toBe(true);
    expect(s.streamingChatId).toBe("chat-b");
  });

  it("не поднимает индикатор проверки ответа по чужому потоку", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-b");

    store.setReviewing("chat-a", true);

    expect(useStreamStore.getState().isReviewing).toBe(false);
  });

  it("применяет запись владельца ровно как раньше, когда владелец совпал", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-b");

    store.applyEvent("chat-b", { type: "text_chunk", content: "ответ B" });
    store.setReviewing("chat-b", true);

    // Обратная сторона guard'а: он не должен глушить своего же владельца —
    // иначе стрим просто перестал бы показывать что-либо.
    const s = useStreamStore.getState();
    expect(s.feed).toEqual([
      { id: "text-0", type: "text", content: "ответ B" },
    ]);
    expect(s.isReviewing).toBe(true);
  });

  // Стрим уже закончился (`endStream` своего же владельца обнулил
  // `streamingChatId`) — записи, догоняющие погашенный ход, не воскрешают его.
  it.each<[string, (store: StreamActions) => void]>([
    [
      "applyEvent",
      (store) =>
        store.applyEvent("chat-a", {
          type: "text_chunk",
          content: "поздний хвост",
        }),
    ],
    ["redact", (store) => store.redact("chat-a", "[hidden]")],
    ["setReviewing", (store) => store.setReviewing("chat-a", true)],
    ["endStream", (store) => store.endStream("chat-a")],
  ])("оставляет погашенный стор нетронутым: %s без владельца", (_, write) => {
    const store = useStreamStore.getState();
    store.startStream("chat-a");
    store.endStream("chat-a");

    write(store);

    const s = useStreamStore.getState();
    expect(s.isStreaming).toBe(false);
    expect(s.streamingChatId).toBeNull();
    expect(s.feed).toEqual([]);
    expect(s.redacted).toBe(false);
    expect(s.isReviewing).toBe(false);
  });

  it("сбрасывает стор в idle неохраняемым reset независимо от владельца", () => {
    const store = useStreamStore.getState();
    store.startStream("chat-a");
    store.applyEvent("chat-a", { type: "text_chunk", content: "ответ A" });
    store.setReviewing("chat-a", true);

    // Уход с экрана владельца не знает и знать не должен: эфемерное состояние
    // чистится безусловно.
    store.reset();

    const s = useStreamStore.getState();
    expect(s.isStreaming).toBe(false);
    expect(s.streamingChatId).toBeNull();
    expect(s.feed).toEqual([]);
    expect(s.isReviewing).toBe(false);
  });
});
