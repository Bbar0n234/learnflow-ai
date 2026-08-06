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

  it("не переписывает состояние на месте — прежняя лента остаётся прежней", () => {
    // Лента живёт в zustand-сторе: мутация на месте не разбудила бы
    // подписчиков и оставила бы на экране предыдущий кадр.
    const before = run([
      { type: "text_chunk", content: "Начало" },
      { type: "tool_call_started", call_id: "c1", tool: "get_section" },
    ]);
    const snapshot = structuredClone(before);

    applyStreamEvent(
      before,
      { type: "text_chunk", content: " и конец" },
      2_000,
    );

    expect(before).toEqual(snapshot);
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

  it("адресует вложенный вызов по call_id на любой глубине", () => {
    const state = run([
      { type: "tool_call_started", call_id: "sub", tool: "run_subagent" },
      {
        type: "tool_call_started",
        call_id: "inner",
        tool: "run_subagent",
        parent_call_id: "sub",
      },
      {
        type: "tool_call_started",
        call_id: "deep",
        tool: "firecrawl_search",
        parent_call_id: "inner",
      },
      {
        type: "tool_result",
        call_id: "deep",
        tool: "firecrawl_search",
        status: "success",
        content: "нашлось",
        truncated: false,
        parent_call_id: "inner",
      },
    ]);

    expect(state.feed).toHaveLength(1);
    expect(call(state, "deep").status).toBe("success");
    expect(call(state, "inner").children).toHaveLength(1);
  });

  it("копит шаги субагента в порядке прихода, не путая их с корневыми", () => {
    const state = run([
      { type: "tool_call_started", call_id: "sub", tool: "run_subagent" },
      {
        type: "tool_call_started",
        call_id: "step-1",
        tool: "firecrawl_search",
        parent_call_id: "sub",
      },
      {
        type: "tool_call_started",
        call_id: "step-2",
        tool: "firecrawl_scrape",
        parent_call_id: "sub",
      },
      { type: "tool_call_started", call_id: "root-1", tool: "get_section" },
    ]);

    expect(state.feed.map((item) => item.id)).toEqual(["sub", "root-1"]);
    expect(call(state, "sub").children.map((item) => item.id)).toEqual([
      "step-1",
      "step-2",
    ]);
  });
});

