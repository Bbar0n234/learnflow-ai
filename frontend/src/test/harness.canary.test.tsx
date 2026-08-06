import { useQuery } from "@tanstack/react-query";
import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { server } from "./msw/server";
import { renderWithProviders } from "./test-utils";

// A self-contained component (component + hook + network) that exercises the
// whole integration harness: renderWithProviders (fresh QueryClient) + a
// MSW-mocked endpoint. The center of gravity for frontend tests (Testing Trophy).
function Greeting() {
  const { data, isLoading } = useQuery({
    queryKey: ["greeting"],
    queryFn: async (): Promise<{ message: string }> => {
      const response = await fetch("/api/greeting");
      return (await response.json()) as { message: string };
    },
  });

  if (isLoading) {
    return <p>Loading…</p>;
  }
  return <p>{data?.message}</p>;
}

describe("frontend test harness", () => {
  it("renders data fetched through a MSW-mocked endpoint", async () => {
    server.use(
      http.get("/api/greeting", () =>
        HttpResponse.json({ message: "hello from msw" }),
      ),
    );

    renderWithProviders(<Greeting />);

    expect(await screen.findByText("hello from msw")).toBeInTheDocument();
  });
});
