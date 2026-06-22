import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";

import { ModelSelector } from "./ModelSelector";

// Integration: the model picker resolves a display name from two queries — the
// available-models list (/models) and the scope's settings (/users/me/settings
// etc.) — and renders the selected and resolved model names. Network is MSW.

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

describe("ModelSelector", () => {
  it("shows the selected model's display name and the resolved model for an explicit choice", async () => {
    server.use(
      mockModels(),
      http.get("/api/users/me/settings", () =>
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
    expect(screen.getAllByText("GPT-4o").length).toBeGreaterThan(0);
  });

  it("labels the default choice 'Default' for user scope when no model is set", async () => {
    server.use(
      mockModels(),
      http.get("/api/users/me/settings", () =>
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
    expect(screen.getAllByText("Default").length).toBeGreaterThan(0);
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
    expect(screen.getAllByText("Inherit").length).toBeGreaterThan(0);
  });

  it("falls back to the raw model name when the models list fails to load", async () => {
    server.use(
      http.get("/api/models", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
      http.get("/api/users/me/settings", () =>
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
});
