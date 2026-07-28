import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it } from "vitest";

import type { Chat } from "@/shared/api/chats";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { ChatDraft } from "./ChatDraft";

// Integration (feat-002, T2.6): the composer at `/projects/:id/chats/new` — a
// chat that does not exist yet. Contract (design-brief § Создание чата и первое
// сообщение, § Целевой UX): nothing is written to the DB until the first
// message is sent, thread-scoped controls stay hidden until there is a
// `thread_id`, and the typed text survives a failed creation. MSW is configured
// to fail on unhandled requests, which is what proves "no thread-scoped
// network" here.

const PROJECT_ID = "p1";
const CHATS_URL = `/api/projects/${PROJECT_ID}/chats`;
const PROJECT_URL = `/api/projects/${PROJECT_ID}`;

function chat(over: Partial<Chat> = {}): Chat {
  return {
    thread_id: "c-new",
    title: "Новый чат",
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-01T10:00:00Z",
    security_blocked: false,
    ...over,
  };
}

function projectHandler() {
  return http.get(PROJECT_URL, () =>
    HttpResponse.json({
      id: PROJECT_ID,
      name: "Матан",
      created_at: "2026-07-01T10:00:00Z",
      updated_at: "2026-07-01T10:00:00Z",
    }),
  );
}

/** Landing screen of the handoff — reports where we ended up and with what. */
function ChatEntryProbe() {
  const location = useLocation();
  const state = location.state as { initialMessage?: string } | null;
  return (
    <div>
      <p>Открыт чат: {location.pathname}</p>
      <p>Первое сообщение: {state?.initialMessage ?? "—"}</p>
    </div>
  );
}

function renderDraft() {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/projects/${PROJECT_ID}/chats/new`]}>
      <Routes>
        <Route path="/projects/:id/chats/new" element={<ChatDraft />} />
        <Route path="/projects/:id/chats/:cid" element={<ChatEntryProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ChatDraft", () => {
  it("explains that the chat appears together with the first message", async () => {
    server.use(projectHandler());

    renderDraft();

    expect(
      await screen.findByText(
        "Напишите первое сообщение — чат появится вместе с ним, а название придумает модель.",
      ),
    ).toBeInTheDocument();
    // The placeholder title is what the header shows until the model names it —
    // not the generic fallback the header falls back to without a loaded chat.
    expect(screen.getAllByText("Новый чат").length).toBeGreaterThan(0);
    expect(screen.queryByText("Чат")).not.toBeInTheDocument();
  });

  it("hides the thread-scoped controls until the chat exists", async () => {
    server.use(projectHandler());

    renderDraft();

    await screen.findByPlaceholderText("Сообщение...");
    expect(
      screen.queryByRole("button", { name: "Модель" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Инструменты" }),
    ).not.toBeInTheDocument();
  });

  it("creates the chat on the first message and opens it with that message", async () => {
    let sentBody: string | null = null;
    server.use(
      projectHandler(),
      http.post(CHATS_URL, async ({ request }) => {
        sentBody = await request.text();
        return HttpResponse.json(chat(), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderDraft();

    await user.type(
      await screen.findByPlaceholderText("Сообщение..."),
      "Объясни ряды{Enter}",
    );

    expect(
      await screen.findByText(
        `Открыт чат: /projects/${PROJECT_ID}/chats/c-new`,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Первое сообщение: Объясни ряды"),
    ).toBeInTheDocument();
    expect(sentBody).toBe("");
  });

  it("keeps the typed message when the chat could not be created", async () => {
    server.use(
      projectHandler(),
      http.post(CHATS_URL, () =>
        HttpResponse.json({ detail: "Проект недоступен" }, { status: 403 }),
      ),
    );
    const user = userEvent.setup();
    renderDraft();

    const field = await screen.findByPlaceholderText("Сообщение...");
    await user.type(field, "Объясни ряды");
    await user.click(screen.getByRole("button", { name: "Отправить" }));

    expect(await screen.findByText("Проект недоступен")).toBeInTheDocument();
    expect(field).toHaveValue("Объясни ряды");
    expect(screen.queryByText(/Открыт чат/)).not.toBeInTheDocument();
  });
});
