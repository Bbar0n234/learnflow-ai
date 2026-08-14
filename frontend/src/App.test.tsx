import "@/test/match-media-polyfill";

import {
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { StrictMode } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { getAccessToken, setAccessToken } from "@/shared/api/client";
import { logger } from "@/shared/lib/logger";
import { authProvidersHandlers } from "@/test/msw/auth-providers";
import { server } from "@/test/msw/server";
import { fakeJwt } from "@/test/sse-stream";

import { App } from "./App";

// Integration (feat-008, трек T2): бутстрап аутентификации на app-уровне —
// поверхность, недостижимая из `app/router.test.tsx`, потому что хук живёт над
// `AppRoutes`, в самом `App`. Проверяем контракт design-brief § Frontend: пока
// бутстрап не завершён, маршруты не смонтированы (нет мигания `/login` и
// редирект-лупа); есть access — тихо готовы без сети; нет access — один тихий
// `POST /api/auth/refresh`, чей 401 не считается ошибкой.
//
// Рендер идёт не через `renderWithProviders`, а через локальный клиент с
// `QueryCache({ onError })`: «тихо» здесь означает «глобальный error-канал
// React Query не сработал» — в проде на нём висит `logger.error`
// (`app/providers/QueryProvider.tsx`), и наблюдать тишину надо на том же шве.
// Клиент создаётся заново на каждый тест: у бутстрап-запроса бесконечные
// `staleTime`/`gcTime`, общий кэш протёк бы между кейсами.

const REFRESH_URL = "/api/auth/refresh";
const ACCESS_TOKEN = "bootstrapped.access.token";

const LOADING_TEXT = "Загрузка...";
// Заголовок карточки входа — типографский блок мокапа, не heading-элемент.
const LOGIN_HEADING = "Вход";
const WELCOME_HEADING = "Добро пожаловать";

function emptyList() {
  return HttpResponse.json({ items: [], total: 0, limit: 10, offset: 0 });
}

/** Сеть защищённого экрана `/` — сайдбар и welcome-страница. */
function appHandlers() {
  return [
    http.get("/api/projects", () => emptyList()),
    http.get("/api/chats/recent", () => emptyList()),
    http.get("/api/auth/me", () =>
      HttpResponse.json({ id: "u1", name: "tester", is_admin: false }),
    ),
  ];
}

/**
 * Хендлер refresh-эндпоинта плюс счётчик обращений к нему. Счётчик получает
 * `request.credentials`: сам факт запроса ещё не значит, что refresh-cookie
 * ушла — без `credentials: "include"` кросс-origin fetch отправит запрос
 * (`same-origin`) и получит 401, то есть возврат из OAuth-callback'а сломается
 * молча. MSW отдаёт режим как есть, поэтому свойство наблюдаемо здесь же.
 */
function refreshHandler(status: 200 | 401) {
  const calls = vi.fn();
  const handler = http.post(REFRESH_URL, ({ request }) => {
    calls(request.credentials);
    return status === 200
      ? HttpResponse.json({ access_token: ACCESS_TOKEN, token_type: "bearer" })
      : HttpResponse.json({ detail: "Not authenticated" }, { status: 401 });
  });
  return { calls, handler };
}

function renderApp(entry: string, { strict = false } = {}) {
  window.history.pushState({}, "", entry);

  const queryErrors = vi.fn();
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    queryCache: new QueryCache({ onError: queryErrors }),
  });

  const tree = (
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  );

  return {
    queryErrors,
    ...render(strict ? <StrictMode>{tree}</StrictMode> : tree),
  };
}

beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  localStorage.clear();
  window.history.pushState({}, "", "/");
  // Спаи на `logger` глушат/наблюдают глобальный объект: без восстановления
  // они переживают кейс и делают файл порядок-зависимым (`restoreMocks` в
  // vitest.config.ts не включён).
  vi.restoreAllMocks();
});

