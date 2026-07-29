import { describe, expect, it } from "vitest";

import type { MessagePart } from "@/shared/api/chats";
import type { SSEEvent } from "@/shared/api/sse";
import {
  applyStreamEvent,
  findFeedCall,
  fromMessageParts,
  groupFeedBlocks,
  redactFeed,
  type AgentFeedItem,
  type AgentFeedState,
} from "./agent-feed";

// Unit: чистая модель ленты активности. Проверяется механика нормализации —
// накопление чанков, жизненный цикл вызова по call_id, вложенность по
// parent_call_id, редакция и эквивалентность «live = история».

const EMPTY: AgentFeedState = { feed: [], redacted: false };

/** Прогон последовательности событий с фиксированной шкалой времени. */
function run(
  events: (SSEEvent | [SSEEvent, number])[],
  initial: AgentFeedState = EMPTY,
): AgentFeedState {
  return events.reduce<AgentFeedState>((state, entry) => {
    const [event, now] = Array.isArray(entry) ? entry : [entry, 1000];
    return applyStreamEvent(state, event, now);
  }, initial);
}

function call(state: AgentFeedState, callId: string) {
  const item = findFeedCall(state.feed, callId);
  if (item === null) throw new Error(`Строки вызова ${callId} нет в ленте`);
  return item;
}

describe("agent-feed: текстовые элементы", () => {
  it("копит чанки одного типа в один элемент", () => {
    const state = run([
      { type: "text_chunk", content: "Привет" },
      { type: "text_chunk", content: ", мир" },
    ]);

    expect(state.feed).toEqual([
      { id: "text-0", type: "text", content: "Привет, мир" },
    ]);
  });

  it("держит рассуждения и ответ раздельными элементами в порядке прихода", () => {
    const state = run([
      { type: "reasoning_chunk", content: "Надо " },
      { type: "reasoning_chunk", content: "проверить" },
      { type: "text_chunk", content: "Готово" },
    ]);

    expect(state.feed).toEqual([
      { id: "reasoning-0", type: "reasoning", content: "Надо проверить" },
      { id: "text-1", type: "text", content: "Готово" },
    ]);
  });

  it("открывает новый элемент, если между чанками была строка действия", () => {
    const state = run([
      { type: "text_chunk", content: "Сначала" },
      { type: "tool_call_started", call_id: "c1", tool: "get_section" },
      { type: "text_chunk", content: "потом" },
    ]);

    expect(state.feed.map((item) => item.type)).toEqual([
      "text",
      "tool_call",
      "text",
    ]);
  });
});

describe("agent-feed: жизненный цикл вызова", () => {
  it("заводит строку в состоянии running и запоминает момент старта", () => {
    const state = run([
      [
        { type: "tool_call_started", call_id: "c1", tool: "firecrawl_search" },
        5_000,
      ],
    ]);

    expect(call(state, "c1")).toMatchObject({
      tool: "firecrawl_search",
      status: "running",
      startedAt: 5_000,
      durationMs: null,
      args: null,
    });
  });

  it("дописывает аргументы и закрывает строку результатом с длительностью", () => {
    const state = run([
      [
        { type: "tool_call_started", call_id: "c1", tool: "firecrawl_search" },
        5_000,
      ],
      [
        {
          type: "tool_call_args",
          call_id: "c1",
          args: '{"query": "langgraph"}',
          truncated: false,
        },
        5_100,
      ],
      [
        {
          type: "tool_result",
          call_id: "c1",
          tool: "firecrawl_search",
          status: "success",
          content: "нашлось",
          truncated: false,
        },
        9_000,
      ],
    ]);

    expect(call(state, "c1")).toMatchObject({
      args: '{"query": "langgraph"}',
      argsTruncated: false,
      status: "success",
      result: "нашлось",
      durationMs: 4_000,
    });
  });

  it("переводит строку в cancelled на срезе вызова guard'ом", () => {
    const state = run([
      [
        { type: "tool_call_started", call_id: "c1", tool: "get_section" },
        1_000,
      ],
      [{ type: "tool_call_cancelled", call_id: "c1" }, 1_500],
    ]);

    expect(call(state, "c1")).toMatchObject({
      status: "cancelled",
      durationMs: 500,
    });
  });

  it("держит параллельные вызовы одновременно и закрывает их независимо", () => {
    const state = run([
      { type: "tool_call_started", call_id: "c1", tool: "firecrawl_search" },
      { type: "tool_call_started", call_id: "c2", tool: "get_section" },
      {
        type: "tool_result",
        call_id: "c1",
        tool: "firecrawl_search",
        status: "success",
        content: "первый",
        truncated: false,
      },
    ]);

    expect(state.feed).toHaveLength(2);
    expect(call(state, "c1").status).toBe("success");
    expect(call(state, "c2").status).toBe("running");
    expect(call(state, "c2").result).toBeNull();
  });

  it("не задваивает строку на повторном анонсе того же вызова", () => {
    const state = run([
      { type: "tool_call_started", call_id: "c1", tool: "get_section" },
      { type: "tool_call_started", call_id: "c1", tool: "get_section" },
    ]);

    expect(state.feed).toHaveLength(1);
  });

  it("показывает строку по результату, пришедшему без анонса", () => {
    const state = run([
      {
        type: "tool_result",
        call_id: "c9",
        tool: "load_skill",
        status: "error",
        content: "нет такого навыка",
        truncated: false,
      },
    ]);

    expect(call(state, "c9")).toMatchObject({
      tool: "load_skill",
      status: "error",
      result: "нет такого навыка",
    });
  });

  it("игнорирует аргументы и отмену неизвестного вызова, не роняя ленту", () => {
    const state = run([
      {
        type: "tool_call_args",
        call_id: "ghost",
        args: "{}",
        truncated: false,
      },
      { type: "tool_call_cancelled", call_id: "ghost" },
    ]);

    expect(state.feed).toEqual([]);
  });
});

