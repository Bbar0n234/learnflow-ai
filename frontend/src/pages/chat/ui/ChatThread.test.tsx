import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { StrictMode, useEffect } from "react";
import {
  MemoryRouter,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { setAccessToken } from "@/shared/api/client";
import { server } from "@/test/msw/server";
import { fakeJwt, sseFrame, sseResponseStream } from "@/test/sse-stream";
import { createTestQueryClient, renderWithProviders } from "@/test/test-utils";

import { ChatThread } from "./ChatThread";

// Integration (feat-002, T2.5): the chat screen as the landing point of both
// entry paths. The message typed on the previous screen travels in router
// state; on arrival the thread must dispatch it exactly once and then wipe the
// state, so that a refresh or a back/forward step never re-sends it
// (design-brief § Создание чата и первое сообщение — контракты гонок). Network
// (chat detail, project, agent SSE) is MSW.

const PROJECT_ID = "p1";
const CHAT_ID = "c1";
const CHAT_URL = `/api/projects/${PROJECT_ID}/chats/${CHAT_ID}`;
const MESSAGES_URL = `${CHAT_URL}/messages`;
const PROJECT_URL = `/api/projects/${PROJECT_ID}`;
/** Соседний чат того же проекта — цель переключения в кейсе скоупинга ниже. */
const OTHER_CHAT_ID = "c2";
const OTHER_CHAT_URL = `/api/projects/${PROJECT_ID}/chats/${OTHER_CHAT_ID}`;
const OTHER_CHAT_MESSAGE = "Сообщение соседнего чата";
/** Текст, с которым поток падает в кейсе скоупинга красной плашки. */
const STREAM_ERROR = "Модель не ответила";
/** What the server stores as the agent's reply — never streamed verbatim. */
const STORED_ANSWER = "Ответ агента, сохранённый на сервере";

function streamResponse(events: unknown[]): Response {
  return new HttpResponse(sseResponseStream(events.map((e) => sseFrame(e))), {
    headers: { "Content-Type": "text/event-stream" },
  }) as unknown as Response;
}

/**
 * Поток, который отдал кадры и **не закрылся**, — ход идёт прямо сейчас. Нужен
 * там, где проверяется состояние живого хода: терминальное событие и даже конец
 * тела потока это состояние снимают. Разрывает его размонтирование экрана
 * (`useAgentStream` зовёт `abort()` в cleanup).
 */
function heldStream(frames: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) {
        controller.enqueue(encoder.encode(frame));
      }
    },
  });
  return new HttpResponse(body, {
    headers: { "Content-Type": "text/event-stream" },
  }) as unknown as Response;
}

function emptyChat() {
  return HttpResponse.json({
    thread_id: CHAT_ID,
    title: "Новый чат",
    security_blocked: false,
    messages: [],
  });
}

/**
 * Соседний чат с собственным сообщением: его появление на экране — признак
 * того, что переключение состоялось и чат **загрузился**. Без этого признака
 * кейсы скоупинга ниже были бы зелёными и с багом — пока идёт запрос истории,
 * экран занят «Loading chat...» и не показывает ничего чужого просто потому,
 * что не показывает ничего.
 */
function otherChat() {
  return HttpResponse.json({
    thread_id: OTHER_CHAT_ID,
    title: "Соседний чат",
    security_blocked: false,
    messages: [
      {
        id: "m-other",
        role: "user",
        content: OTHER_CHAT_MESSAGE,
        created_at: "2026-07-01T10:00:00Z",
        artifacts: [],
      },
    ],
  });
}

/** The project the chat belongs to — read by the header, same in every case. */
function projectHandler() {
  return http.get(PROJECT_URL, () =>
    HttpResponse.json({
      id: PROJECT_ID,
      name: "Матан",
      created_at: "2026-07-01T10:00:00Z",
      updated_at: "2026-07-01T10:00:00Z",
    }),
  );
}

/**
 * A chat that really records the exchange: every send lands in `sentBodies`,
 * and the persisted history grows with the user message plus the agent's answer.
 * The stored answer is deliberately a different string from the streamed chunk —
 * seeing it on screen is the proof that the refetched history (not the stream)
 * is what the thread renders once `done` has arrived.
 */
