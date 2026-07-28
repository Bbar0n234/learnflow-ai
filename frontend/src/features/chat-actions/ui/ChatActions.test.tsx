import "@/test/pointer-event-polyfill";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";

import { describe, expect, it } from "vitest";

import { CHAT_TITLE_MAX_LENGTH, type Chat } from "@/shared/api/chats";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { ChatActions } from "./ChatActions";

// Integration (feat-002, T2.3): rename and delete of a chat, offered from the
// project chat list and from sidebar recents. Contract (design-brief § Rename и
// delete, § Frontend: раскладка): rename is capped at 100 characters and hits
// PUT, delete asks for a destructive confirmation and hits DELETE; a failed
// mutation keeps its dialog open with the message inline; deleting the chat the
// user currently has open moves them to the project page, while deleting from
// any other screen leaves navigation alone. Network is MSW.

const PROJECT_ID = "p1";
const CHAT_ID = "c1";
const CHAT_URL = `/api/projects/${PROJECT_ID}/chats/${CHAT_ID}`;
const CURRENT_TITLE = "Новый чат";

function chat(title: string): Chat {
  return {
    thread_id: CHAT_ID,
    title,
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-01T10:00:00Z",
    security_blocked: false,
  };
}

function PathProbe() {
  const location = useLocation();
  return <p>Текущий путь: {location.pathname}</p>;
}

/**
 * Mounts the actions on a given screen. Both hosts of the slice live outside
 * the `chats/:cid` route subtree (chat list page, sidebar), so the component
 * decides "is this chat open?" from the URL — the test drives that URL.
 */
function renderChatActions(entry: string, title = CURRENT_TITLE) {
  const actions = (
    <>
      <ChatActions projectId={PROJECT_ID} chatId={CHAT_ID} title={title} />
      <PathProbe />
    </>
  );
  return renderWithProviders(
    <MemoryRouter initialEntries={[entry]}>
      <Routes>
        <Route path="/settings" element={actions} />
        <Route path="/projects/:id" element={actions} />
        <Route path="/projects/:id/chats/:cid" element={actions} />
      </Routes>
    </MemoryRouter>,
  );
}

async function openMenu(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button"));
}

async function openRenameDialog(user: ReturnType<typeof userEvent.setup>) {
  await openMenu(user);
  await user.click(
    await screen.findByRole("menuitem", { name: "Переименовать" }),
  );
  return screen.findByRole("textbox");
}

async function openDeleteDialog(user: ReturnType<typeof userEvent.setup>) {
  await openMenu(user);
  await user.click(await screen.findByRole("menuitem", { name: "Удалить" }));
}