describe("agent-feed: события вне ленты", () => {
  // Контракт растёт без версионирования (streaming.md § Forward-compat):
  // неизвестный тип обязан пройти мимо, не оставив следа на экране.
  it("не даёт строки на событии неизвестного типа", () => {
    const unknown = {
      type: "brand_new_event",
      payload: { anything: 1 },
    } as unknown as SSEEvent;

    const state = applyStreamEvent(EMPTY, unknown, 1_000);

    expect(state.feed).toEqual([]);
  });

  it.each<SSEEvent>([
    { type: "stream_started" },
    { type: "heartbeat" },
    { type: "final_output_review_started" },
    { type: "final_output_review_complete" },
    { type: "title_updated", title: "Производные" },
    { type: "artifact_created", id: "a1", title: "Notes", artifact_type: "md" },
    { type: "security_block" },
    { type: "cancelled" },
    { type: "error", detail: "модель упала" },
    { type: "done", message_id: "m1", trace_id: "t1" },
  ])("$type ленту не трогает", (event) => {
    // Служебные и терминальные события живут вне ленты: артефакты — своим
    // списком в сторе, ревью — флагом, причина остановки — состоянием экрана.
    const before = run([{ type: "text_chunk", content: "ответ" }]);

    const after = applyStreamEvent(before, event, 2_000);

    expect(after.feed).toEqual(before.feed);
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
        { type: "reasoning_chunk", content: "запоздалая мысль" },
        { type: "tool_call_started", call_id: "c2", tool: "get_section" },
        {
          type: "tool_result",
          call_id: "c2",
          tool: "get_section",
          status: "success",
          content: "содержимое раздела",
          truncated: false,
        },
        { type: "agent_event", kind: "compaction", payload: {} },
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

  it.each(["success", "error", "pending"] as const)(
    "переносит статус вызова %s без подмены",
    (status) => {
      // Три состояния вызова в истории; `pending` — вызов оборванного хода, и
      // подменить его на ошибку значило бы соврать о том, что произошло.
      const [item] = fromMessageParts([
        {
          type: "tool_call",
          call_id: "c1",
          tool: "firecrawl_search",
          args: '{"query": "langgraph"}',
          args_truncated: false,
          status,
          result_preview: status === "pending" ? "" : "результат",
          result_truncated: false,
        },
      ]);

      expect(item).toMatchObject({ status, tool: "firecrawl_search" });
    },
  );

  it("сохраняет порядок частей хода", () => {
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
    ]);

    expect(feed.map((item) => item.type)).toEqual([
      "reasoning",
      "tool_call",
      "text",
    ]);
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

  it("совпадает и на ходе с несколькими вызовами, ошибкой и усечением", () => {
    // Ход, на котором расхождение стоит дороже всего: два вызова подряд, у
    // одного оборваны аргументы, у другого — результат, второй вызов упал.
    // Если хоть один флаг или статус разъедется, перезагрузка страницы покажет
    // не то, что пользователь видел живым.
    const live = run([
      { type: "reasoning_chunk", content: "Сначала поищу" },
      { type: "tool_call_started", call_id: "c1", tool: "firecrawl_search" },
      {
        type: "tool_call_args",
        call_id: "c1",
        args: '{"query": "очень длинный запр',
        truncated: true,
      },
      {
        type: "tool_result",
        call_id: "c1",
        tool: "firecrawl_search",
        status: "success",
        content: "нашлось",
        truncated: false,
      },
      { type: "tool_call_started", call_id: "c2", tool: "update_section" },
      {
        type: "tool_call_args",
        call_id: "c2",
        args: '{"section_id": "Субагенты"}',
        truncated: false,
      },
      {
        type: "tool_result",
        call_id: "c2",
        tool: "update_section",
        status: "error",
        content: "раздела нет",
        truncated: true,
      },
      { type: "text_chunk", content: "Не вышло." },
    ]);

    const parts: MessagePart[] = [
      { type: "reasoning", content: "Сначала поищу" },
      {
        type: "tool_call",
        call_id: "c1",
        tool: "firecrawl_search",
        args: '{"query": "очень длинный запр',
        args_truncated: true,
        status: "success",
        result_preview: "нашлось",
        result_truncated: false,
      },
      {
        type: "tool_call",
        call_id: "c2",
        tool: "update_section",
        args: '{"section_id": "Субагенты"}',
        args_truncated: false,
        status: "error",
        result_preview: "раздела нет",
        result_truncated: true,
      },
      { type: "text", content: "Не вышло." },
    ];

    expect(withoutTiming(live.feed)).toEqual(
      withoutTiming(fromMessageParts(parts)),
    );
  });

  it("совпадает на ходе, оборванном отменой: вызов без результата", () => {
    // Отменённый ход приезжает из истории вызовом в статусе `pending` — той же
    // строкой, что осталась на экране незакрытой.
    const live = run([
      { type: "tool_call_started", call_id: "c1", tool: "run_subagent" },
      {
        type: "tool_call_args",
        call_id: "c1",
        args: '{"agent_type": "judge"}',
        truncated: false,
      },
    ]);
    const fromHistory = fromMessageParts([
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

    // Строка та же самая: тот же вызов, то же имя инструмента, те же
    // аргументы. Расходится только статус — живая строка ещё шла (`running`),
    // сохранённая уже знает, что результата не будет (`pending`).
    const identity = (feed: AgentFeedItem[]) =>
      feed.map((item) =>
        item.type === "tool_call"
          ? {
              id: item.id,
              callId: item.callId,
              tool: item.tool,
              args: item.args,
            }
          : item,
      );

    expect(identity(live.feed)).toEqual(identity(fromHistory));
    expect(findFeedCall(live.feed, "c1")?.status).toBe("running");
    expect(findFeedCall(fromHistory, "c1")?.status).toBe("pending");
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

  it("на пустой ленте блоков не даёт", () => {
    expect(groupFeedBlocks([])).toEqual([]);
  });

  it("ход из одного текста даёт единственный текстовый блок без ленты", () => {
    const blocks = groupFeedBlocks(
      fromMessageParts([{ type: "text", content: "Просто ответ." }]),
    );

    expect(blocks).toHaveLength(1);
    expect(blocks[0]?.type).toBe("text");
  });
});