describe("agent-feed: вложенность субагента", () => {
  it("укладывает события с parent_call_id во вложенную ленту родителя", () => {
    const state = run([
      { type: "tool_call_started", call_id: "sub", tool: "run_subagent" },
      {
        type: "tool_call_started",
        call_id: "inner",
        tool: "firecrawl_search",
        parent_call_id: "sub",
      },
      {
        type: "tool_result",
        call_id: "inner",
        tool: "firecrawl_search",
        status: "success",
        content: "нашлось",
        truncated: false,
        parent_call_id: "sub",
      },
    ]);

    expect(state.feed).toHaveLength(1);
    const parent = call(state, "sub");
    expect(parent.children).toHaveLength(1);
    expect(parent.children[0]).toMatchObject({
      type: "tool_call",
      callId: "inner",
      status: "success",
    });
  });

  it("оставляет элемент в корне, если родитель не анонсирован", () => {
    const state = run([
      {
        type: "tool_call_started",
        call_id: "inner",
        tool: "get_section",
        parent_call_id: "неизвестный",
      },
    ]);

    expect(state.feed).toHaveLength(1);
    expect(call(state, "inner").status).toBe("running");
  });
});

describe("agent-feed: доменные agent_event", () => {
  it("даёт строку только на компакцию", () => {
    const state = run([
      { type: "agent_event", kind: "compaction", payload: {} },
    ]);

    expect(state.feed).toEqual([
      {
        id: "agent_event-0",
        type: "agent_event",
        kind: "compaction",
        payload: {},
      },
    ]);
  });

  it("поглощает остальные доменные kind'ы без следа", () => {
    const state = run([
      { type: "agent_event", kind: "sphere_write", payload: { key: "s1" } },
      { type: "agent_event", kind: "memory_write", payload: {} },
      { type: "agent_event", kind: "skill_context_write", payload: {} },
    ]);

    expect(state.feed).toEqual([]);
  });

  it("не роняет модель на неизвестном kind", () => {
    const state = run([
      { type: "agent_event", kind: "совершенно_новый", payload: {} },
    ]);

    expect(state.feed).toEqual([]);
  });
});

describe("agent-feed: редакция по security_block", () => {
  it("заменяет ленту хода единственной заглушкой", () => {
    const before = run([
      { type: "reasoning_chunk", content: "секретные мысли" },
      { type: "tool_call_started", call_id: "c1", tool: "firecrawl_search" },
      { type: "text_chunk", content: "секретный ответ" },
    ]);

    expect(before.feed).toHaveLength(3);
    const state = redactFeed("[Сообщение скрыто]");

    expect(state.feed).toEqual([
      { id: "text-0", type: "text", content: "[Сообщение скрыто]" },
    ]);
    expect(state.redacted).toBe(true);
  });

  it("после редакции лента не принимает дописывающих событий", () => {
    const state = run(
      [
        { type: "text_chunk", content: " ещё" },
        { type: "tool_call_started", call_id: "c2", tool: "get_section" },
      ],
      redactFeed("[Сообщение скрыто]"),
    );

    expect(state.feed).toEqual([
      { id: "text-0", type: "text", content: "[Сообщение скрыто]" },
    ]);
  });
});

