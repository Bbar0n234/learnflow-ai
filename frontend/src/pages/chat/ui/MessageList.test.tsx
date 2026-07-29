import { screen } from "@testing-library/react";
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

function renderFeed(feed: AgentFeedItem[]): void {
  const ui: ReactElement = (
    <MemoryRouter>
      <MessageList
        messages={[]}
        isStreaming
        feed={feed}
        streamingArtifacts={[]}
        projectId="p1"
        chatId="c1"
        streamError={null}
        onOpenLens={vi.fn()}
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
