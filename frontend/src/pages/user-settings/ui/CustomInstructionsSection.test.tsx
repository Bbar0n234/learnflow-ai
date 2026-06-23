import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { SECURITY_VIOLATION_MESSAGE } from "@/shared/lib/security-error";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { CustomInstructionsSection } from "./CustomInstructionsSection";

// Integration: the custom-instructions editor. Loads the saved text from
// /users/me/instructions, enables Save only when the text is dirty, and persists
// edits via PUT (resetting the dirty flag on success). The 422 security-policy
// branch surfaces the violation message. Network is MSW.
//
// The <label> is not associated with the <textarea> (no htmlFor/id — a11y gap,
// see run-log), so the textarea is reached by role.

const URL = "/api/users/me/instructions";

describe("CustomInstructionsSection", () => {
  it("loads saved instructions and keeps Save disabled until edited", async () => {
    server.use(http.get(URL, () => HttpResponse.json({ content: "initial" })));

    renderWithProviders(<CustomInstructionsSection />);

    expect(await screen.findByDisplayValue("initial")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("saves edited instructions and re-disables Save on success", async () => {
    let putBody: { content: string } | null = null;
    server.use(
      http.get(URL, () => HttpResponse.json({ content: "initial" })),
      http.put(URL, async ({ request }) => {
        putBody = (await request.json()) as { content: string };
        return HttpResponse.json({ content: putBody.content });
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<CustomInstructionsSection />);
    const textarea = await screen.findByDisplayValue("initial");

    await user.type(textarea, " more");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(putBody).toEqual({ content: "initial more" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save" })).toBeDisabled(),
    );
  });

  it("shows the security-policy message when the save is rejected as a violation", async () => {
    server.use(
      http.get(URL, () => HttpResponse.json({ content: "initial" })),
      http.put(URL, () =>
        HttpResponse.json(
          { type: "urn:learnflow:security-policy-violation" },
          { status: 422 },
        ),
      ),
    );
    const user = userEvent.setup();

    renderWithProviders(<CustomInstructionsSection />);
    const textarea = await screen.findByDisplayValue("initial");

    await user.type(textarea, " bad");
    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(
      await screen.findByText(SECURITY_VIOLATION_MESSAGE),
    ).toBeInTheDocument();
  });
});