describe("agent-feed: адаптер истории", () => {
  it("переносит незавершённый вызов статусом pending", () => {
    const feed = fromMessageParts([
      {
        type: "tool_call",
        call_id: "c1",
        tool: "run_subagent",
        args: '{"agent_type": "judge"}',
        args_truncated: false,
        status: "pending",
        result_preview: "",
        result_truncated: false,
      },
    ]);

    expect(feed[0]).toMatchObject({ status: "pending", tool: "run_subagent" });
  });

  it("не помечает аргументы усечёнными, когда обрезан только результат", () => {
    const [item] = fromMessageParts([
      {
        type: "tool_call",
        call_id: "c1",
        tool: "firecrawl_search",
        args: '{"query": "langgraph"}',
        args_truncated: false,
        status: "success",
        result_preview: "очень длинный результат",
        result_truncated: true,
      },
    ]);

    expect(item).toMatchObject({ argsTruncated: false, resultTruncated: true });
  });

  it("не помечает результат усечённым, когда обрезаны только аргументы", () => {
    const [item] = fromMessageParts([
      {
        type: "tool_call",
        call_id: "c1",
        tool: "firecrawl_search",
        args: '{"query": "очень длинный запр',
        args_truncated: true,
        status: "success",
        result_preview: "ok",
        result_truncated: false,
      },
    ]);

    expect(item).toMatchObject({ argsTruncated: true, resultTruncated: false });
  });

  it("даёт пустую ленту на отсутствующих parts", () => {
    expect(fromMessageParts(undefined)).toEqual([]);
  });
});

describe("agent-feed: live = история", () => {
  // Длительность вызова — знание live: в истории временных меток нет вовсе
  // (streaming.md § История: typed parts). Всё остальное обязано совпадать.
  function withoutTiming(feed: AgentFeedItem[]): AgentFeedItem[] {
    return feed.map((item) =>
      item.type === "tool_call"
        ? {
            ...item,
            startedAt: null,
            durationMs: null,
            children: withoutTiming(item.children),
          }
        : item,
    );
  }

  it("даёт эквивалентную структуру на событиях и на parts одного хода", () => {
    const live = run([
      { type: "reasoning_chunk", content: "Надо " },
      { type: "reasoning_chunk", content: "поискать" },
      { type: "tool_call_started", call_id: "c1", tool: "firecrawl_search" },
      {
        type: "tool_call_args",
        call_id: "c1",
        args: '{"query": "langgraph"}',
        truncated: false,
      },
      {
        type: "tool_result",
        call_id: "c1",
        tool: "firecrawl_search",
        status: "success",
        content: "нашлось",
        truncated: false,
      },
      { type: "text_chunk", content: "Вот что нашлось" },
    ]);

    const parts: MessagePart[] = [
      { type: "reasoning", content: "Надо поискать" },
      {
        type: "tool_call",
        call_id: "c1",
        tool: "firecrawl_search",
        args: '{"query": "langgraph"}',
        args_truncated: false,
        status: "success",
        result_preview: "нашлось",
        result_truncated: false,
      },
      { type: "text", content: "Вот что нашлось" },
    ];

    expect(withoutTiming(live.feed)).toEqual(
      withoutTiming(fromMessageParts(parts)),
    );
  });
});

describe("agent-feed: блоки", () => {
  it("склеивает подряд идущие действия и отделяет текст", () => {
    const feed = fromMessageParts([
      { type: "reasoning", content: "думаю" },
      {
        type: "tool_call",
        call_id: "c1",
        tool: "get_section",
        args: "{}",
        args_truncated: false,
        status: "success",
        result_preview: "ok",
        result_truncated: false,
      },
      { type: "text", content: "ответ" },
      {
        type: "tool_call",
        call_id: "c2",
        tool: "create_artifact",
        args: "{}",
        args_truncated: false,
        status: "success",
        result_preview: "ok",
        result_truncated: false,
      },
    ]);

    const blocks = groupFeedBlocks(feed);

    expect(blocks.map((block) => block.type)).toEqual(["feed", "text", "feed"]);
    const first = blocks[0];
    expect(first?.type === "feed" ? first.items : []).toHaveLength(2);
  });
});
