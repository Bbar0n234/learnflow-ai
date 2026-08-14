import "@/test/match-media-polyfill";

import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { MemoryRouter, useLocation, useNavigationType } from "react-router";
import {
  afterEach,
  beforeAll,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from "vitest";

import { setAccessToken } from "@/shared/api/client";
import { authProvidersHandlers } from "@/test/msw/auth-providers";
import { server } from "@/test/msw/server";
import { fakeJwt } from "@/test/sse-stream";
import { renderWithProviders } from "@/test/test-utils";

// The build-time SIEM flag is mocked at the module boundary; its parsing rules
// are pinned in `shared/config/feature-flags.test.ts`. The mock is a getter so
// a single test file can render both bundles.
const flags = vi.hoisted(() => ({ siemEnabled: true }));

vi.mock("@/shared/config/feature-flags", () => ({
  get SIEM_ENABLED() {
    return flags.siemEnabled;
  },
  SHOW_GROUP_B_STUBS: false,
}));

import { AppRoutes } from "./router";

// Integration (feat-002, T2.6): the chat routes as the user reaches them —
// through the real route table, not by mounting a page component directly. The
// composer lives at its own URL `/projects/:id/chats/new` (design-brief §
// Создание чата и первое сообщение) and must land on the draft branch: without
// that route the `chats/:cid` pattern would swallow it with `cid = "new"` and
// try to load a chat that does not exist. Network is MSW with
// `onUnhandledRequest: "error"`, so such a request would fail the run.

const PROJECT_ID = "p1";
const CHAT_ID = "c1";

function appHandlers() {
  return [
    http.get("/api/projects", () =>
      HttpResponse.json({ items: [], total: 0, limit: 200, offset: 0 }),
    ),
    http.get("/api/auth/me", () =>
      HttpResponse.json({ id: "u1", name: "tester", is_admin: false }),
    ),
    http.get("/api/chats/recent", () =>
      HttpResponse.json({ items: [], total: 0, limit: 10, offset: 0 }),
    ),
    http.get(`/api/projects/${PROJECT_ID}`, () =>
      HttpResponse.json({
        id: PROJECT_ID,
        name: "Матан",
        created_at: "2026-07-01T10:00:00Z",
        updated_at: "2026-07-01T10:00:00Z",
      }),
    ),
  ];
}

function renderAppAt(entry: string) {
  return renderWithProviders(
    <MemoryRouter initialEntries={[entry]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

// jsdom has no layout — the message feed auto-scrolls a ref into view.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

beforeEach(() => {
  flags.siemEnabled = true;
});

afterEach(() => {
  localStorage.clear();
});

describe("AppRoutes — chat screens", () => {
  it("opens the composer on the new-chat URL, without touching a chat", async () => {
    setAccessToken(fakeJwt());
    server.use(...appHandlers());

    renderAppAt(`/projects/${PROJECT_ID}/chats/new`);

    expect(
      await screen.findByText(
        "Напишите первое сообщение — чат появится вместе с ним, а название придумает модель.",
      ),
    ).toBeInTheDocument();
  });

  it("opens the existing chat with its history on a chat URL", async () => {
    setAccessToken(fakeJwt());
    server.use(
      ...appHandlers(),
      http.get(`/api/projects/${PROJECT_ID}/chats/${CHAT_ID}`, () =>
        HttpResponse.json({
          thread_id: CHAT_ID,
          title: "Производные",
          security_blocked: false,
          messages: [
            {
              id: "m-1",
              role: "user",
              content: "Старое сообщение",
              created_at: "2026-07-01T10:00:00Z",
              artifacts: [],
            },
          ],
        }),
      ),
    );

    renderAppAt(`/projects/${PROJECT_ID}/chats/${CHAT_ID}`);

    expect(await screen.findByText("Старое сообщение")).toBeInTheDocument();
  });
});

// Integration on the route half of the SIEM kill-switch (chore-001): in a
// SIEM-off bundle `/security` must not exist as a route at all, and in a
// SIEM-on bundle it must still be there, behind its RBAC guard.
//
// Since feat-013 (design-brief блок 7) the app layout carries a catch-all
// `path="*"`, so "the route is gone" no longer means "nothing renders": an
// unmatched `/security` now falls through to the branded 404 inside the layout
// — the user keeps the sidebar instead of staring at a blank document. The
// observable difference from a working route is therefore the 404 screen in
// place of the Security page, not an empty tree. The SIEM-on case is held at
// the guard's loading state (the profile request is delayed) — that is enough
// to prove the route matched, and it keeps the lazy Security page and its own
// network out of a test about routing.

const GUARD_LOADING = "Загрузка…";
const WELCOME_HEADING = "Добро пожаловать";
const NOT_FOUND_HEADING = "Страница не найдена";

function emptyList() {
  return HttpResponse.json({ items: [], total: 0, limit: 10, offset: 0 });
}

function stubAppNetwork() {
  server.use(
    // Delayed on purpose: the guard stays in its loading state, so the test
    // observes "the route rendered" without mounting the Security page.
    http.get("/api/auth/me", async () => {
      await delay(200);
      return HttpResponse.json({ id: "u1", name: "tester", is_admin: true });
    }),
    http.get("/api/projects", () => emptyList()),
    http.get("/api/chats/recent", () => emptyList()),
  );
}

function renderAt(entry: string) {
  stubAppNetwork();
  // The RBAC guard only queries the profile when a token is present; without
  // one it redirects immediately and the loading state never appears.
  setAccessToken("header.payload.signature");
  return renderWithProviders(
    <MemoryRouter initialEntries={[entry]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe("AppRoutes — the /security route under the SIEM flag", () => {
  it("routes /security to the guarded Security page in a SIEM-on build", async () => {
    renderAt("/security");

    expect(await screen.findByText(GUARD_LOADING)).toBeInTheDocument();
  });

  it("answers /security with the 404 screen in a SIEM-off build", async () => {
    flags.siemEnabled = false;

    renderAt("/security");

    // No route matches the URL, so the catch-all answers: the branded 404
    // inside the app layout, neither the Security page nor its guard.
    expect(
      await screen.findByRole("heading", { name: NOT_FOUND_HEADING }),
    ).toBeInTheDocument();
    expect(screen.queryByText(GUARD_LOADING)).not.toBeInTheDocument();
  });

  it("keeps every other route working in a SIEM-off build", async () => {
    // The kill-switch removes one route, not the router: the rest of the app
    // must be indistinguishable from a SIEM-on build.
    flags.siemEnabled = false;

    renderAt("/");

    expect(
      await screen.findByRole("heading", { name: WELCOME_HEADING }),
    ).toBeInTheDocument();
  });
});

// Integration on the catch-all (feat-013, design-brief блок 7): a URL that
// matches nothing must not be a dead end. The 404 lives *inside* the app
// layout, so the user keeps the sidebar and one click back to the app.

describe("AppRoutes — the catch-all 404", () => {
  it("answers an unknown URL with the 404 screen", async () => {
    setAccessToken(fakeJwt());
    server.use(...appHandlers());

    renderAppAt("/чепуха");

    expect(
      await screen.findByRole("heading", { name: NOT_FOUND_HEADING }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Такой страницы нет или она переехала. Вернитесь на главную и продолжите оттуда.",
      ),
    ).toBeInTheDocument();
  });

  it("keeps the sidebar on screen, so the user stays inside the app", async () => {
    setAccessToken(fakeJwt());
    server.use(...appHandlers());

    renderAppAt("/projects/p1/несуществующая-вкладка");

    await screen.findByRole("heading", { name: NOT_FOUND_HEADING });
    // The sidebar is the chrome the layout provides: its actions are still
    // there, i.e. the 404 replaced the working area only.
    expect(
      screen.getByRole("button", { name: "Новый проект" }),
    ).toBeInTheDocument();
  });

  it("takes the user home from the 404, without a page reload", async () => {
    setAccessToken(fakeJwt());
    server.use(...appHandlers());
    const user = userEvent.setup();

    renderAppAt("/чепуха");
    await screen.findByRole("heading", { name: NOT_FOUND_HEADING });

    // CTA действия — навигационная ссылка, а не элемент с подменённой ролью:
    // скринридер находит её среди ссылок, а `href` даёт штатные средства
    // браузера (Enter, «открыть в новой вкладке»). Роль и адрес утверждаются
    // до клика — переход одинаково сработал бы и у `<button role="button">`,
    // поэтому сам по себе он семантику не сторожит.
    const home = screen.getByRole("link", { name: "На главную" });
    expect(home).toHaveAttribute("href", "/");

    await user.click(home);

    // A client-side transition: the welcome screen appears in the same tree.
    expect(
      await screen.findByRole("heading", { name: WELCOME_HEADING }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: NOT_FOUND_HEADING }),
    ).not.toBeInTheDocument();
  });
});

// Integration on the artifacts tab index route (design-brief блок 6.2): with
// nothing selected the viewer panel carries a prompt of its own instead of the
// inline markup the router used to hold. Адрес артефакта — `?path=` (feat-011),
// поэтому «ничего не выбрано» — это отсутствие query-параметра, а не индекса.

describe("AppRoutes — the artifacts tab without a selection", () => {
  const ARTIFACT_PROMPT =
    "Выберите артефакт из списка слева, чтобы посмотреть его.";

  it("prompts to pick an artifact while none is open", async () => {
    setAccessToken(fakeJwt());
    server.use(
      ...appHandlers(),
      http.get(`/api/projects/${PROJECT_ID}/artifacts`, () =>
        HttpResponse.json({
          items: [
            {
              path: "konspekt.md",
              title: "Конспект лекции",
              type: "md",
              updated_at: "2026-07-01T10:00:00Z",
            },
          ],
          total: 1,
          limit: 200,
          offset: 0,
        }),
      ),
    );

    renderAppAt(`/projects/${PROJECT_ID}/artifacts`);

    expect(await screen.findByText(ARTIFACT_PROMPT)).toBeInTheDocument();
  });
});

// Integration (feat-008, трек T2): вход в SPA как маршрут, а не модалка. Guard
// `RequireAuth` стоит над группой защищённых роутов, `/login` лежит снаружи.
// Наблюдаем через сам роутер: зонд рядом с `<AppRoutes />` печатает текущий путь
// и строку `from`, положенную guard'ом в `location.state` — то самое значение,
// которое потом уходит и в `navigate(from)`, и в query-параметр `next`
// (design-brief § Frontend). Зонд печатает и тип навигации: редирект guard'а
// обязан заменять запись истории, иначе Back с `/login` возвращает на
// защищённый URL, который тут же редиректит обратно — Back для пользователя
// перестаёт работать. Отличить push от replace рендером нельзя (в обоих
// случаях на экране `/login`), поэтому наблюдаем ту самую запись истории,
// которую делает роутер.

const LOGIN_HEADING = "Вход";

function LocationProbe() {
  const location = useLocation();
  const navigationType = useNavigationType();
  const state = location.state as { from?: string } | null;
  return (
    <>
      <div>{`probe:${location.pathname}|${state?.from ?? ""}`}</div>
      <div>{`nav:${navigationType}`}</div>
    </>
  );
}

function renderRoutedAt(entry: string) {
  return renderWithProviders(
    <MemoryRouter initialEntries={[entry]}>
      <AppRoutes />
      <LocationProbe />
    </MemoryRouter>,
  );
}

describe("AppRoutes — guard входа и публичный /login", () => {
  it("уводит анонима с защищённого маршрута на /login, запоминая исходный путь строкой", async () => {
    server.use(authProvidersHandlers.ru());

    renderRoutedAt("/projects/p1/artifacts?tab=all#top");

    expect(
      await screen.findByRole("heading", { name: LOGIN_HEADING }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("probe:/login|/projects/p1/artifacts?tab=all#top"),
    ).toBeInTheDocument();
    // Защищённый URL заменён в истории, а не задвинут под `/login`.
    expect(screen.getByText("nav:REPLACE")).toBeInTheDocument();
  });

  it("открывает /login без токена — маршрут публичный, вне guard'а", async () => {
    server.use(authProvidersHandlers.ru());

    renderRoutedAt("/login");

    expect(
      await screen.findByRole("heading", { name: LOGIN_HEADING }),
    ).toBeInTheDocument();
    expect(screen.getByText("probe:/login|")).toBeInTheDocument();
  });
});
