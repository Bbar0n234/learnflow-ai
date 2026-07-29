import { act, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import type { ReactElement } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { SSEEvent } from "@/shared/api/sse";
import {
  applyStreamEvent,
  type AgentFeedItem,
  type AgentFeedState,
} from "@/shared/lib/agent-feed";
import { renderWithProviders } from "@/test/test-utils";

import { MessageList } from "./MessageList";
import type { StreamEndReason } from "./StreamEndNotice";

// Integration: the streaming region of the message feed. Live activity is the
// same feed the history renders (`shared/lib/agent-feed`), and on top of it the
// image generation placeholder lives for exactly as long as a `generate_image`
// call stays unclosed — it appears with the call's args and goes away on the
// call's result (feat-001, T2.4: покрытие переехало с `tool_start`/`tool_end`).

// jsdom has no layout — MessageList auto-scrolls a ref into view on mount.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

/** Лента, собранная тем же редьюсером, что работает в сторе на live-потоке. */
function feedFrom(events: SSEEvent[]): AgentFeedItem[] {
  const initial: AgentFeedState = { feed: [], redacted: false };
  return events.reduce(
    (state, event) => applyStreamEvent(state, event),
    initial,
  ).feed;
}

interface RenderOptions {
  isStreaming?: boolean;
  endNotice?: StreamEndReason | null;
}

function renderFeed(feed: AgentFeedItem[], options: RenderOptions = {}): void {
  const ui: ReactElement = (
    <MemoryRouter>
      <MessageList
        messages={[]}
        isStreaming={options.isStreaming ?? true}
        feed={feed}
        streamingArtifacts={[]}
        projectId="p1"
        chatId="c1"
        streamError={null}
        endNotice={options.endNotice ?? null}
      />
    </MemoryRouter>
  );
  renderWithProviders(ui);
}

const GENERATION_LABEL = "Идёт генерация изображения";

function imageCall(callId: string, prompt: string): SSEEvent[] {
  return [
    { type: "tool_call_started", call_id: callId, tool: "generate_image" },
    {
      type: "tool_call_args",
      call_id: callId,
      args: JSON.stringify({ prompt }),
      truncated: false,
    },
  ];
}

describe("MessageList — image generation placeholder", () => {
  it("renders one placeholder card per unfinished generate_image call", () => {
    renderFeed(
      feedFrom([
        ...imageCall("call-1", "кот на подоконнике"),
        ...imageCall("call-2", "график производной"),
      ]),
    );

    expect(
      screen.getAllByRole("status", { name: GENERATION_LABEL }),
    ).toHaveLength(2);
  });

  it("drops the placeholder once the call returns its result", () => {
    renderFeed(
      feedFrom([
        ...imageCall("call-1", "кот на подоконнике"),
        {
          type: "tool_result",
          call_id: "call-1",
          tool: "generate_image",
          status: "success",
          content: "готово",
          truncated: false,
        },
      ]),
    );

    expect(
      screen.queryByRole("status", { name: GENERATION_LABEL }),
    ).not.toBeInTheDocument();
  });

  it("shows no placeholder for a non-image tool call", () => {
    renderFeed(
      feedFrom([
        {
          type: "tool_call_started",
          call_id: "call-9",
          tool: "firecrawl_search",
        },
        {
          type: "tool_call_args",
          call_id: "call-9",
          args: JSON.stringify({ query: "langgraph" }),
          truncated: false,
        },
      ]),
    );

    // Работа инструмента видна строкой ленты, а не карточкой генерации.
    expect(screen.getByText(/Ищу в интернете/)).toBeInTheDocument();
    expect(
      screen.queryByRole("status", { name: GENERATION_LABEL }),
    ).not.toBeInTheDocument();
  });

  it("shows no placeholder cards on an empty feed", () => {
    renderFeed([]);

    expect(
      screen.queryByRole("status", { name: GENERATION_LABEL }),
    ).not.toBeInTheDocument();
  });
});

// Смоук фазы T2.5: живость и терминальные состояния. Покрытие снятого
// индикатора «агент думает» переехало сюда — на строку-паузу, которая приняла
// его роль.
describe("MessageList — живость ленты", () => {
  it("держит строку-паузу, пока в ленте нет ни одного события", () => {
    renderFeed([]);

    expect(
      screen.getByRole("status", { name: "Агент думает" }),
    ).toBeInTheDocument();
  });

  it("снимает строку-паузу с первым содержательным событием", () => {
    renderFeed(
      feedFrom([
        { type: "tool_call_started", call_id: "call-1", tool: "get_section" },
      ]),
    );

    expect(
      screen.queryByRole("status", { name: "Агент думает" }),
    ).not.toBeInTheDocument();
  });

  it("подписывает хвостовое рассуждение процессом, а завершённое — следом", () => {
    renderFeed(
      feedFrom([{ type: "reasoning_chunk", content: "надо поискать" }]),
    );

    expect(screen.getByText("Рассуждает")).toBeInTheDocument();
  });

  it("сворачивает рассуждение, когда поток ушёл в следующее действие", () => {
    renderFeed(
      feedFrom([
        { type: "reasoning_chunk", content: "надо поискать" },
        {
          type: "tool_call_started",
          call_id: "call-1",
          tool: "firecrawl_search",
        },
      ]),
    );

    expect(screen.getByText("Рассуждения")).toBeInTheDocument();
    expect(screen.queryByText("Рассуждает")).not.toBeInTheDocument();
  });

  it("показывает счётчик времени у действия, идущего дольше порога", async () => {
    vi.useFakeTimers();
    try {
      const feed = feedFrom([
        {
          type: "tool_call_started",
          call_id: "call-1",
          tool: "firecrawl_search",
        },
      ]);
      renderFeed(feed);

      expect(screen.queryByText("0:04")).not.toBeInTheDocument();

      await act(async () => {
        vi.advanceTimersByTime(4000);
      });

      expect(screen.getByText("0:04")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

// Смоук фазы T2.6: вложенность приезжает единственным признаком —
// `parent_call_id`; шаги субагента видны в live внутри строки его вызова.
describe("MessageList — вложенная лента субагента", () => {
  const subagentCall: SSEEvent[] = [
    { type: "tool_call_started", call_id: "sub-1", tool: "run_subagent" },
    {
      type: "tool_call_args",
      call_id: "sub-1",
      args: JSON.stringify({ agent_type: "judge", task: "Проверь выводы." }),
      truncated: false,
    },
  ];

  it("показывает шаги субагента строками внутри его вызова", () => {
    renderFeed(
      feedFrom([
        ...subagentCall,
        {
          type: "tool_call_started",
          call_id: "step-1",
          tool: "firecrawl_scrape",
          parent_call_id: "sub-1",
        },
        {
          type: "tool_call_args",
          call_id: "step-1",
          args: JSON.stringify({ url: "docs.langchain.com/subagents" }),
          truncated: false,
          parent_call_id: "sub-1",
        },
      ]),
    );

    // Идущий субагент развёрнут сам — шаги видны без клика.
    expect(screen.getByText(/Проверяющий субагент/)).toBeInTheDocument();
    expect(screen.getByText("Проверь выводы.")).toBeInTheDocument();
    expect(screen.getByText(/Читаю страницу/)).toBeInTheDocument();
  });

  it("не рисует синтетической первой строки вложенной ленты", () => {
    renderFeed(feedFrom(subagentCall));

    expect(screen.queryByText(/Получил задание/)).not.toBeInTheDocument();
  });

  it("закрывает строку субагента вердиктом", () => {
    renderFeed(
      feedFrom([
        ...subagentCall,
        {
          type: "tool_result",
          call_id: "sub-1",
          tool: "run_subagent",
          status: "success",
          content: "Три замечания по формулировкам.",
          truncated: false,
        },
      ]),
    );

    expect(screen.getByText("успешно")).toBeInTheDocument();
    // Завершённый субагент сворачивается — вердикт открывается по клику.
    expect(
      screen.queryByText("Три замечания по формулировкам."),
    ).not.toBeInTheDocument();
  });
});

describe("MessageList — терминальные состояния", () => {
  it("сообщает об остановке генерации нейтральной строкой, без ошибки", () => {
    renderFeed([], { isStreaming: false, endNotice: "cancelled" });

    expect(screen.getByText("Генерация остановлена")).toBeInTheDocument();
  });

  it("ставит generic-карточку блокировки без деталей срабатывания", () => {
    renderFeed([], { isStreaming: false, endNotice: "blocked" });

    expect(
      screen.getByText("Ход остановлен системой безопасности"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Генерация остановлена")).not.toBeInTheDocument();
  });

  it("не показывает терминальное уведомление, пока ход идёт", () => {
    renderFeed([], { isStreaming: true, endNotice: "cancelled" });

    expect(screen.queryByText("Генерация остановлена")).not.toBeInTheDocument();
  });
});
