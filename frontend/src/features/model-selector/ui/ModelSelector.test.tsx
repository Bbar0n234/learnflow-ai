import "@/test/pointer-event-polyfill";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { ModelSelector } from "./ModelSelector";

// Integration: the model picker resolves a display name from two queries — the
// available-models list (/models) and the scope's settings (/users/me/settings
// etc.) — renders the selected and resolved model names, and writes a choice back
// through PUT settings. The Base UI Select popup is driven for real (open the
// listbox, click an option) under jsdom via the pointer-event polyfill. Network
// is MSW.

const MODELS = {
  items: [
    { name: "gpt-4o", display_name: "GPT-4o" },
    { name: "claude-sonnet", display_name: "Claude Sonnet" },
  ],
  total: 2,
  limit: 50,
  offset: 0,
};

function mockModels() {
  return http.get("/api/models", () => HttpResponse.json(MODELS));
}

const USER_SETTINGS = "/api/users/me/settings";

/**
 * The trigger is always reached by its accessible name rather than by a bare
 * role: "Модель" is what a screen reader announces the control as, and the
 * caption is tied to the (non-native) trigger by `aria-labelledby` alone — lose
 * that tie and the picker goes back to being an anonymous combobox, so every
 * case here has to notice.
 */
const trigger = () => screen.getByRole("combobox", { name: "Модель" });

