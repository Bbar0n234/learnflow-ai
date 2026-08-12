import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { describe, expect, it } from "vitest";

import type { Chat } from "@/shared/api/chats";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { ChatList } from "./ChatList";

// Integration (feat-002, T2.5): the project page as the first entry point into
// a chat. The user types a *message*, never a chat name (design-brief § Целевой
// UX); sending it creates the chat and opens it with the message handed over in
// router state, so the chat row appears only together with its first message. A
// failed creation must not swallow the typed text. Network is MSW.

const PROJECT_ID = "p1";
const CHATS_URL = `/api/projects/${PROJECT_ID}/chats`;
const FIRST_MESSAGE_PLACEHOLDER = "Спросите о чём угодно — начнётся новый чат…";

function chat(over: Partial<Chat> = {}): Chat {
  return {
    thread_id: "c1",
    title: "Производные",
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-01T10:00:00Z",
    security_blocked: false,
    ...over,
  };
}

function chatsResponse(items: Chat[]) {
  return HttpResponse.json({
    items,
    total: items.length,
    limit: 200,
    offset: 0,
  });
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

/**
 * The row menu trigger sits alongside the chat link, not inside it. It is an
 * icon-only button (no accessible name), so it is found by walking up from the
 * link until an ancestor holds a button outside of it — that keeps the query on
 * the behaviour ("next to the link") rather than on the row's exact nesting.
 */
function rowMenuTriggerFor(link: HTMLElement): HTMLElement {
  for (let row = link.parentElement; row; row = row.parentElement) {
    const trigger = within(row)
      .queryAllByRole("button")
      .find((button) => !link.contains(button));
    if (trigger) return trigger;
  }
  throw new Error("Меню строки чата не найдено рядом со ссылкой");
}

function renderChatList() {
  return renderWithProviders(
    <MemoryRouter initialEntries={[`/projects/${PROJECT_ID}`]}>
      <Routes>
        <Route path="/projects/:id" element={<ChatList />} />
        <Route path="/projects/:id/chats/:cid" element={<ChatEntryProbe />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ChatList", () => {
  it("asks for the first message, not for a chat name", async () => {
    server.use(http.get(CHATS_URL, () => chatsResponse([])));

    renderChatList();

    expect(
      await screen.findByPlaceholderText(FIRST_MESSAGE_PLACEHOLDER),
    ).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/Название/i)).not.toBeInTheDocument();
  });

  it("points a user with no chats at the message field above", async () => {
    server.use(http.get(CHATS_URL, () => chatsResponse([])));

    renderChatList();

    expect(
      await screen.findByText("Нет чатов. Начните с первого сообщения выше."),
    ).toBeInTheDocument();
  });

  it("creates the chat with an empty request and opens it with the typed message", async () => {
    let sentBody: string | null = null;
    server.use(
      http.get(CHATS_URL, () => chatsResponse([])),
      http.post(CHATS_URL, async ({ request }) => {
        sentBody = await request.text();
        return HttpResponse.json(chat({ thread_id: "c-new" }), { status: 201 });
      }),
    );
    const user = userEvent.setup();
    renderChatList();

    await user.type(
      await screen.findByPlaceholderText(FIRST_MESSAGE_PLACEHOLDER),
      "Объясни производные",
    );
    await user.click(screen.getByRole("button"));

    expect(
      await screen.findByText(
        `Открыт чат: /projects/${PROJECT_ID}/chats/c-new`,
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Первое сообщение: Объясни производные"),
    ).toBeInTheDocument();
    // The user names no chat: the create request carries no payload at all.
    expect(sentBody).toBe("");
  });

  it("sends the first message on Enter", async () => {
    server.use(
      http.get(CHATS_URL, () => chatsResponse([])),
      http.post(CHATS_URL, () =>
        HttpResponse.json(chat({ thread_id: "c-enter" }), { status: 201 }),
      ),
    );
    const user = userEvent.setup();
    renderChatList();

    await user.type(
      await screen.findByPlaceholderText(FIRST_MESSAGE_PLACEHOLDER),
      "Привет{Enter}",
    );

    expect(
      await screen.findByText(
        `Открыт чат: /projects/${PROJECT_ID}/chats/c-enter`,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Первое сообщение: Привет")).toBeInTheDocument();
  });

  it("treats Shift+Enter as a line break, not as sending", async () => {
    server.use(http.get(CHATS_URL, () => chatsResponse([])));
    const user = userEvent.setup();
    renderChatList();

    const field = await screen.findByPlaceholderText(FIRST_MESSAGE_PLACEHOLDER);
    await user.type(field, "Первая строка{Shift>}{Enter}{/Shift}вторая");

    // Still on the project page, text intact — no chat was created (an
    // unhandled POST would fail the run, MSW `onUnhandledRequest: "error"`).
    expect(field).toHaveValue("Первая строка\nвторая");
    expect(screen.queryByText(/Открыт чат/)).not.toBeInTheDocument();
  });

  it("refuses to send an empty message", async () => {
    server.use(http.get(CHATS_URL, () => chatsResponse([])));

    renderChatList();

    await screen.findByPlaceholderText(FIRST_MESSAGE_PLACEHOLDER);
    expect(screen.getByRole("button")).toBeDisabled();
  });

  it("keeps the typed message when the chat could not be created", async () => {
    server.use(
      http.get(CHATS_URL, () => chatsResponse([])),
      http.post(CHATS_URL, () =>
        HttpResponse.json({ detail: "Проект недоступен" }, { status: 403 }),
      ),
    );
    const user = userEvent.setup();
    renderChatList();

    const field = await screen.findByPlaceholderText(FIRST_MESSAGE_PLACEHOLDER);
    await user.type(field, "Объясни интегралы");
    await user.click(screen.getByRole("button"));

    expect(await screen.findByText("Проект недоступен")).toBeInTheDocument();
    expect(field).toHaveValue("Объясни интегралы");
    expect(screen.queryByText(/Открыт чат/)).not.toBeInTheDocument();
  });

  it("lists existing chats with a link and a row menu", async () => {
    server.use(
      http.get(CHATS_URL, () =>
        chatsResponse([chat({ thread_id: "c1", title: "Производные" })]),
      ),
    );

    const user = userEvent.setup();
    renderChatList();

    const link = await screen.findByRole("link", { name: /Производные/ });
    expect(link).toHaveAttribute("href", `/projects/${PROJECT_ID}/chats/c1`);
    // The row menu lives next to the link, not inside it: opening it offers the
    // chat actions and does not navigate into the chat.
    const trigger = rowMenuTriggerFor(link);
    expect(link).not.toContainElement(trigger);
    await user.click(trigger);
    expect(
      await screen.findByRole("menuitem", { name: "Переименовать" }),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Открыт чат/)).not.toBeInTheDocument();
  });

  it("holds the list with placeholders while it loads, without claiming it is empty", async () => {
    server.use(
      http.get(CHATS_URL, async () => {
        await delay(50);
        return chatsResponse([]);
      }),
    );

    const { container } = renderChatList();

    // Плашки скелетона не имеют доступного имени, поэтому берём публичный
    // маркер примитива дизайн-системы (`data-slot="skeleton"`) — последняя
    // ступень лестницы запросов из testing.md § Frontend. Геометрия и
    // мерцание в jsdom не исполняются: их сторожит ручной кейс.
    expect(
      container.querySelectorAll('[data-slot="skeleton"]').length,
    ).toBeGreaterThan(0);
    // Пока данные в пути, пустой список не объявляется — иначе на каждом
    // открытии проекта мигало бы «нет чатов».
    expect(
      screen.queryByText("Нет чатов. Начните с первого сообщения выше."),
    ).not.toBeInTheDocument();

    await screen.findByText("Нет чатов. Начните с первого сообщения выше.");
  });

  it("reports a failure to load the chat list", async () => {
    server.use(
      http.get(CHATS_URL, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderChatList();

    expect(
      await screen.findByText("Не удалось загрузить чаты."),
    ).toBeInTheDocument();
  });

  it("recovers the chat list from a failure through «Повторить»", async () => {
    let failing = true;
    server.use(
      http.get(CHATS_URL, () => {
        if (failing) {
          return HttpResponse.json({ detail: "boom" }, { status: 500 });
        }
        return chatsResponse([chat({ title: "Производные" })]);
      }),
    );
    const user = userEvent.setup();
    renderChatList();

    await screen.findByText("Не удалось загрузить чаты.");
    failing = false;
    // Путь восстановления помимо F5: кнопка перезапрашивает ту же квери.
    await user.click(screen.getByRole("button", { name: "Повторить" }));

    expect(
      await screen.findByRole("link", { name: /Производные/ }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Не удалось загрузить чаты."),
    ).not.toBeInTheDocument();
  });

  it("does not create a chat while the previous request is still in flight", async () => {
    let postCount = 0;
    // The creation is held open by the test, so the second click really lands
    // while the first request is in flight — with an instant response the
    // component would already be gone and the guard never exercised.
    let releaseCreate!: () => void;
    const createHeld = new Promise<void>((resolve) => {
      releaseCreate = resolve;
    });
    server.use(
      http.get(CHATS_URL, () => chatsResponse([])),
      http.post(CHATS_URL, async () => {
        postCount += 1;
        await createHeld;
        return HttpResponse.json(chat({ thread_id: "c-slow" }), {
          status: 201,
        });
      }),
    );
    const user = userEvent.setup();
    renderChatList();

    const field = await screen.findByPlaceholderText(FIRST_MESSAGE_PLACEHOLDER);
    await user.type(field, "Дважды");
    const sendButton = screen.getByRole("button");
    await user.click(sendButton);
    await waitFor(() => expect(sendButton).toBeDisabled());
    await user.click(sendButton);
    expect(postCount).toBe(1);

    releaseCreate();
    await waitFor(() =>
      expect(screen.getByText(/Открыт чат/)).toBeInTheDocument(),
    );
    expect(postCount).toBe(1);
  });
});