function recordingChat() {
  const sentBodies: string[] = [];
  const persisted: unknown[] = [];
  const handlers = [
    projectHandler(),
    http.get(CHAT_URL, () =>
      HttpResponse.json({
        thread_id: CHAT_ID,
        title: "Новый чат",
        security_blocked: false,
        messages: persisted,
      }),
    ),
    http.post(MESSAGES_URL, async ({ request }) => {
      const body = await request.text();
      sentBodies.push(body);
      persisted.push(
        {
          id: `m-user-${persisted.length}`,
          role: "user",
          content: (JSON.parse(body) as { content: string }).content,
          created_at: "2026-07-01T10:00:00Z",
          artifacts: [],
        },
        {
          id: `m-agent-${persisted.length}`,
          role: "assistant",
          content: STORED_ANSWER,
          created_at: "2026-07-01T10:00:01Z",
          artifacts: [],
        },
      );
      return streamResponse([
        { type: "text_chunk", content: "Производная — это..." },
        { type: "done", message_id: "m-1", trace_id: null },
      ]);
    }),
  ];
  return { sentBodies, handlers };
}

/** Reports what router state the chat screen is currently sitting on. */
function StateProbe() {
  const location = useLocation();
  const state = location.state as { initialMessage?: string } | null;
  return <p>Очередь входа: {state?.initialMessage ?? "пусто"}</p>;
}

/**
 * Records the effect passes React ran on this tree. Under Strict Mode they must
 * be mount → cleanup → mount; without it, a single mount. Guards the Strict
 * Mode case below from going vacuous if the double pass ever stops happening.
 */
function EffectPassProbe({ passes }: { passes: string[] }) {
  useEffect(() => {
    passes.push("mount");
    return () => {
      passes.push("cleanup");
    };
  }, [passes]);
  return null;
}

function renderChatThread(
  state: { initialMessage?: string } | null,
  // `strict` mounts the screen the way `main.tsx` does in dev — React then runs
  // effects as mount → cleanup → mount (see the Strict Mode case below).
  { strict = false }: { strict?: boolean } = {},
) {
  const effectPasses: string[] = [];
  const screenTree = (
    <MemoryRouter
      initialEntries={[
        { pathname: `/projects/${PROJECT_ID}/chats/${CHAT_ID}`, state },
      ]}
    >
      <Routes>
        <Route path="/projects/:id/chats/:cid" element={<ChatThread />} />
      </Routes>
      <StateProbe />
      <EffectPassProbe passes={effectPasses} />
    </MemoryRouter>
  );
  if (!strict) return { effectPasses, ...renderWithProviders(screenTree) };
  // React re-runs effects only when `StrictMode` is the **root** of the
  // rendered tree — nested inside another element it stays inert (checked in
  // this environment). That is exactly how the app mounts
  // (`main.tsx`: `<StrictMode><Providers>…`), so here the providers go inside
  // Strict Mode instead of coming from `renderWithProviders`, which wraps from
  // the outside. Same fresh client with `retry: false` underneath.
  const queryClient = createTestQueryClient();
  return {
    effectPasses,
    queryClient,
    ...render(
      <StrictMode>
        <QueryClientProvider client={queryClient}>
          {screenTree}
        </QueryClientProvider>
      </StrictMode>,
    ),
  };
}

/**
 * Переключение на соседний чат тем же маршрутом — то есть без перемонтирования
 * `ChatThread`, ровно как в приложении (боковая панель ведёт на `chats/:cid`).
 */
function ChatSwitch() {
  const navigate = useNavigate();
  return (
    <button
      type="button"
      onClick={() => navigate(`/projects/${PROJECT_ID}/chats/${OTHER_CHAT_ID}`)}
    >
      Открыть соседний чат
    </button>
  );
}

function renderChatWithSwitch(state: { initialMessage?: string } | null) {
  return renderWithProviders(
    <MemoryRouter
      initialEntries={[
        { pathname: `/projects/${PROJECT_ID}/chats/${CHAT_ID}`, state },
      ]}
    >
      <Routes>
        <Route path="/projects/:id/chats/:cid" element={<ChatThread />} />
      </Routes>
      <ChatSwitch />
    </MemoryRouter>,
  );
}

// jsdom has no layout — the message feed auto-scrolls a ref into view.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  localStorage.clear();
});

