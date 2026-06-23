import "@/test/pointer-event-polyfill";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
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

    expect(await screen.findByText("Current: GPT-4o")).toBeInTheDocument();
    // The trigger reflects the selected model's display name.
    expect(screen.getByRole("combobox")).toHaveTextContent("GPT-4o");
  });

  it("labels the default choice 'Default' for user scope when no model is set", async () => {
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
    );

    renderWithProviders(<ModelSelector scope="user" />);

    expect(await screen.findByText("Current: GPT-4o")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveTextContent("Default");
  });

  it("labels the default choice 'Inherit' for project scope when no model is set", async () => {
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
      await screen.findByText("Current: Claude Sonnet"),
    ).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toHaveTextContent("Inherit");
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
      await screen.findByText("Current: mystery-model"),
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
    await screen.findByText("Current: GPT-4o");

    await user.click(screen.getByRole("combobox"));
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
    await screen.findByText("Current: GPT-4o");

    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: "Default" }));

    await waitFor(() => expect(putBody).toEqual({ model_name: null }));
  });

  it("disables the trigger while the settings write is in flight", async () => {
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
        await delay(150);
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
    await screen.findByText("Current: GPT-4o");

    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: "GPT-4o" }));

    await waitFor(() => expect(screen.getByRole("combobox")).toBeDisabled());
  });
});