describe("ModelSelector", () => {
  it("shows the selected model's display name and the resolved model for an explicit choice", async () => {
    server.use(
      mockModels(),
      http.get(USER_SETTINGS, () =>
        HttpResponse.json({
          model_name: "gpt-4o",
          extra_body: null,
          resolved_model: "gpt-4o",
          resolved_source: "user",
        }),
      ),
    );

    renderWithProviders(<ModelSelector scope="user" />);

    expect(
      await screen.findByText("Активная модель: GPT-4o"),
    ).toBeInTheDocument();
    // The trigger reflects the selected model's display name.
    expect(trigger()).toHaveTextContent("GPT-4o");
  });

  // The collapsed trigger speaks the same language as the expanded listbox
  // (design-brief 5.1): "По умолчанию" for the user's own settings, "Наследовать"
  // wherever the value can fall through to an outer scope.
  it.each([
    {
      scope: "user" as const,
      settingsUrl: USER_SETTINGS,
      element: <ModelSelector scope="user" />,
      resolvedModel: "gpt-4o",
      resolvedLine: "Активная модель: GPT-4o",
      label: "По умолчанию",
    },
    {
      scope: "project" as const,
      settingsUrl: "/api/projects/p1/settings",
      element: <ModelSelector scope="project" projectId="p1" />,
      resolvedModel: "claude-sonnet",
      resolvedLine: "Активная модель: Claude Sonnet",
      label: "Наследовать",
    },
    {
      scope: "thread" as const,
      settingsUrl: "/api/projects/p1/chats/t1/settings",
      element: <ModelSelector scope="thread" projectId="p1" threadId="t1" />,
      resolvedModel: "claude-sonnet",
      resolvedLine: "Активная модель: Claude Sonnet",
      label: "Наследовать",
    },
  ])(
    "labels the default choice '$label' on the collapsed trigger in $scope scope",
    async ({ settingsUrl, element, resolvedModel, resolvedLine, label }) => {
      server.use(
        mockModels(),
        http.get(settingsUrl, () =>
          HttpResponse.json({
            model_name: null,
            extra_body: null,
            resolved_model: resolvedModel,
            resolved_source: "system",
          }),
        ),
      );

      renderWithProviders(element);
      // Wait for the settings-dependent line so the trigger is asserted on
      // loaded data, not on the pre-fetch default.
      await screen.findByText(resolvedLine);

      expect(trigger()).toHaveTextContent(label);
    },
  );

  it("names the default option in the open listbox exactly as the collapsed trigger does", async () => {
    server.use(
      mockModels(),
      http.get("/api/projects/p1/settings", () =>
        HttpResponse.json({
          model_name: null,
          extra_body: null,
          resolved_model: "claude-sonnet",
          resolved_source: "user",
        }),
      ),
    );
    const user = userEvent.setup();

    renderWithProviders(<ModelSelector scope="project" projectId="p1" />);
    await screen.findByText("Активная модель: Claude Sonnet");
    // Captured before opening: the trigger keeps a decorative chevron glyph, so
    // the comparison is "the trigger carries the option's label", not equality.
    const triggerLabel = trigger().textContent ?? "";

    await user.click(trigger());

    const defaultOption = await screen.findByRole("option", {
      name: "Наследовать",
    });
    expect(defaultOption).toBeInTheDocument();
    expect(triggerLabel).toContain("Наследовать");
  });

  it("shows the resolved model line in project scope instead of a static override hint", async () => {
    server.use(
      mockModels(),
      http.get("/api/projects/p1/settings", () =>
        HttpResponse.json({
          model_name: null,
          extra_body: null,
          resolved_model: "claude-sonnet",
          resolved_source: "user",
        }),
      ),
    );

    renderWithProviders(<ModelSelector scope="project" projectId="p1" />);

    expect(
      await screen.findByText("Активная модель: Claude Sonnet"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/Переопределяет модель пользователя/),
    ).not.toBeInTheDocument();
  });

  it("falls back to the raw model name when the models list fails to load", async () => {
    server.use(
      http.get("/api/models", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
      http.get(USER_SETTINGS, () =>
        HttpResponse.json({
          model_name: "mystery-model",
          extra_body: null,
          resolved_model: "mystery-model",
          resolved_source: "user",
        }),
      ),
    );

    renderWithProviders(<ModelSelector scope="user" />);

    expect(
      await screen.findByText("Активная модель: mystery-model"),
    ).toBeInTheDocument();
  });

  it("PUTs the chosen model name when an explicit model is picked from the open listbox", async () => {
    let putBody: unknown;
    server.use(
      mockModels(),
      http.get(USER_SETTINGS, () =>
        HttpResponse.json({
          model_name: null,
          extra_body: null,
          resolved_model: "gpt-4o",
          resolved_source: "system",
        }),
      ),
      http.put(USER_SETTINGS, async ({ request }) => {
        putBody = await request.json();
        return HttpResponse.json({
          model_name: "claude-sonnet",
          extra_body: null,
          resolved_model: "claude-sonnet",
          resolved_source: "user",
        });
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<ModelSelector scope="user" />);
    await screen.findByText("Активная модель: GPT-4o");

    await user.click(trigger());
    await user.click(
      await screen.findByRole("option", { name: "Claude Sonnet" }),
    );

    await waitFor(() =>
      expect(putBody).toEqual({ model_name: "claude-sonnet" }),
    );
  });

  it("PUTs model_name null when 'Default' is picked while an explicit model is set", async () => {
    let putBody: unknown;
    server.use(
      mockModels(),
      http.get(USER_SETTINGS, () =>
        HttpResponse.json({
          model_name: "gpt-4o",
          extra_body: null,
          resolved_model: "gpt-4o",
          resolved_source: "user",
        }),
      ),
      http.put(USER_SETTINGS, async ({ request }) => {
        putBody = await request.json();
        return HttpResponse.json({
          model_name: null,
          extra_body: null,
          resolved_model: "gpt-4o",
          resolved_source: "system",
        });
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<ModelSelector scope="user" />);
    await screen.findByText("Активная модель: GPT-4o");

    await user.click(trigger());
    await user.click(
      await screen.findByRole("option", { name: "По умолчанию" }),
    );

    await waitFor(() => expect(putBody).toEqual({ model_name: null }));
  });

  it("disables the trigger while the settings write is in flight", async () => {
    // "In flight" is held open by the test rather than by a delay on the real
    // clock: a slow machine could otherwise finish the write before the
    // assertion looks, and the case would fail for a reason that is not the
    // component's.
    let letResponseThrough!: () => void;
    const held = new Promise<void>((resolve) => {
      letResponseThrough = resolve;
    });
    server.use(
      mockModels(),
      http.get(USER_SETTINGS, () =>
        HttpResponse.json({
          model_name: null,
          extra_body: null,
          resolved_model: "gpt-4o",
          resolved_source: "system",
        }),
      ),
      http.put(USER_SETTINGS, async () => {
        await held;
        return HttpResponse.json({
          model_name: "gpt-4o",
          extra_body: null,
          resolved_model: "gpt-4o",
          resolved_source: "user",
        });
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<ModelSelector scope="user" />);
    await screen.findByText("Активная модель: GPT-4o");

    await user.click(trigger());
    await user.click(await screen.findByRole("option", { name: "GPT-4o" }));

    await waitFor(() => expect(trigger()).toBeDisabled());

    letResponseThrough();

    // ...and the lock is the write's, not a permanent one.
    await waitFor(() => expect(trigger()).toBeEnabled());
  });
});
