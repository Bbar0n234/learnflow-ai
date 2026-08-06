import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import "@/test/pointer-event-polyfill";
import { server } from "@/test/msw/server";
import { renderWithProviders } from "@/test/test-utils";
import type { InheritedMCPServer, MCPServer } from "@/shared/api/mcp-servers";

import { MCPServersSection } from "./MCPServersSection";

// Integration: the per-scope MCP servers panel. Lists own + inherited servers
// from /users/me/mcp-servers (user scope here drops inherited), drives test /
// delete / toggle mutations, and surfaces loading and empty states. Network MSW.

const USER_URL = "/api/users/me/mcp-servers";

function ownServer(over: Partial<MCPServer> = {}): MCPServer {
  return {
    id: "srv-1",
    name: "my-server",
    transport: "http",
    url: "https://mcp.example.com/v1",
    has_api_key: false,
    api_key_hint: null,
    allowed_tools: [],
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...over,
  };
}

function listResponse(
  items: MCPServer[],
  inherited: InheritedMCPServer[] = [],
) {
  return HttpResponse.json({
    items,
    total: items.length,
    limit: 50,
    offset: 0,
    inherited,
  });
}

describe("MCPServersSection", () => {
  it("shows a loading hint while the list is in flight", () => {
    server.use(http.get(USER_URL, () => listResponse([])));

    renderWithProviders(<MCPServersSection scope="user" />);

    expect(screen.getByText("Загрузка…")).toBeInTheDocument();
  });

  it("shows an empty-state message when there are no servers", async () => {
    server.use(http.get(USER_URL, () => listResponse([])));

    renderWithProviders(<MCPServersSection scope="user" />);

    expect(
      await screen.findByText("MCP-серверы не настроены."),
    ).toBeInTheDocument();
  });

  it("renders a configured server with its transport and url", async () => {
    server.use(http.get(USER_URL, () => listResponse([ownServer()])));

    renderWithProviders(<MCPServersSection scope="user" />);

    expect(await screen.findByText("my-server")).toBeInTheDocument();
    expect(
      screen.getByText("http · https://mcp.example.com/v1"),
    ).toBeInTheDocument();
  });

  it("reports a successful connection test with the tool count", async () => {
    server.use(
      http.get(USER_URL, () => listResponse([ownServer()])),
      http.post(`${USER_URL}/srv-1/test`, () =>
        HttpResponse.json({ success: true, tools: ["a", "b", "c"] }),
      ),
    );
    const user = userEvent.setup();

    renderWithProviders(<MCPServersSection scope="user" />);
    await screen.findByText("my-server");

    await user.click(
      screen.getByRole("button", { name: "Проверить соединение" }),
    );

    expect(await screen.findByText("OK (3 инструментов)")).toBeInTheDocument();
  });

  it("surfaces a failed connection test reason", async () => {
    server.use(
      http.get(USER_URL, () => listResponse([ownServer()])),
      http.post(`${USER_URL}/srv-1/test`, () =>
        HttpResponse.json({
          success: false,
          tools: [],
          error: "handshake timeout",
        }),
      ),
    );
    const user = userEvent.setup();

    renderWithProviders(<MCPServersSection scope="user" />);
    await screen.findByText("my-server");

    await user.click(
      screen.getByRole("button", { name: "Проверить соединение" }),
    );

    expect(
      await screen.findByText("Ошибка: handshake timeout"),
    ).toBeInTheDocument();
  });

  it("removes a server after delete and refetch", async () => {
    let deleted = false;
    server.use(
      http.get(USER_URL, () => listResponse(deleted ? [] : [ownServer()])),
      http.delete(`${USER_URL}/srv-1`, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<MCPServersSection scope="user" />);
    await screen.findByText("my-server");

    await user.click(screen.getByRole("button", { name: "Удалить" }));

    await waitFor(() =>
      expect(screen.getByText("MCP-серверы не настроены.")).toBeInTheDocument(),
    );
  });

  it("opens the add form and creates a server", async () => {
    let created = false;
    server.use(
      http.get(USER_URL, () =>
        listResponse(created ? [ownServer({ name: "fresh" })] : []),
      ),
      http.post(USER_URL, () => {
        created = true;
        return HttpResponse.json(ownServer({ name: "fresh" }), {
          status: 201,
        });
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<MCPServersSection scope="user" />);
    await screen.findByText("MCP-серверы не настроены.");

    await user.click(screen.getByRole("button", { name: /Добавить/ }));
    await user.type(screen.getByPlaceholderText("my-server"), "fresh");
    await user.type(
      screen.getByPlaceholderText("https://mcp.example.com/v1"),
      "https://fresh.example.com/v1",
    );
    await user.click(screen.getByRole("button", { name: "Add Server" }));

    expect(await screen.findByText("fresh")).toBeInTheDocument();
  });

  it("disables Add once five servers exist", async () => {
    const five = Array.from({ length: 5 }, (_, i) =>
      ownServer({ id: `srv-${i}`, name: `server-${i}` }),
    );
    server.use(http.get(USER_URL, () => listResponse(five)));

    renderWithProviders(<MCPServersSection scope="user" />);
    await screen.findByText("server-0");

    expect(screen.getByRole("button", { name: /Добавить/ })).toBeDisabled();
  });

  it("renders inherited servers and toggles their enabled state", async () => {
    const PROJECT_URL = "/api/projects/p1/mcp-servers";
    let disabled = false;
    const inherited = (): InheritedMCPServer => ({
      id: "inh-1",
      name: "inherited-server",
      transport: "sse",
      url: "https://parent.example.com/v1",
      has_api_key: false,
      api_key_hint: null,
      is_active: true,
      is_disabled: disabled,
    });
    let toggledDisabled: boolean | null = null;
    server.use(
      http.get(PROJECT_URL, () => listResponse([], [inherited()])),
      http.put(`${PROJECT_URL}/inherited/inh-1/toggle`, async ({ request }) => {
        const body = (await request.json()) as { disabled: boolean };
        toggledDisabled = body.disabled;
        disabled = body.disabled;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const user = userEvent.setup();

    renderWithProviders(<MCPServersSection scope="project" projectId="p1" />);
    await screen.findByText("inherited-server");

    // Enabled inherited server reads as a checked switch.
    expect(screen.getByRole("switch")).toBeChecked();

    await user.click(screen.getByRole("switch"));

    // Payload disables it, and after the refetch the switch reflects the off state.
    await waitFor(() => expect(toggledDisabled).toBe(true));
    await waitFor(() => expect(screen.getByRole("switch")).not.toBeChecked());
  });
});
