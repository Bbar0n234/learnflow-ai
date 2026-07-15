import { screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import type { ReactElement } from "react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { useStreamStore } from "@/stores/stream-store";
import { renderWithProviders } from "@/test/test-utils";

import { MessageList } from "./MessageList";

// Integration: the message feed's streaming region (feat-010, T2.4). While
// streaming, one GeneratingArtifactCard renders per active generate_image
// call_id (from the stream store), and the generic ToolIndicator pill is
// suppressed specifically for generate_image (the placeholder card replaces
// it) while other tools still surface their pill. Zustand store auto-resets
// between tests (src/test/setup.ts).

// jsdom has no layout — MessageList auto-scrolls a ref into view on mount.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

function renderFeed(activeTool: string | null): void {
  const ui: ReactElement = (
    <MemoryRouter>
      <MessageList
        messages={[]}
        isStreaming
        streamingText=""
        activeTool={activeTool}
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

describe("MessageList — image generation placeholder", () => {
  it("renders one placeholder card per active generate_image call_id", () => {
    const store = useStreamStore.getState();
    store.addPendingImage("call-1");
    store.addPendingImage("call-2");

    renderFeed("generate_image");

    expect(
      screen.getAllByRole("status", { name: "Идёт генерация изображения" }),
    ).toHaveLength(2);
  });

  it("suppresses the tool pill for generate_image (placeholder replaces it)", () => {
    useStreamStore.getState().addPendingImage("call-1");

    renderFeed("generate_image");

    // The generic pill (which would show the tool name) is not rendered.
    expect(screen.queryByText("generate_image")).not.toBeInTheDocument();
    // The placeholder card stands in its place.
    expect(
      screen.getByRole("status", { name: "Идёт генерация изображения" }),
    ).toBeInTheDocument();
  });

  it("still shows the tool pill for a non-image tool", () => {
    renderFeed("web_search");

    expect(screen.getByText("web_search")).toBeInTheDocument();
    expect(
      screen.queryByRole("status", { name: "Идёт генерация изображения" }),
    ).not.toBeInTheDocument();
  });

  it("shows no placeholder cards when there are no pending generations", () => {
    renderFeed(null);

    expect(
      screen.queryByRole("status", { name: "Идёт генерация изображения" }),
    ).not.toBeInTheDocument();
  });
});