describe("App — бутстрап аутентификации", () => {
  it("поднимает сессию по refresh-cookie, не показав по дороге /login", async () => {
    const loggerError = vi.spyOn(logger, "error");
    const refresh = refreshHandler(200);
    server.use(refresh.handler, ...appHandlers());

    const { queryErrors } = renderApp("/");

    // Синхронно после рендера: маршруты ещё не смонтированы, а значит guard не
    // успел увести на `/login` — на экране паттерн загрузки, не форма входа.
    expect(screen.getByText(LOADING_TEXT)).toBeInTheDocument();
    expect(screen.queryByText(LOGIN_HEADING)).not.toBeInTheDocument();

    expect(
      await screen.findByRole("heading", { name: WELCOME_HEADING }),
    ).toBeInTheDocument();
    expect(getAccessToken()).toBe(ACCESS_TOKEN);
    // Бутстрап обязан слать refresh-cookie: без `credentials: "include"` запрос
    // уходит анонимным и сессия после OAuth-callback'а не поднимется.
    expect(refresh.calls).toHaveBeenCalledWith("include");
    expect(window.location.pathname).toBe("/");
    expect(screen.queryByText(LOGIN_HEADING)).not.toBeInTheDocument();
    expect(queryErrors).not.toHaveBeenCalled();
    expect(loggerError).not.toHaveBeenCalled();
  });

  it("на 401 без cookie тихо остаётся анонимом и уводит на /login", async () => {
    const loggerError = vi.spyOn(logger, "error");
    const refresh = refreshHandler(401);
    server.use(refresh.handler, authProvidersHandlers.ru());

    const { queryErrors } = renderApp("/projects/p1");

    expect(await screen.findByText(LOGIN_HEADING)).toBeInTheDocument();
    expect(window.location.pathname).toBe("/login");
    expect(getAccessToken()).toBeNull();
    // Ожидаемый путь анонима — не ошибка: ни глобальный error-канал Query, ни
    // логгер не должны были сработать.
    expect(queryErrors).not.toHaveBeenCalled();
    expect(loggerError).not.toHaveBeenCalled();
    // Редирект-луп ассертом не сторожится: в jsdom он проявляется не лишним
    // экраном, а исключением React «Maximum update depth exceeded» — на нём
    // падает (и подвисает) сам кейс. Сторож здесь — то, что кейс вообще
    // доходит до конца, а не отдельная проверка количества заголовков.
  });

  it("на таймаут бутстрапа тихо остаётся анонимом и уводит на /login", async () => {
    const loggerError = vi.spyOn(logger, "error");
    // Настоящий бюджет (30 с) кейсу не отмотать: fake timers на связке
    // fetch + MSW + React Query делают прогон недетерминированным, а живое
    // ожидание — тридцатисекундным. Подменяется источник сигнала: фабрика
    // отдаёт уже сработавший `AbortSignal`, то есть `fetch` видит ровно то,
    // что увидел бы по истечении бюджета. Сторож двусторонний — если сигнал
    // перестанут передавать в `fetch`, подмена ни на что не повлияет,
    // хендлер ответит 200 и кейс покраснеет на отсутствии формы входа.
    vi.spyOn(AbortSignal, "timeout").mockReturnValue(AbortSignal.abort());
    const refresh = refreshHandler(200);
    server.use(refresh.handler, authProvidersHandlers.ru());

    const { queryErrors } = renderApp("/projects/p1");

    expect(await screen.findByText(LOGIN_HEADING)).toBeInTheDocument();
    expect(getAccessToken()).toBeNull();
    // Оборвавшийся по таймауту бутстрап — тот же тихий путь анонима, что и
    // 401: гейт обязан открыться (`ready`), а error-канал остаться молчащим.
    expect(queryErrors).not.toHaveBeenCalled();
    expect(loggerError).not.toHaveBeenCalled();
  });

  it("с access в localStorage готов сразу и не ходит на refresh", async () => {
    setAccessToken(fakeJwt());
    const refresh = refreshHandler(200);
    server.use(refresh.handler, ...appHandlers());

    renderApp("/");

    expect(
      await screen.findByRole("heading", { name: WELCOME_HEADING }),
    ).toBeInTheDocument();
    expect(refresh.calls).not.toHaveBeenCalled();
  });

  it("не задваивает refresh при двойном монтировании эффектов (StrictMode)", async () => {
    const refresh = refreshHandler(200);
    server.use(refresh.handler, ...appHandlers());

    renderApp("/", { strict: true });

    expect(
      await screen.findByRole("heading", { name: WELCOME_HEADING }),
    ).toBeInTheDocument();
    expect(refresh.calls).toHaveBeenCalledTimes(1);
  });
});
