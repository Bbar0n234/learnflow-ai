import { AxiosError, AxiosHeaders, type AxiosResponse } from "axios";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "@/test/test-utils";
import { SECURITY_VIOLATION_MESSAGE } from "@/shared/lib/security-error";
import type { MCPServer } from "@/shared/api/mcp-servers";

import { MCPServerForm } from "./MCPServerForm";

// The MCP server add/edit form. Native text inputs (name, url, api key) drive a
// MCPServerCreate body on submit; the transport Select defaults to "http". The
// error prop is rendered through the security-violation / generic-api-error
// branches. Tested as a unit with props (onSubmit/onCancel spies, error object).

/** Build an AxiosError carrying a problem+json response body. */
function axiosError(status: number, data: unknown): AxiosError {
  const response = {
    status,
    data,
    statusText: "",
    headers: {},
    config: { headers: new AxiosHeaders() },
  } as AxiosResponse;
  return new AxiosError(
    "request failed",
    "ERR_BAD_REQUEST",
    response.config,
    {},
    response,
  );
}

const EXISTING_SERVER: MCPServer = {
  id: "srv-1",
  name: "existing",
  transport: "http",
  url: "https://old.example.com/v1",
  has_api_key: true,
  api_key_hint: "sk-…abcd",
  allowed_tools: [],
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("MCPServerForm", () => {
  it("submits the name, default transport and url for a new server", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <MCPServerForm
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        isPending={false}
        error={null}
      />,
    );

    await user.type(screen.getByLabelText("Name"), "my-mcp");
    await user.type(screen.getByLabelText("URL"), "https://mcp.example.com/v1");
    await user.click(screen.getByRole("button", { name: "Add Server" }));

    expect(onSubmit).toHaveBeenCalledWith({
      name: "my-mcp",
      transport: "http",
      url: "https://mcp.example.com/v1",
    });
  });

  it("includes the api key when one is typed", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <MCPServerForm
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        isPending={false}
        error={null}
      />,
    );

    await user.type(screen.getByLabelText("Name"), "keyed");
    await user.type(screen.getByLabelText("URL"), "https://mcp.example.com/v1");
    await user.type(screen.getByLabelText(/API Key/), "secret-token");
    await user.click(screen.getByRole("button", { name: "Add Server" }));

    expect(onSubmit).toHaveBeenCalledWith({
      name: "keyed",
      transport: "http",
      url: "https://mcp.example.com/v1",
      api_key: "secret-token",
    });
  });

  it("prefills existing values and omits api_key when the key is left blank in edit mode", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    renderWithProviders(
      <MCPServerForm
        onSubmit={onSubmit}
        onCancel={vi.fn()}
        isPending={false}
        error={null}
        initialData={EXISTING_SERVER}
      />,
    );

    expect(screen.getByDisplayValue("existing")).toBeInTheDocument();
    expect(
      screen.getByDisplayValue("https://old.example.com/v1"),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Save" }));

    expect(onSubmit).toHaveBeenCalledWith({
      name: "existing",
      transport: "http",
      url: "https://old.example.com/v1",
    });
  });

  it("calls onCancel when the cancel button is pressed", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    renderWithProviders(
      <MCPServerForm
        onSubmit={vi.fn()}
        onCancel={onCancel}
        isPending={false}
        error={null}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("disables the submit button and shows progress text while pending", () => {
    renderWithProviders(
      <MCPServerForm
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isPending={true}
        error={null}
      />,
    );

    expect(screen.getByRole("button", { name: "Adding..." })).toBeDisabled();
  });

  it("renders the security-policy message for a 422 violation error", () => {
    renderWithProviders(
      <MCPServerForm
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isPending={false}
        error={axiosError(422, {
          type: "urn:learnflow:security-policy-violation",
        })}
      />,
    );

    expect(screen.getByText(SECURITY_VIOLATION_MESSAGE)).toBeInTheDocument();
  });

  it("renders the parsed problem+json detail for a generic error", () => {
    renderWithProviders(
      <MCPServerForm
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        isPending={false}
        error={axiosError(409, { detail: "Server name already exists" })}
      />,
    );

    expect(screen.getByText("Server name already exists")).toBeInTheDocument();
  });
});