describe("ChatActions", () => {
  it("offers rename and delete from the row menu", async () => {
    const user = userEvent.setup();
    renderChatActions(`/projects/${PROJECT_ID}`);

    await openMenu(user);

    expect(
      await screen.findByRole("menuitem", { name: "Переименовать" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("menuitem", { name: "Удалить" }),
    ).toBeInTheDocument();
  });

  it("renames the chat and closes the dialog", async () => {
    const user = userEvent.setup();
    let sentBody: unknown = null;
    server.use(
      http.put(CHAT_URL, async ({ request }) => {
        sentBody = await request.json();
        return HttpResponse.json(chat("Производные"));
      }),
    );
    renderChatActions(`/projects/${PROJECT_ID}`);

    const input = await openRenameDialog(user);
    await user.clear(input);
    await user.type(input, "Производные");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    await waitFor(() => expect(sentBody).toEqual({ title: "Производные" }));
    await waitFor(() =>
      expect(screen.queryByText("Переименовать чат")).not.toBeInTheDocument(),
    );
  });

  it("prefills the current title and refuses an empty or unchanged one", async () => {
    const user = userEvent.setup();
    renderChatActions(`/projects/${PROJECT_ID}`);

    const input = await openRenameDialog(user);

    expect(input).toHaveValue(CURRENT_TITLE);
    // Unchanged value — nothing to save.
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();
    await user.clear(input);
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeDisabled();
  });

  it("caps the new title at the agreed length limit", async () => {
    const user = userEvent.setup();
    renderChatActions(`/projects/${PROJECT_ID}`);

    const input = await openRenameDialog(user);
    await user.clear(input);
    await user.paste("я".repeat(CHAT_TITLE_MAX_LENGTH + 10));

    // Anything past the limit simply does not go in — the user cannot submit a
    // title the server would reject.
    expect(input).toHaveValue("я".repeat(CHAT_TITLE_MAX_LENGTH));
  });

  it("keeps the rename dialog open and shows why the rename failed", async () => {
    const user = userEvent.setup();
    server.use(
      http.put(CHAT_URL, () =>
        HttpResponse.json(
          { detail: "Название слишком длинное" },
          { status: 422 },
        ),
      ),
    );
    renderChatActions(`/projects/${PROJECT_ID}`);

    const input = await openRenameDialog(user);
    await user.clear(input);
    await user.type(input, "Другое название");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(
      await screen.findByText("Название слишком длинное"),
    ).toBeInTheDocument();
    expect(screen.getByText("Переименовать чат")).toBeInTheDocument();
  });

  it("warns that deleting is irreversible and keeps the artifacts", async () => {
    const user = userEvent.setup();
    renderChatActions(`/projects/${PROJECT_ID}`);

    await openDeleteDialog(user);

    expect(await screen.findByText("Удалить чат")).toBeInTheDocument();
    expect(
      screen.getByText(/История сообщений будет удалена/),
    ).toBeInTheDocument();
    expect(screen.getByText(/нельзя отменить/)).toBeInTheDocument();
    expect(
      screen.getByText(/Артефакты чата останутся в проекте/),
    ).toBeInTheDocument();
  });

  it("deletes the chat on confirmation", async () => {
    const user = userEvent.setup();
    let deleted = false;
    server.use(
      http.delete(CHAT_URL, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderChatActions(`/projects/${PROJECT_ID}`);

    await openDeleteDialog(user);
    await user.click(await screen.findByRole("button", { name: "Удалить" }));

    await waitFor(() => expect(deleted).toBe(true));
  });

  it("moves the user to the project page when the open chat is deleted", async () => {
    const user = userEvent.setup();
    server.use(
      http.delete(CHAT_URL, () => new HttpResponse(null, { status: 204 })),
    );
    renderChatActions(`/projects/${PROJECT_ID}/chats/${CHAT_ID}`);

    await openDeleteDialog(user);
    await user.click(await screen.findByRole("button", { name: "Удалить" }));

    expect(
      await screen.findByText(`Текущий путь: /projects/${PROJECT_ID}`),
    ).toBeInTheDocument();
  });

  it("stays on the current screen when another chat is deleted from recents", async () => {
    const user = userEvent.setup();
    server.use(
      http.delete(CHAT_URL, () => new HttpResponse(null, { status: 204 })),
    );
    renderChatActions("/settings");

    await openDeleteDialog(user);
    await user.click(await screen.findByRole("button", { name: "Удалить" }));

    await waitFor(() =>
      expect(screen.queryByText("Удалить чат")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Текущий путь: /settings")).toBeInTheDocument();
  });

  it("keeps the delete dialog open and shows why the delete failed", async () => {
    const user = userEvent.setup();
    server.use(
      http.delete(CHAT_URL, () =>
        HttpResponse.json({ detail: "Чат занят" }, { status: 409 }),
      ),
    );
    renderChatActions(`/projects/${PROJECT_ID}/chats/${CHAT_ID}`);

    await openDeleteDialog(user);
    await user.click(await screen.findByRole("button", { name: "Удалить" }));

    expect(await screen.findByText("Чат занят")).toBeInTheDocument();
    expect(screen.getByText("Удалить чат")).toBeInTheDocument();
    // A failed delete must not move the user away from the open chat.
    expect(
      screen.getByText(
        `Текущий путь: /projects/${PROJECT_ID}/chats/${CHAT_ID}`,
      ),
    ).toBeInTheDocument();
  });
});
