import {
  act,
  fireEvent,
  screen,
  waitFor,
  waitForElementToBeRemoved,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { Project } from "@/shared/api/projects";
import { server } from "@/test/msw/server";
import { routerAt } from "@/test/router";
import { renderWithProviders } from "@/test/test-utils";

import { ProjectSettingsPage } from "./ProjectSettingsPage";

// Integration (feat-013, T3.2 + T3.3): the project name row on the settings page
// is an inline edit. Contract (design-brief § 5.2 and both of its refinements):
// the name reads as text until the pencil opens an input seeded with a snapshot;
// Enter and the check button commit, Esc and the cross discard; an external
// rename arriving while the editor is open never overwrites the draft, and
// cancelling afterwards drops the user back onto the fresh server value; while
// the write is in flight nothing cancels it; a successful write confirms itself
// with a short "Сохранено" status and the row shows the name that was just
// saved, never a frame of the old one beside the confirmation. Network is MSW.
//
// The field is always reached by its accessible name ("Имя проекта"), never by a
// bare role: the caption is what makes the control announceable, so losing the
// label/control link has to redden this suite instead of passing unnoticed.

const PROJECT_ID = "p1";
const PROJECT_URL = `/api/projects/${PROJECT_ID}`;
const INITIAL_NAME = "Электрика в гараже";
const NEW_NAME = "Электрика в мастерской";

// What GET /api/projects/p1 answers right now — tests move it to play out an
// external rename or a server that has not caught up with the write yet.
let serverName = INITIAL_NAME;

function projectPayload(name: string): Project {
  return {
    id: PROJECT_ID,
    name,
    created_at: "2026-08-01T10:00:00Z",
    updated_at: "2026-08-01T10:00:00Z",
  };
}

beforeEach(() => {
  serverName = INITIAL_NAME;
  server.use(
    http.get(PROJECT_URL, () => HttpResponse.json(projectPayload(serverName))),
    // Neighbours of the name row on the same page: the model selector and the
    // MCP panel each own a query, so the page cannot render without them.
    http.get(`${PROJECT_URL}/settings`, () =>
      HttpResponse.json({
        model_name: null,
        extra_body: null,
        resolved_model: "gpt-4o",
        resolved_source: "user",
      }),
    ),
    http.get("/api/models", () =>
      HttpResponse.json({
        items: [{ name: "gpt-4o", display_name: "GPT-4o" }],
        total: 1,
        limit: 50,
        offset: 0,
      }),
    ),
    http.get(`${PROJECT_URL}/mcp-servers`, () =>
      HttpResponse.json({
        items: [],
        total: 0,
        limit: 50,
        offset: 0,
        inherited: [],
      }),
    ),
  );
});

function renderPage() {
  return renderWithProviders(
    routerAt(<ProjectSettingsPage />, {
      path: "/projects/:id/settings",
      entry: `/projects/${PROJECT_ID}/settings`,
    }),
  );
}

const pencil = () =>
  screen.getByRole("button", { name: "Переименовать проект" });
const saveButton = () => screen.getByRole("button", { name: "Сохранить" });
const cancelButton = () => screen.getByRole("button", { name: "Отменить" });
const nameInput = () =>
  screen.getByLabelText("Имя проекта") as HTMLInputElement;

/** Open the editor and replace the draft with `text` (empty string just clears). */
async function editName(
  user: ReturnType<typeof userEvent.setup>,
  text: string,
) {
  await user.click(
    await screen.findByRole("button", { name: /Переименовать/ }),
  );
  const input = nameInput();
  await user.clear(input);
  if (text) await user.type(input, text);
  return input;
}

/**
 * PUT that succeeds and (optionally) moves the server's own copy of the name.
 * `held` keeps the response pending until the test releases it, so "while the
 * write is in flight" is a state the test controls rather than a timing race.
 */
function mockRename(
  options: { advanceServer?: boolean; held?: Promise<void> } = {},
) {
  const { advanceServer = true, held } = options;
  const seen: { body?: unknown } = {};
  server.use(
    http.put(PROJECT_URL, async ({ request }) => {
      seen.body = await request.json();
      if (held) await held;
      const saved = (seen.body as { name: string }).name;
      if (advanceServer) serverName = saved;
      return HttpResponse.json(projectPayload(saved));
    }),
  );
  return seen;
}

describe("ProjectSettingsPage — имя проекта", () => {
  it("shows the name as plain text behind a rename button", async () => {
    renderPage();

    expect(await screen.findByText(INITIAL_NAME)).toBeInTheDocument();
    expect(pencil()).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("opens a focused input seeded with the current name when the pencil is clicked", async () => {
    const user = userEvent.setup();
    renderPage();

    await user.click(
      await screen.findByRole("button", { name: /Переименовать/ }),
    );

    const input = nameInput();
    expect(input).toHaveValue(INITIAL_NAME);
    expect(input).toHaveFocus();
    // Whole value selected, so typing replaces the name instead of appending.
    expect(input.selectionStart).toBe(0);
    expect(input.selectionEnd).toBe(INITIAL_NAME.length);
  });

  it("lets the caption name the input while editing and label nothing while viewing", async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByText(INITIAL_NAME);
    // В просмотре поля не существует, значит подписывать нечего: подпись здесь —
    // обычный текст. `<label for>`, ведущий в пустоту, — это подпись без
    // контрола, тот же дефект доступности, что и контрол без подписи.
    expect(screen.getByText("Имя проекта").tagName).not.toBe("LABEL");
    expect(screen.queryByLabelText("Имя проекта")).not.toBeInTheDocument();

    await user.click(pencil());

    // А в редактировании подпись обязана называть поле — иначе скринридер
    // объявляет его безымянным «редактирование текста».
    expect(screen.getByLabelText("Имя проекта")).toBe(
      screen.getByRole("textbox"),
    );
  });

  it("saves the trimmed name on Enter and returns to the view mode", async () => {
    const seen = mockRename();
    const user = userEvent.setup();
    renderPage();

    await editName(user, `  ${NEW_NAME}  `);
    await user.keyboard("{Enter}");

    await waitFor(() => expect(seen.body).toEqual({ name: NEW_NAME }));
    expect(await screen.findByText(NEW_NAME)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("saves on a click on the check button, even though the input loses focus first", async () => {
    const seen = mockRename();
    const user = userEvent.setup();
    renderPage();

    await editName(user, NEW_NAME);
    await user.click(saveButton());

    await waitFor(() => expect(seen.body).toEqual({ name: NEW_NAME }));
    expect(await screen.findByText(NEW_NAME)).toBeInTheDocument();
  });

  it("discards the draft on Escape without writing anything", async () => {
    const seen = mockRename();
    const user = userEvent.setup();
    renderPage();

    await editName(user, NEW_NAME);
    await user.keyboard("{Escape}");

    expect(await screen.findByText(INITIAL_NAME)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(seen.body).toBeUndefined();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("discards the draft on a click on the cross without writing anything", async () => {
    const seen = mockRename();
    const user = userEvent.setup();
    renderPage();

    await editName(user, NEW_NAME);
    await user.click(cancelButton());

    expect(await screen.findByText(INITIAL_NAME)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(seen.body).toBeUndefined();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("discards the draft when the field loses focus outside a write", async () => {
    const seen = mockRename();
    const user = userEvent.setup();
    renderPage();

    await editName(user, NEW_NAME);
    // Уход фокуса мимо галочки — такой же выход из режима, как Esc и крестик
    // (бриф 5.2: «Esc/blur отменяет», автосохранение по blur отвергнуто).
    await user.click(document.body);

    expect(await screen.findByText(INITIAL_NAME)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(seen.body).toBeUndefined();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("neither writes nor closes on an empty name", async () => {
    const seen = mockRename();
    const user = userEvent.setup();
    renderPage();

    await editName(user, "");
    await user.keyboard("{Enter}");

    expect(saveButton()).toBeDisabled();
    expect(nameInput()).toBeInTheDocument();
    expect(seen.body).toBeUndefined();
  });

  it("closes without a write when the name was not changed", async () => {
    const seen = mockRename();
    const user = userEvent.setup();
    renderPage();

    await editName(user, INITIAL_NAME);
    await user.keyboard("{Enter}");

    expect(await screen.findByText(INITIAL_NAME)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(seen.body).toBeUndefined();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("caps the typed name at 100 characters", async () => {
    const user = userEvent.setup();
    renderPage();

    const input = await editName(user, "я".repeat(120));

    expect(input.value).toHaveLength(100);
  });

  it("keeps the open draft intact when the project is renamed elsewhere, and cancels onto the fresh server name", async () => {
    const user = userEvent.setup();
    const { queryClient } = renderPage();
    const externalName = "Переименован из сайдбара";

    const input = await editName(user, "Черновик ");
    // Somebody renames the project in another tab / from the sidebar modal; the
    // page learns about it the way it does in the app — by refetching.
    serverName = externalName;
    await act(async () => {
      await queryClient.refetchQueries();
    });
    // The user types on. This is what makes the page re-render *while* holding
    // the fresh query data — without it the fresh name never reaches a render
    // during the edit and the check below would pass on any implementation.
    await user.type(input, "пользователя");

    expect(input).toHaveValue("Черновик пользователя");

    await user.type(input, "{Escape}");

    expect(await screen.findByText(externalName)).toBeInTheDocument();
    expect(screen.queryByText(INITIAL_NAME)).not.toBeInTheDocument();
  });

  it("ignores a cancel while the write is in flight and closes only on its result", async () => {
    let letResponseThrough!: () => void;
    mockRename({
      held: new Promise<void>((resolve) => {
        letResponseThrough = resolve;
      }),
    });
    const user = userEvent.setup();
    renderPage();

    await editName(user, NEW_NAME);
    await user.keyboard("{Enter}");

    // In flight: the row is locked and a lost focus must not roll it back.
    await waitFor(() => expect(nameInput()).toBeDisabled());
    expect(cancelButton()).toBeDisabled();
    await user.click(document.body);
    // A real browser also blurs the field by itself the moment it goes
    // disabled; jsdom does not, so that blur is delivered directly.
    fireEvent.blur(nameInput());
    expect(nameInput()).toBeInTheDocument();

    letResponseThrough();

    expect(await screen.findByText(NEW_NAME)).toBeInTheDocument();
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("confirms a successful save with a status message that clears on its own", async () => {
    mockRename();
    const user = userEvent.setup();
    renderPage();

    await editName(user, NEW_NAME);
    await user.keyboard("{Enter}");

    const status = await screen.findByRole("status");
    expect(status).toHaveTextContent("Сохранено");

    // Real clock on purpose: a faked one either stalls the MSW round trip
    // (frozen) or drifts along with real time (auto-advancing), and the
    // confirmation would then clear for reasons the test does not control.
    await waitForElementToBeRemoved(status, { timeout: 4000 });
  });

  it("drops the confirmation of the previous save as soon as the editor is reopened", async () => {
    mockRename();
    const user = userEvent.setup();
    renderPage();

    await editName(user, NEW_NAME);
    await user.keyboard("{Enter}");
    await screen.findByRole("status");

    // The network round trip is behind us, so from here the clock is frozen and
    // the confirmation's own 1.6s deadline can no longer arrive. Without this
    // the case would also go green whenever the reopen happened to outlast the
    // deadline — the right assertion for the wrong reason, a silent false-green
    // that no amount of re-running exposes. The reopen is driven by fireEvent
    // rather than userEvent because the latter waits on timers that nothing is
    // moving anymore.
    vi.useFakeTimers();
    try {
      fireEvent.click(pencil());
      fireEvent.keyDown(nameInput(), { key: "Escape" });

      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  // Not covered here: "the previous save's timer must not swallow the fresh
  // confirmation of the next save". Two mechanisms cover that race — the
  // clearSavedTimer() in onSuccess and the one in startEdit — and startEdit is
  // the only way into the editor, so by the time onSuccess runs the timer has
  // already been dropped. Removing either one alone changes nothing observable
  // anywhere (jsdom or browser), which is why the mutation of the onSuccess one
  // shows 0 red: the case has no oracle until both are gone. Manual {T3.7}
  // covers what is left of it, not a decoration test here.
  //
  // Not covered either: preventDefault on the cross's mousedown. Its purpose —
  // surviving a re-render between mousedown and mouseup and racing the
  // programmatic focus return — is not something jsdom plays out, and the
  // outcome without it is identical (blur cancels the same way).

  it("shows the just-saved name beside the confirmation even before the refetch catches up", async () => {
    // The write succeeds but the server keeps answering with the old name, so a
    // page that trusted the query alone would paint "old name + Сохранено".
    mockRename({ advanceServer: false });
    const user = userEvent.setup();
    renderPage();

    await editName(user, NEW_NAME);
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("status")).toHaveTextContent("Сохранено");
    expect(screen.getByText(NEW_NAME)).toBeInTheDocument();
    expect(screen.queryByText(INITIAL_NAME)).not.toBeInTheDocument();
  });

  it("hands the row back to the query as soon as it carries the saved name", async () => {
    // The other half of the case above: the local stand-in must last exactly
    // until the query catches up, not forever — otherwise the row freezes on
    // the name we wrote and never shows anybody else's rename again.
    mockRename();
    const user = userEvent.setup();
    const { queryClient } = renderPage();
    const externalName = "Переименован из сайдбара";

    await editName(user, NEW_NAME);
    await user.keyboard("{Enter}");
    await screen.findByText(NEW_NAME);
    // The query catches up with our own write (in the app the invalidation
    // after the PUT does this) — the stand-in has no reason to live on.
    await act(async () => {
      await queryClient.refetchQueries();
    });

    // Now somebody renames the project elsewhere; the view mode reads the query
    // directly again, so the fresh name has to land on the row.
    serverName = externalName;
    await act(async () => {
      await queryClient.refetchQueries();
    });

    expect(await screen.findByText(externalName)).toBeInTheDocument();
    expect(screen.queryByText(NEW_NAME)).not.toBeInTheDocument();
  });

  it("keeps the editor and the typed text when the write fails, without confirming", async () => {
    const seen: { body?: unknown } = {};
    server.use(
      http.put(PROJECT_URL, async ({ request }) => {
        seen.body = await request.json();
        return HttpResponse.json({ detail: "boom" }, { status: 500 });
      }),
    );
    const user = userEvent.setup();
    renderPage();

    await editName(user, NEW_NAME);
    await user.keyboard("{Enter}");

    // The write really left and really failed — otherwise "the editor is still
    // open with the typed text" would also hold in a world where Enter sends
    // nothing at all.
    await waitFor(() => expect(seen.body).toEqual({ name: NEW_NAME }));
    await waitFor(() => expect(nameInput()).toBeEnabled());
    expect(nameInput()).toHaveValue(NEW_NAME);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("returns focus to the pencil after a cancel", async () => {
    const user = userEvent.setup();
    renderPage();

    await editName(user, NEW_NAME);
    await user.keyboard("{Escape}");

    await waitFor(() => expect(pencil()).toHaveFocus());
  });

  it("returns focus to the pencil after a successful save", async () => {
    mockRename();
    const user = userEvent.setup();
    renderPage();

    await editName(user, NEW_NAME);
    await user.keyboard("{Enter}");

    await screen.findByText(NEW_NAME);
    await waitFor(() => expect(pencil()).toHaveFocus());
  });
});