describe("ChatThread — first message handed over by the entry path", () => {
  it("sends the queued message once and shows it in the thread", async () => {
    setAccessToken(fakeJwt());
    // The server persists the exchange, so the post-`done` refetch returns it —
    // that is where a re-sent or duplicated message would show up.
    const { sentBodies, handlers } = recordingChat();
    server.use(...handlers);

    renderChatThread({ initialMessage: "Объясни производные" });

    // Exactly one send reaches the server, carrying the typed text…
    await waitFor(() => expect(sentBodies).toHaveLength(1));
    expect(sentBodies.map((body) => JSON.parse(body) as unknown)).toEqual([
      { content: "Объясни производные" },
    ]);
    // …and once the stream has finished and the refetched history is on screen,
    // that message is there exactly once — neither the optimistic copy nor the
    // refetched one duplicates it.
    expect(await screen.findByText(STORED_ANSWER)).toBeInTheDocument();
    expect(screen.getAllByText("Объясни производные")).toHaveLength(1);
    expect(sentBodies).toHaveLength(1);
  });

  // Regression of `{T2.5}`: in dev the app lives under `<StrictMode>`, where
  // React runs effects as mount → cleanup → mount. A send made straight in the
  // effect body did not survive that pass — it set up an `AbortController` and
  // went into `await ensureFreshToken()`, the `useAgentStream` cleanup called
  // `abort()` right away, and the request left with an already aborted signal
  // (never reaching the server), while the second mount hit the ref guard. The
  // user was left in an empty chat with no answer and no error. Hence the
  // assertion is the network fact — how many sends reached the handler — and
  // not the number of effect passes: what was broken is «reached the server».
  it("dispatches the queued message once under the Strict Mode double effect pass", async () => {
    setAccessToken(fakeJwt());
    const { sentBodies, handlers } = recordingChat();
    server.use(...handlers);

    const { effectPasses } = renderChatThread(
      { initialMessage: "Объясни производные" },
      { strict: true },
    );

    // The double pass really happened — otherwise this case would silently
    // degrade into a copy of the one above and stop guarding the regression.
    expect(effectPasses).toEqual(["mount", "cleanup", "mount"]);
    // Exactly one send reached the server — not zero (killed by the cleanup),
    // not two (dispatched on both effect passes).
    await waitFor(() => expect(sentBodies).toHaveLength(1));
    expect(sentBodies.map((body) => JSON.parse(body) as unknown)).toEqual([
      { content: "Объясни производные" },
    ]);
    // And it was not aborted: the stream was read through `done` and the
    // refetched history put the server-side answer on screen — an aborted
    // request yields neither.
    expect(await screen.findByText(STORED_ANSWER)).toBeInTheDocument();
    expect(screen.getAllByText("Объясни производные")).toHaveLength(1);
    // The router state is wiped, so the remount (this very Strict pass), a
    // refresh or a back/forward step have nothing left to re-send.
    await waitFor(() =>
      expect(screen.getByText("Очередь входа: пусто")).toBeInTheDocument(),
    );
    expect(sentBodies).toHaveLength(1);
  });

  it("clears the queued message from router state right after dispatching it", async () => {
    setAccessToken(fakeJwt());
    server.use(
      projectHandler(),
      http.get(CHAT_URL, () => emptyChat()),
      http.post(MESSAGES_URL, () =>
        streamResponse([{ type: "done", message_id: "m-1", trace_id: null }]),
      ),
    );

    renderChatThread({ initialMessage: "Привет" });

    // Wiping the state is what makes refresh / back / forward on this URL a
    // no-op — nothing is left to re-send.
    expect(await screen.findByText("Очередь входа: пусто")).toBeInTheDocument();
  });

  it("sends nothing when the chat is opened without a queued message", async () => {
    setAccessToken(fakeJwt());
    server.use(
      projectHandler(),
      http.get(CHAT_URL, () =>
        HttpResponse.json({
          thread_id: CHAT_ID,
          title: "Производные",
          security_blocked: false,
          messages: [
            {
              id: "m-old",
              role: "user",
              content: "Старое сообщение",
              created_at: "2026-07-01T10:00:00Z",
              artifacts: [],
            },
          ],
        }),
      ),
      // No POST handler on purpose: MSW is configured with
      // `onUnhandledRequest: "error"`, so an unexpected send fails the test.
    );

    renderChatThread(null);

    expect(await screen.findByText("Старое сообщение")).toBeInTheDocument();
    expect(screen.getByText("Очередь входа: пусто")).toBeInTheDocument();
  });

  // Регрессия ревью: `ChatThread` при смене чата не перемонтируется — маршрут
  // `chats/:cid` рендерит один и тот же компонент без `key`. Нескоупленное
  // состояние экрана уезжало вместе с ним, и пользователь видел в соседнем чате
  // сообщение об остановке чужого хода. `isStreaming` рядом скоуплен по чату
  // намеренно — причина остановки обязана жить по тому же правилу.
  it("не переносит уведомление об остановке хода в соседний чат", async () => {
    setAccessToken(fakeJwt());
    server.use(
      projectHandler(),
      http.get(CHAT_URL, () => emptyChat()),
      http.get(OTHER_CHAT_URL, () => otherChat()),
      // Ход первого чата обрывается отменой — экран показывает «Генерация
      // остановлена» рядом со `streamError`.
      http.post(MESSAGES_URL, () => streamResponse([{ type: "cancelled" }])),
    );

    renderChatWithSwitch({ initialMessage: "Объясни производные" });

    expect(
      await screen.findByText("Генерация остановлена"),
    ).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Открыть соседний чат" }),
    );

    // Ждём именно загруженного соседнего чата: пока он грузится, экран занят
    // «Loading chat...» и уведомления не показал бы даже с багом.
    expect(await screen.findByText(OTHER_CHAT_MESSAGE)).toBeInTheDocument();
    expect(screen.queryByText("Генерация остановлена")).not.toBeInTheDocument();
  });

  // Тот же дефект, что и у причины остановки, на двух соседних состояниях
  // экрана: красная плашка ошибки и оптимистичная копия отправленного
  // сообщения тоже переезжали в соседний чат и висели там до первой отправки.
  it("не переносит красную плашку ошибки в соседний чат", async () => {
    setAccessToken(fakeJwt());
    server.use(
      projectHandler(),
      http.get(CHAT_URL, () => emptyChat()),
      http.get(OTHER_CHAT_URL, () => otherChat()),
      http.post(MESSAGES_URL, () =>
        streamResponse([{ type: "error", detail: STREAM_ERROR }]),
      ),
    );

    renderChatWithSwitch({ initialMessage: "Объясни производные" });

    expect(await screen.findByText(STREAM_ERROR)).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Открыть соседний чат" }),
    );

    expect(await screen.findByText(OTHER_CHAT_MESSAGE)).toBeInTheDocument();
    expect(screen.queryByText(STREAM_ERROR)).not.toBeInTheDocument();
  });

  it("не переносит оптимистичную копию отправленного сообщения в соседний чат", async () => {
    setAccessToken(fakeJwt());
    server.use(
      projectHandler(),
      http.get(CHAT_URL, () => emptyChat()),
      http.get(OTHER_CHAT_URL, () => otherChat()),
      // Ход не заканчивается вовсе: копия снимается терминальным событием,
      // поэтому проверять её переезд можно только пока ход идёт.
      http.post(MESSAGES_URL, () =>
        heldStream([sseFrame({ type: "text_chunk", content: "Производная" })]),
      ),
    );

    renderChatWithSwitch({ initialMessage: "Объясни производные" });

    expect(await screen.findByText("Объясни производные")).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Открыть соседний чат" }),
    );

    expect(await screen.findByText(OTHER_CHAT_MESSAGE)).toBeInTheDocument();
    expect(screen.queryByText("Объясни производные")).not.toBeInTheDocument();
  });

  it("does not wait for the chat history to load before sending", async () => {
    setAccessToken(fakeJwt());
    let sent = 0;
    // The history is held by the test, not by a timeout: whether the send got
    // ahead of it is then a fact of the handler, not a race between a delay and
    // the polling of `waitFor`.
    let releaseHistory!: () => void;
    const historyHeld = new Promise<void>((resolve) => {
      releaseHistory = resolve;
    });
    let historyDelivered = false;
    server.use(
      projectHandler(),
      // The chat was just created and is known to be empty; a slow history
      // request must not delay the first message.
      http.get(CHAT_URL, async () => {
        await historyHeld;
        historyDelivered = true;
        return emptyChat();
      }),
      http.post(MESSAGES_URL, () => {
        sent += 1;
        return streamResponse([
          { type: "done", message_id: "m-1", trace_id: null },
        ]);
      }),
    );

    renderChatThread({ initialMessage: "Срочно" });

    await waitFor(() => expect(sent).toBe(1));
    // The history has not been answered yet — the send went first.
    expect(historyDelivered).toBe(false);
    expect(screen.getByText("Loading chat...")).toBeInTheDocument();
    // Let the held history land before the test ends — a request still in
    // flight at teardown resolves into a torn-down environment.
    releaseHistory();
    expect(
      await screen.findByPlaceholderText("Сообщение..."),
    ).toBeInTheDocument();
  });
});
