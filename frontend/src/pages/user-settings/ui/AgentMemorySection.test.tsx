import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import type { MemoryItem } from "@/shared/api/user-memory";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { AgentMemorySection } from "./AgentMemorySection";

// Integration: the agent-memory list. Loads memories from /users/me/memories,
// renders each fact, and deletes one (DELETE + refetch). Loading and empty states
// are covered. Network is MSW.

const URL = "/api/users/me/memories";

function memory(over: Partial<MemoryItem> = {}): MemoryItem {
  return {
    key: "fav_language",
    description: "Preferred programming language",
    content: "Python",
    created_at: "2026-06-01T10:00:00Z",
    ...over,
  };
}

function page(items: MemoryItem[]) {
  return HttpResponse.json({
    items,
    total: items.length,
    limit: 50,
    offset: 0,
  });
}

describe("AgentMemorySection", () => {
  it("shows a loading hint while memories are in flight", () => {
    server.use(
      http.get(URL, async () => {
        await delay(50);
        return page([]);
      }),
    );

    renderWithProviders(<AgentMemorySection />);

    expect(screen.getByText("Загрузка памяти…")).toBeInTheDocument();
  });

  it("shows an empty-state message when there are no memories", async () => {
    server.use(http.get(URL, () => page([])));

    renderWithProviders(<AgentMemorySection />);

    expect(await screen.findByText(/Нет записей/)).toBeInTheDocument();
  });

  it("renders a saved memory's key, description and content", async () => {
    server.use(http.get(URL, () => page([memory()])));

    renderWithProviders(<AgentMemorySection />);

    expect(await screen.findByText("fav_language")).toBeInTheDocument();
    expect(
      screen.getByText("Preferred programming language"),
    ).toBeInTheDocument();
    expect(screen.getByText("Python")).toBeInTheDocument();
  });

  it("deletes a memory and refetches the list", async () => {
    let deleted = false;
    let deletedKey: string | null = null;
    server.use(
      http.get(URL, () => page(deleted ? [] : [memory()])),
      http.delete(`${URL}/:key`, ({ params }) => {
        deleted = true;
        deletedKey = params.key as string;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<AgentMemorySection />);
    await screen.findByText("fav_language");

    await user.click(screen.getByRole("button", { name: "Удалить запись" }));

    await waitFor(() => expect(deletedKey).toBe("fav_language"));
    await waitFor(() =>
      expect(screen.getByText(/Нет записей/)).toBeInTheDocument(),
    );
  });
});
