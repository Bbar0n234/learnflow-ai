import { QueryClientProvider } from "@tanstack/react-query";
import { render, renderHook, waitFor } from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { createElement, useEffect, type ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { setAccessToken } from "@/shared/api/client";
import { queryKeys } from "@/shared/api/query-keys";
import type { ChatDetail } from "@/shared/api/chats";
import { findFeedCall } from "@/shared/lib/agent-feed";
import { server } from "@/test/msw/server";
import { createTestQueryClient } from "@/test/test-utils";
import { fakeJwt, sseFrame, sseResponseStream } from "@/test/sse-stream";

import { useStreamStore } from "@/stores/stream-store";
import { MessageList } from "../ui/MessageList";

import { useAgentStream } from "./useAgentStream";

// Integration: the agent SSE stream consumer. The hook POSTs to the messages
// endpoint and reads a text/event-stream body frame by frame, driving the
// stream store and lifecycle callbacks. Network is mocked with MSW's native
// streaming response; a non-expired JWT in localStorage lets ensureFreshToken
// resolve without a refresh round-trip.

const PROJECT_ID = "p1";
const CHAT_ID = "c1";
const MESSAGES_URL = `/api/projects/${PROJECT_ID}/chats/${CHAT_ID}/messages`;
const CANCEL_URL = `/api/projects/${PROJECT_ID}/chats/${CHAT_ID}/cancel`;
const REFRESH_URL = "/api/auth/refresh";
/** Соседний чат того же проекта — куда пользователь уходит посреди хода. */
const OTHER_CHAT_ID = "c2";
const OTHER_MESSAGES_URL = `/api/projects/${PROJECT_ID}/chats/${OTHER_CHAT_ID}/messages`;

function streamResponse(events: unknown[]): Response {
  return new HttpResponse(sseResponseStream(events.map((e) => sseFrame(e))), {
    headers: { "Content-Type": "text/event-stream" },
  }) as unknown as Response;
}

/**
 * A live SSE response whose frames are pushed from the test on demand and which
 * stays open until explicitly closed (or the reader is aborted). Lets a test
 * drive cancel/interruption timing against an in-flight stream.
 */
function liveStream() {
  const encoder = new TextEncoder();
  let ctrl!: ReadableStreamDefaultController<Uint8Array>;
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      ctrl = c;
    },
  });
  const response = new HttpResponse(body, {
    headers: { "Content-Type": "text/event-stream" },
  }) as unknown as Response;
  return {
    response,
    push: (event: unknown) => ctrl.enqueue(encoder.encode(sseFrame(event))),
    close: () => ctrl.close(),
  };
}

function renderAgentStream(options?: Parameters<typeof useAgentStream>[2]) {
  const queryClient = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  const { result, unmount } = renderHook(
    () => useAgentStream(PROJECT_ID, CHAT_ID, options),
    { wrapper },
  );
  return { result, queryClient, unmount };
}

/**
 * Хук, переживающий смену чата **без перемонтирования**, — ровно как в
 * приложении: маршрут `chats/:cid` рендерит один и тот же `ChatThread` без
 * `key`, поэтому уже начатый ход остаётся жив, а `chatId` под ним меняется.
 * Именно в этом зазоре и терялся владелец потока.
 */
function renderSwitchableStream(
  options?: Parameters<typeof useAgentStream>[2],
) {
  const queryClient = createTestQueryClient();
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  const { result, rerender, unmount } = renderHook(
    ({ chatId }: { chatId: string }) =>
      useAgentStream(PROJECT_ID, chatId, options),
    { wrapper, initialProps: { chatId: CHAT_ID } },
  );
  return {
    result,
    queryClient,
    unmount,
    switchTo: (chatId: string) => rerender({ chatId }),
  };
}

/**
 * Ответ сервера, который тест придерживает до нужного момента: даёт увести
 * пользователя в соседний чат раньше, чем ветка без SSE-событий (не-ok статус,
 * сетевой сбой) успеет позвать колбэк.
 */
function heldResponse() {
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { held, release };
}

afterEach(() => {
  localStorage.clear();
  vi.useRealTimers();
});

/** Текст ассистента, накопленный лентой активного хода. */
async function streamedText(): Promise<string> {
  const { useStreamStore } = await import("@/stores/stream-store");
  return useStreamStore
    .getState()
    .feed.reduce(
      (text, item) => (item.type === "text" ? text + item.content : text),
      "",
    );
}

async function isStreaming(): Promise<boolean> {
  const { useStreamStore } = await import("@/stores/stream-store");
  return useStreamStore.getState().isStreaming;
}

/** Лента активного хода — то, что диспетчер сложил из событий потока. */
async function streamedFeed() {
  const { useStreamStore } = await import("@/stores/stream-store");
  return useStreamStore.getState().feed;
}

async function isReviewing(): Promise<boolean> {
  const { useStreamStore } = await import("@/stores/stream-store");
  return useStreamStore.getState().isReviewing;
}

/** Чат, которому стор принадлежит прямо сейчас. */
function streamOwner(): string | null {
  return useStreamStore.getState().streamingChatId;
}

describe("useAgentStream", () => {
  it("invokes onDone with the message and trace ids on a done event", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([
          { type: "text_chunk", content: "Hello" },
          { type: "done", message_id: "m-1", trace_id: "t-1" },
        ]),
      ),
    );
    const onDone = vi.fn();
    const { result } = renderAgentStream({ onDone });

    result.current.send("hi");

    await waitFor(() =>
      expect(onDone).toHaveBeenCalledWith({
        chatId: CHAT_ID,
        messageId: "m-1",
        traceId: "t-1",
      }),
    );
  });

  // Редакция — операция над всей лентой хода, а не над одним текстом: после
  // блокировки на экране не остаётся ни строки рассуждений, ни строк вызовов —
  // ровно то, что покажет перезагрузка (streaming.md § История: typed parts).
  it("replaces the whole feed with a single stub on a security_block", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([
          { type: "reasoning_chunk", content: "надо обойти правила" },
          { type: "tool_call_started", call_id: "c-1", tool: "web_search" },
          { type: "text_chunk", content: "leaking secret" },
          { type: "security_block" },
        ]),
      ),
    );
    const onSecurityBlock = vi.fn();
    const { result } = renderAgentStream({ onSecurityBlock });

    result.current.send("hi");

    await waitFor(() => expect(onSecurityBlock).toHaveBeenCalledTimes(1));
    const { useStreamStore } = await import("@/stores/stream-store");
    const state = useStreamStore.getState();
    expect(state.redacted).toBe(true);
    expect(state.feed).toEqual([
      {
        id: "text-0",
        type: "text",
        content: "[Сообщение скрыто в целях безопасности]",
      },
    ]);
  });

  it("optimistically marks the chat security_blocked when blocked before any text", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([{ type: "security_block" }]),
      ),
    );
    const onSecurityBlock = vi.fn();
    const { result, queryClient } = renderAgentStream({ onSecurityBlock });
    queryClient.setQueryData<ChatDetail>(
      queryKeys.projects.chat(PROJECT_ID, CHAT_ID),
      {
        thread_id: CHAT_ID,
        title: "t",
        security_blocked: false,
        messages: [],
      },
    );

    result.current.send("hi");

    await waitFor(() => expect(onSecurityBlock).toHaveBeenCalledTimes(1));
    const cached = queryClient.getQueryData<ChatDetail>(
      queryKeys.projects.chat(PROJECT_ID, CHAT_ID),
    );
    expect(cached?.security_blocked).toBe(true);
  });

  it("forwards an error event detail to onError", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([{ type: "error", detail: "model exploded" }]),
      ),
    );
    const onError = vi.fn();
    const { result } = renderAgentStream({ onError });

    result.current.send("hi");

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(CHAT_ID, "model exploded"),
    );
  });

  it("reports a problem message when the POST returns a non-ok status", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        HttpResponse.json({ detail: "Доступ запрещён" }, { status: 403 }),
      ),
    );
    const onError = vi.fn();
    const { result } = renderAgentStream({ onError });

    result.current.send("hi");

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(CHAT_ID, "Доступ запрещён"),
    );
  });

  it("skips a malformed SSE frame and still completes the stream", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(
        MESSAGES_URL,
        () =>
          new HttpResponse(
            sseResponseStream([
              "data: {not valid json}\n\n",
              sseFrame({ type: "text_chunk", content: "ok" }),
              sseFrame({ type: "done", message_id: "m-9", trace_id: null }),
            ]),
            { headers: { "Content-Type": "text/event-stream" } },
          ),
      ),
    );
    const onDone = vi.fn();
    const onError = vi.fn();
    const { result } = renderAgentStream({ onDone, onError });

    result.current.send("hi");

    await waitFor(() =>
      expect(onDone).toHaveBeenCalledWith({
        chatId: CHAT_ID,
        messageId: "m-9",
        traceId: null,
      }),
    );
    expect(onError).not.toHaveBeenCalled();
  });

  it("sends a cancel request to the server and surfaces no error on a graceful cancel", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    let cancelHit = false;
    server.use(
      http.post(MESSAGES_URL, () => live.response),
      http.post(CANCEL_URL, () => {
        cancelHit = true;
        return HttpResponse.json({ ok: true });
      }),
    );
    const onError = vi.fn();
    const onDone = vi.fn();
    const { result } = renderAgentStream({ onError, onDone });

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "partial" });
    await waitFor(async () => expect(await streamedText()).toBe("partial"));

    result.current.cancel();
    await waitFor(() => expect(cancelHit).toBe(true));

    // Server finalizes the cancelled turn with a terminal event.
    live.push({ type: "done", message_id: "m-cancel", trace_id: null });
    live.close();

    await waitFor(async () => expect(await isStreaming()).toBe(false));
    expect(onError).not.toHaveBeenCalled();
  });

  it("aborts the in-flight stream and resets the store on unmount", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const { result, unmount } = renderAgentStream();

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "partial" });
    await waitFor(async () => expect(await streamedText()).toBe("partial"));

    unmount();

    expect(await isStreaming()).toBe(false);
  });

  it("suppresses a trailing error event that arrives after cancel", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(
      http.post(MESSAGES_URL, () => live.response),
      // Server-side cancel succeeds; the reader keeps draining a final error frame.
      http.post(CANCEL_URL, () => HttpResponse.json({ ok: true })),
    );
    const onError = vi.fn();
    const { result } = renderAgentStream({ onError });

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "partial" });
    await waitFor(async () => expect(await streamedText()).toBe("partial"));

    // cancel() flips the cancelling flag synchronously, before the async
    // cancelChat round-trip; a trailing error frame must now be swallowed.
    result.current.cancel();
    live.push({ type: "error", detail: "stream torn down" });
    live.close();

    await waitFor(async () => expect(await isStreaming()).toBe(false));
    expect(onError).not.toHaveBeenCalled();
  });

  // Сторож тишины взводится синхронно в `send()`, до `fetch`: сервер, не
  // вернувший даже заголовков, иначе оставил бы пользователя в бесконечном
  // ожидании вместо ошибки.
  it("fires onError with the timeout message when the server sends nothing at all", async () => {
    setAccessToken(fakeJwt());
    vi.useFakeTimers();
    server.use(
      // Never responds — headers included.
      http.post(MESSAGES_URL, () => delay("infinite")),
    );
    const onError = vi.fn();
    const { result } = renderAgentStream({ onError });

    result.current.send("hi");
    // Порог — три пропущенных heartbeat подряд (3 × 5 с, streaming.md § Лимиты).
    await vi.advanceTimersByTimeAsync(14000);
    expect(onError).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(2000);

    expect(onError).toHaveBeenCalledWith(CHAT_ID, "Превышено время ожидания");
  });

  it("keeps a silent-but-alive stream running while heartbeats arrive", async () => {
    setAccessToken(fakeJwt());
    vi.useFakeTimers();
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const onError = vi.fn();
    const { result } = renderAgentStream({ onError });

    result.current.send("hi");
    // Ход молчит содержательно, но соединение живо: каждый heartbeat
    // перезаводит сторож, и совокупные 30 с тишины ошибкой не становятся.
    for (let i = 0; i < 3; i += 1) {
      await vi.advanceTimersByTimeAsync(10000);
      live.push({ type: "heartbeat" });
    }
    await vi.advanceTimersByTimeAsync(1000);

    expect(onError).not.toHaveBeenCalled();
    expect(await isStreaming()).toBe(true);
  });

  // Forward-compat (streaming.md § Forward-compat): контракт растёт без
  // версионирования пути — неизвестный тип не имеет права рвать поток.
  it("ignores an unknown event type and keeps reading the stream", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([
          { type: "brand_new_event", whatever: 42 },
          { type: "text_chunk", content: "продолжаем" },
          { type: "done", message_id: "m-fc", trace_id: null },
        ]),
      ),
    );
    const onDone = vi.fn();
    const onError = vi.fn();
    const { result } = renderAgentStream({ onDone, onError });

    result.current.send("hi");

    await waitFor(() =>
      expect(onDone).toHaveBeenCalledWith({
        chatId: CHAT_ID,
        messageId: "m-fc",
        traceId: null,
      }),
    );
    expect(onError).not.toHaveBeenCalled();
  });

  // Отмена — не ошибка: терминальный `cancelled` закрывает поток без
  // error-баннера, но рефетчит detail (там живут вызовы со статусом `pending`)
  // и списки чатов (автозаголовок пишется независимо от исхода хода).
  it("closes the stream on cancelled without an error and refetches the chat", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(
      http.post(MESSAGES_URL, () => live.response),
      http.post(CANCEL_URL, () => HttpResponse.json({ ok: true })),
    );
    const onError = vi.fn();
    const onDone = vi.fn();
    const onCancelled = vi.fn();
    const { result, queryClient } = renderAgentStream({
      onError,
      onDone,
      onCancelled,
    });
    primeTitleCaches(queryClient);

    result.current.send("hi");
    live.push({
      type: "tool_call_started",
      call_id: "c-1",
      tool: "firecrawl_search",
    });
    await waitFor(async () => expect(await isStreaming()).toBe(true));

    result.current.cancel();
    live.push({ type: "cancelled" });
    live.close();

    await waitFor(() => expect(onCancelled).toHaveBeenCalledTimes(1));
    expect(await isStreaming()).toBe(false);
    expect(onError).not.toHaveBeenCalled();
    expect(onDone).not.toHaveBeenCalled();
    expect(
      queryClient.getQueryState(queryKeys.projects.chat(PROJECT_ID, CHAT_ID))
        ?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState(queryKeys.projects.chats(PROJECT_ID))
        ?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState(queryKeys.chats.recent)?.isInvalidated,
    ).toBe(true);
  });

  it("retries the message POST after a 401 by refreshing the token, then completes", async () => {
    setAccessToken(fakeJwt(10)); // near expiry → proactive refresh round-trip
    let refreshCount = 0;
    let postCount = 0;
    server.use(
      http.post(REFRESH_URL, () => {
        refreshCount += 1;
        return HttpResponse.json({
          access_token: fakeJwt(3600),
          token_type: "bearer",
        });
      }),
      http.post(MESSAGES_URL, () => {
        postCount += 1;
        if (postCount === 1) {
          return HttpResponse.json({ detail: "expired" }, { status: 401 });
        }
        return streamResponse([
          { type: "text_chunk", content: "after retry" },
          { type: "done", message_id: "m-401", trace_id: null },
        ]);
      }),
    );
    const onDone = vi.fn();
    const { result } = renderAgentStream({ onDone });

    result.current.send("hi");

    await waitFor(() =>
      expect(onDone).toHaveBeenCalledWith({
        chatId: CHAT_ID,
        messageId: "m-401",
        traceId: null,
      }),
    );
    expect(postCount).toBe(2);
    expect(refreshCount).toBeGreaterThanOrEqual(1);
  });

  // Карточку в живом ходе фронт по `artifact_created` больше не рисует: факт
  // создания виден строкой ленты, полная карточка приезжает из истории после
  // завершения хода. За событием остаётся его побочный эффект — инвалидация
  // кэшей, и ниже проверяется именно она.
  //
  // Артефакт файловой модели адресуется путём, и кэши держатся свежими двумя
  // разными механизмами: точечной инвалидацией пути на событии и довозом
  // списка по завершении хода. Ниже проверяется, что один не съедает другой.
  const NOTES = "lecture-1/konspekt.md";
  const OTHER = "lecture-1/flashcards.md";

  function primeArtifactCaches(
    queryClient: ReturnType<typeof renderAgentStream>["queryClient"],
  ) {
    queryClient.setQueryData(queryKeys.projects.artifacts(PROJECT_ID), {
      items: [],
      total: 0,
      limit: 200,
      offset: 0,
    });
    for (const path of [NOTES, OTHER]) {
      queryClient.setQueryData(queryKeys.projects.artifact(PROJECT_ID, path), {
        path,
        title: path,
        type: "md",
        updated_at: "2026-02-01T12:00:00Z",
        content: "тело",
      });
      queryClient.setQueryData(
        queryKeys.projects.artifactMedia(PROJECT_ID, path),
        new Blob(["тело"]),
      );
    }
  }

  function invalidated(
    queryClient: ReturnType<typeof renderAgentStream>["queryClient"],
    key: readonly unknown[],
  ): boolean | undefined {
    return queryClient.getQueryState(key)?.isInvalidated;
  }

  it.each(["artifact_created", "artifact_updated"] as const)(
    "%s освежает свой путь вместе с его медиа, не задевая соседний артефакт",
    async (type) => {
      setAccessToken(fakeJwt());
      const live = liveStream();
      server.use(http.post(MESSAGES_URL, () => live.response));
      const onDone = vi.fn();
      const { result, queryClient } = renderAgentStream({ onDone });
      primeArtifactCaches(queryClient);

      result.current.send("hi");
      live.push({
        type,
        path: NOTES,
        title: "Конспект",
        artifact_type: "md",
        ...(type === "artifact_updated"
          ? { diff: { added: 12, removed: 3 } }
          : {}),
      });

      await waitFor(() =>
        expect(
          invalidated(
            queryClient,
            queryKeys.projects.artifact(PROJECT_ID, NOTES),
          ),
        ).toBe(true),
      );
      // Миниатюра карточки и картинка вьюера живут потомком того же ключа —
      // перезаписанный по пути файл обязан перерисоваться вместе с деталью.
      expect(
        invalidated(
          queryClient,
          queryKeys.projects.artifactMedia(PROJECT_ID, NOTES),
        ),
      ).toBe(true);
      expect(
        invalidated(queryClient, queryKeys.projects.artifacts(PROJECT_ID)),
      ).toBe(true);
      // Событие про один файл не имеет права сбрасывать соседний: список
      // инвалидируется точно своим ключом, а не префиксом всех артефактов.
      expect(
        invalidated(
          queryClient,
          queryKeys.projects.artifact(PROJECT_ID, OTHER),
        ),
      ).toBe(false);

      live.push({ type: "done", message_id: "m-art", trace_id: null });
      live.close();
      await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    },
  );

  it.each([
    {
      name: "done",
      event: { type: "done", message_id: "m-1", trace_id: null },
    },
    { name: "cancelled", event: { type: "cancelled" } },
    { name: "error", event: { type: "error", detail: "джоба упала" } },
  ])(
    "довозит список артефактов на терминальном событии $name",
    async ({ event }) => {
      // Событий удаления и переименования в контракте нет: файл, который джоба
      // снесла или переименовала, иначе остался бы призраком в списке до
      // перезагрузки страницы (A6c, B9 — сироты отменённой джобы).
      setAccessToken(fakeJwt());
      server.use(http.post(MESSAGES_URL, () => streamResponse([event])));
      const { result, queryClient } = renderAgentStream({
        onError: vi.fn(),
        onCancelled: vi.fn(),
        onDone: vi.fn(),
      });
      primeArtifactCaches(queryClient);

      result.current.send("hi");

      await waitFor(() =>
        expect(
          invalidated(queryClient, queryKeys.projects.artifacts(PROJECT_ID)),
        ).toBe(true),
      );
      // Довоз списка — не сброс открытого артефакта: `exact` держит детали и
      // медиа тех же путей нетронутыми.
      expect(
        invalidated(
          queryClient,
          queryKeys.projects.artifact(PROJECT_ID, NOTES),
        ),
      ).toBe(false);
    },
  );

  // Пути вложений едут в теле того же POST, что и текст (design-brief
  // § Вложения пользователя): upload к этому моменту уже прошёл.
  describe("вложения в теле сообщения", () => {
    function recordingMessages(bodies: string[]) {
      return http.post(MESSAGES_URL, async ({ request }) => {
        bodies.push(await request.text());
        return streamResponse([
          { type: "done", message_id: "m-1", trace_id: null },
        ]);
      });
    }

    it("кладёт пути вложений рядом с текстом", async () => {
      setAccessToken(fakeJwt());
      const bodies: string[] = [];
      server.use(recordingMessages(bodies));
      const onDone = vi.fn();
      const { result } = renderAgentStream({ onDone });

      result.current.send("Разбери конспект", [
        "uploads/notes.md",
        "uploads/lecture.pdf",
      ]);

      await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
      expect(JSON.parse(bodies[0]!) as unknown).toEqual({
        content: "Разбери конспект",
        attachments: ["uploads/notes.md", "uploads/lecture.pdf"],
      });
    });

    it("ход без файлов отправляет тело без поля вложений", async () => {
      setAccessToken(fakeJwt());
      const bodies: string[] = [];
      server.use(recordingMessages(bodies));
      const onDone = vi.fn();
      const { result } = renderAgentStream({ onDone });

      result.current.send("Просто вопрос");

      await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
      expect(JSON.parse(bodies[0]!) as unknown).toEqual({
        content: "Просто вопрос",
      });
    });

    it("повторяет вложения и в ретрае после протухшего токена", async () => {
      // Ретрай пересобирает запрос целиком — потерянные на нём пути означали
      // бы, что агент не увидит уже загруженных файлов.
      setAccessToken(fakeJwt(10));
      const bodies: string[] = [];
      server.use(
        http.post(REFRESH_URL, () =>
          HttpResponse.json({
            access_token: fakeJwt(3600),
            token_type: "bearer",
          }),
        ),
        http.post(MESSAGES_URL, async ({ request }) => {
          bodies.push(await request.text());
          if (bodies.length === 1) {
            return HttpResponse.json({ detail: "expired" }, { status: 401 });
          }
          return streamResponse([
            { type: "done", message_id: "m-1", trace_id: null },
          ]);
        }),
      );
      const onDone = vi.fn();
      const { result } = renderAgentStream({ onDone });

      result.current.send("Разбери конспект", ["uploads/notes.md"]);

      await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
      expect(bodies).toHaveLength(2);
      expect(JSON.parse(bodies[1]!) as unknown).toEqual({
        content: "Разбери конспект",
        attachments: ["uploads/notes.md"],
      });
    });
  });

  // Пара review-событий — единственный источник индикатора «Проверяем ответ...»:
  // ставить флаг больше некому, и её отсутствие на ходе не должно оставлять
  // индикатор висеть.
  it("поднимает и снимает флаг проверки ответа по паре review-событий", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const { result } = renderAgentStream();

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "готовый ответ" });
    await waitFor(async () =>
      expect(await streamedText()).toBe("готовый ответ"),
    );
    expect(await isReviewing()).toBe(false);

    live.push({ type: "final_output_review_started" });
    await waitFor(async () => expect(await isReviewing()).toBe(true));

    live.push({ type: "final_output_review_complete" });
    await waitFor(async () => expect(await isReviewing()).toBe(false));

    live.push({ type: "done", message_id: "m-rev", trace_id: null });
    live.close();
    await waitFor(async () => expect(await isStreaming()).toBe(false));
  });

  it("reports a broken connection when the stream ends without a terminal event", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([{ type: "text_chunk", content: "incomplete" }]),
      ),
    );
    const onError = vi.fn();
    const onDone = vi.fn();
    const { result } = renderAgentStream({ onError, onDone });

    result.current.send("hi");

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(CHAT_ID, "Соединение прервано"),
    );
    expect(onDone).not.toHaveBeenCalled();
  });

  it("reports a connection error on a non-abort fetch failure", async () => {
    setAccessToken(fakeJwt());
    server.use(http.post(MESSAGES_URL, () => HttpResponse.error()));
    const onError = vi.fn();
    const { result } = renderAgentStream({ onError });

    result.current.send("hi");

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(CHAT_ID, "Ошибка соединения"),
    );
  });

  // feat-002 (T2.2): the non-terminal `title_updated` event carries the
  // generated chat name mid-stream. It may only patch caches in place — a
  // refetch of the open chat would duplicate the optimistic user message that
  // still lives in `localMessages` (design-brief § Доставка title на фронт).
  const GENERATED_TITLE = "Производные функции";

  function primeTitleCaches(
    queryClient: ReturnType<typeof renderAgentStream>["queryClient"],
  ) {
    queryClient.setQueryData(queryKeys.projects.chats(PROJECT_ID), {
      items: [{ thread_id: CHAT_ID, title: "Новый чат" }],
      total: 1,
      limit: 200,
      offset: 0,
    });
    queryClient.setQueryData(queryKeys.chats.recent, {
      items: [{ thread_id: CHAT_ID, title: "Новый чат" }],
      total: 1,
      limit: 10,
      offset: 0,
    });
    queryClient.setQueryData<ChatDetail>(
      queryKeys.projects.chat(PROJECT_ID, CHAT_ID),
      {
        thread_id: CHAT_ID,
        title: "Новый чат",
        security_blocked: false,
        messages: [],
      },
    );
  }

  function titleIn(
    queryClient: ReturnType<typeof renderAgentStream>["queryClient"],
    key: readonly unknown[],
  ): string | undefined {
    const data = queryClient.getQueryData<{
      items: { thread_id: string; title: string }[];
    }>(key);
    return data?.items.find((c) => c.thread_id === CHAT_ID)?.title;
  }

  it("patches the generated title into the chat list, recents and the open chat", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([
          { type: "text_chunk", content: "Начнём" },
          { type: "title_updated", title: GENERATED_TITLE },
          { type: "done", message_id: "m-t", trace_id: null },
        ]),
      ),
    );
    const onDone = vi.fn();
    const { result, queryClient } = renderAgentStream({ onDone });
    primeTitleCaches(queryClient);

    result.current.send("расскажи про производные");

    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(titleIn(queryClient, queryKeys.projects.chats(PROJECT_ID))).toBe(
      GENERATED_TITLE,
    );
    expect(titleIn(queryClient, queryKeys.chats.recent)).toBe(GENERATED_TITLE);
    expect(
      queryClient.getQueryData<ChatDetail>(
        queryKeys.projects.chat(PROJECT_ID, CHAT_ID),
      )?.title,
    ).toBe(GENERATED_TITLE);
  });

  it("keeps the stream running after a title_updated and refetches nothing", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const { result, queryClient } = renderAgentStream();
    primeTitleCaches(queryClient);

    result.current.send("привет");
    live.push({ type: "title_updated", title: GENERATED_TITLE });
    await waitFor(() =>
      expect(titleIn(queryClient, queryKeys.chats.recent)).toBe(
        GENERATED_TITLE,
      ),
    );

    // Non-terminal: text keeps arriving and the stream is still open, and no
    // query was invalidated by the event itself.
    expect(
      queryClient.getQueryState(queryKeys.projects.chat(PROJECT_ID, CHAT_ID))
        ?.isInvalidated,
    ).toBe(false);
    expect(
      queryClient.getQueryState(queryKeys.projects.chats(PROJECT_ID))
        ?.isInvalidated,
    ).toBe(false);
    expect(
      queryClient.getQueryState(queryKeys.chats.recent)?.isInvalidated,
    ).toBe(false);
    live.push({ type: "text_chunk", content: "продолжение" });
    await waitFor(async () => expect(await streamedText()).toBe("продолжение"));
    expect(await isStreaming()).toBe(true);

    live.push({ type: "done", message_id: "m-open", trace_id: null });
    live.close();
    await waitFor(async () => expect(await isStreaming()).toBe(false));
  });

  it("ignores a title_updated for caches that are not mounted", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([
          { type: "title_updated", title: GENERATED_TITLE },
          { type: "done", message_id: "m-nocache", trace_id: null },
        ]),
      ),
    );
    const onDone = vi.fn();
    const onError = vi.fn();
    // No caches primed: lists may simply not be mounted in this session.
    const { result, queryClient } = renderAgentStream({ onDone, onError });

    result.current.send("привет");

    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(onError).not.toHaveBeenCalled();
    expect(
      queryClient.getQueryData(queryKeys.projects.chats(PROJECT_ID)),
    ).toBeUndefined();
  });

  it("falls back to refetching the project chat list on done, exactly that key", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        // No title_updated at all — the generation did not finish in time.
        streamResponse([{ type: "done", message_id: "m-fb", trace_id: null }]),
      ),
    );
    const onDone = vi.fn();
    const { result, queryClient } = renderAgentStream({ onDone });
    primeTitleCaches(queryClient);
    // A sibling chat's detail shares the list key as a prefix — `exact: true`
    // must leave it alone even on the terminal event.
    queryClient.setQueryData<ChatDetail>(
      queryKeys.projects.chat(PROJECT_ID, "c2"),
      {
        thread_id: "c2",
        title: "Другой чат",
        security_blocked: false,
        messages: [],
      },
    );

    result.current.send("привет");

    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    expect(
      queryClient.getQueryState(queryKeys.projects.chats(PROJECT_ID))
        ?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState(queryKeys.chats.recent)?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState(queryKeys.projects.chat(PROJECT_ID, "c2"))
        ?.isInvalidated,
    ).toBe(false);
  });

  // Диспетчер — единственное место, где словарь v2 превращается в содержимое
  // экрана. Семь событий ленты обязаны дойти до модели: пропущенная ветка не
  // роняет поток, а просто стирает часть работы агента из виду.
  it("доводит до ленты каждое событие хода, включая срез вызова guard'ом", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const { result } = renderAgentStream();

    result.current.send("hi");
    live.push({ type: "stream_started" });
    live.push({ type: "reasoning_chunk", content: "Надо поискать" });
    live.push({ type: "heartbeat" });
    live.push({
      type: "tool_call_started",
      call_id: "c-1",
      tool: "firecrawl_search",
    });
    live.push({
      type: "tool_call_args",
      call_id: "c-1",
      args: '{"query": "langgraph"}',
      truncated: false,
    });
    live.push({
      type: "tool_result",
      call_id: "c-1",
      tool: "firecrawl_search",
      status: "success",
      content: "нашлось",
      truncated: false,
    });
    live.push({
      type: "tool_call_started",
      call_id: "c-2",
      tool: "load_skill",
    });
    live.push({ type: "tool_call_cancelled", call_id: "c-2" });
    live.push({ type: "agent_event", kind: "compaction", payload: {} });
    live.push({ type: "text_chunk", content: "Вот что нашлось." });

    await waitFor(async () =>
      expect((await streamedFeed()).length).toBeGreaterThanOrEqual(5),
    );
    const feed = await streamedFeed();
    expect(
      feed.map((item) => (item.type === "tool_call" ? item.callId : item.type)),
    ).toEqual(["reasoning", "c-1", "c-2", "agent_event", "text"]);
    expect(
      feed.map((item) => (item.type === "tool_call" ? item.status : null)),
    ).toEqual([null, "success", "cancelled", null, null]);
    // Содержимое каждой ветки, а не только форма ленты. Аргументы дороже
    // прочего: без них строка теряет дополнение подписи, разворот — зону
    // «Вызов», а субагент — задание, ради которого его позвали.
    expect(findFeedCall(feed, "c-1")).toMatchObject({
      tool: "firecrawl_search",
      args: '{"query": "langgraph"}',
      argsTruncated: false,
      result: "нашлось",
      resultTruncated: false,
    });
    expect(feed[0]).toMatchObject({
      type: "reasoning",
      content: "Надо поискать",
    });
    expect(feed[3]).toMatchObject({ type: "agent_event", kind: "compaction" });
    expect(feed[4]).toMatchObject({
      type: "text",
      content: "Вот что нашлось.",
    });

    live.push({ type: "done", message_id: "m-1", trace_id: null });
    live.close();
    await waitFor(async () => expect(await isStreaming()).toBe(false));
  });

  // Сторож тишины перезаводится **любым** пришедшим фреймом — иначе поток,
  // где сервер шлёт что-то, чего фронт ещё не знает, оборвётся по таймауту.
  it("перезаводит сторож тишины и на событии неизвестного типа", async () => {
    setAccessToken(fakeJwt());
    vi.useFakeTimers();
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const onError = vi.fn();
    const { result } = renderAgentStream({ onError });

    result.current.send("hi");
    await vi.advanceTimersByTimeAsync(10000);
    live.push({ type: "brand_new_event", whatever: 42 });
    // Ещё 10 с: без перезавода порог в 15 с был бы уже пройден.
    await vi.advanceTimersByTimeAsync(10000);
    expect(onError).not.toHaveBeenCalled();

    // Сторож при этом не разоружён — новая тишина его дожигает.
    await vi.advanceTimersByTimeAsync(6000);
    expect(onError).toHaveBeenCalledWith(CHAT_ID, "Превышено время ожидания");
  });

  // Снятие сторожа на терминальном событии: сервер, придержавший соединение
  // открытым после `done`, не имеет права превратить успешный ход в ошибку.
  it("снимает сторож тишины на терминальном событии, а не по концу чтения", async () => {
    setAccessToken(fakeJwt());
    vi.useFakeTimers();
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const onError = vi.fn();
    const onDone = vi.fn();
    const { result } = renderAgentStream({ onError, onDone });

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "готово" });
    live.push({ type: "done", message_id: "m-1", trace_id: null });
    await vi.waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));

    // Соединение всё ещё открыто, содержательных событий больше нет.
    await vi.advanceTimersByTimeAsync(30000);

    expect(onError).not.toHaveBeenCalled();
    live.close();
  });

  // Списки чатов инвалидируются на каждом терминальном событии, потому что
  // автозаголовок пишется в БД fire-and-forget и мог успеть записаться.
  it("рефетчит списки чатов и на терминальной ошибке", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([{ type: "error", detail: "модель упала" }]),
      ),
    );
    const onError = vi.fn();
    const { result, queryClient } = renderAgentStream({ onError });
    primeTitleCaches(queryClient);

    result.current.send("hi");

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(CHAT_ID, "модель упала"),
    );
    expect(
      queryClient.getQueryState(queryKeys.projects.chats(PROJECT_ID))
        ?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState(queryKeys.chats.recent)?.isInvalidated,
    ).toBe(true);
  });

  // Исключение из того же правила: на заблокированном вводе генерация
  // заголовка не запускается вовсе, поэтому список чатов проекта трогать
  // незачем (streaming.md § Уточнения → `title_updated`).
  it("не рефетчит список чатов проекта на блокировке, но обновляет сам чат", async () => {
    setAccessToken(fakeJwt());
    server.use(
      http.post(MESSAGES_URL, () =>
        streamResponse([{ type: "security_block" }]),
      ),
    );
    const onSecurityBlock = vi.fn();
    const { result, queryClient } = renderAgentStream({ onSecurityBlock });
    primeTitleCaches(queryClient);

    result.current.send("hi");

    await waitFor(() => expect(onSecurityBlock).toHaveBeenCalledTimes(1));
    expect(
      queryClient.getQueryState(queryKeys.projects.chats(PROJECT_ID))
        ?.isInvalidated,
    ).toBe(false);
    expect(
      queryClient.getQueryState(queryKeys.projects.chat(PROJECT_ID, CHAT_ID))
        ?.isInvalidated,
    ).toBe(true);
    expect(
      queryClient.getQueryState(queryKeys.chats.recent)?.isInvalidated,
    ).toBe(true);
  });

  it("закрывает стрим на блокировке — композер не остаётся с кнопкой отмены", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const onSecurityBlock = vi.fn();
    const { result } = renderAgentStream({ onSecurityBlock });

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "начало ответа" });
    await waitFor(async () =>
      expect(await streamedText()).toBe("начало ответа"),
    );

    live.push({ type: "security_block" });

    await waitFor(() => expect(onSecurityBlock).toHaveBeenCalledTimes(1));
    // Блокировка терминальна и для стрима: иначе заглушка видна дважды (своя в
    // живом регионе и приехавшая из истории), а ввод остаётся в режиме отмены.
    expect(await isStreaming()).toBe(false);
    live.close();
  });

  // Регрессия живого стенда: поток придерживают, накопленное приезжает разом —
  // и ход не доходит до `done` вовсе, а превращается в «Ошибка соединения»,
  // теряя ответ целиком. Причина в темпе чтений, а не в числе фрагментов:
  // готовые данные резолвят `reader.read()` микрозадачей, чтения идут вплотную,
  // каждое обновляет стор по sync-lane, и сторож вложенных обновлений React
  // (`NESTED_UPDATE_LIMIT = 50`) не обнуляется ни разу. Кейс подаёт бэклог
  // ровно так — каждый кадр отдельным куском тела — и требует, чтобы ход дошёл
  // до конца. Экран здесь обязателен: без подписчика ленты обновлений стора
  // никто не коммитит и цепочке не из чего собраться.
  it("доводит до конца ход, чей бэклог приехал одной пачкой", async () => {
    setAccessToken(fakeJwt());
    Element.prototype.scrollIntoView = vi.fn();
    // Порог сторожа — 50; 80 кадров дают запас против машины, а на коде без
    // уступки событийному циклу этого хватает с избытком (граница — 53-54).
    const backlog: unknown[] = [{ type: "stream_started" }];
    for (let i = 0; i < 80; i += 1) {
      backlog.push({ type: "text_chunk", content: `фрагмент ${i} ` });
    }
    backlog.push({ type: "done", message_id: "m1", trace_id: "t1" });
    server.use(http.post(MESSAGES_URL, () => streamResponse(backlog)));

    const onDone = vi.fn();
    const onError = vi.fn();
    const queryClient = createTestQueryClient();
    const wrapper = ({ children }: { children: ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);

    // Экран хода целиком: диспетчер плюс лента, подписанная на стор, — то же
    // сочетание, что живёт в `ChatThread`. Текст снимается по ходу: `done`
    // гасит стрим и стирает ленту раньше, чем колбэк доходит до теста.
    let streamedOnScreen = "";
    function Turn() {
      const feed = useStreamStore((s) => s.feed);
      const { send } = useAgentStream(PROJECT_ID, CHAT_ID, { onDone, onError });
      useEffect(() => {
        send("привет");
      }, [send]);
      useEffect(() => {
        const text = feed.reduce(
          (acc, item) => (item.type === "text" ? acc + item.content : acc),
          "",
        );
        if (text.length > streamedOnScreen.length) streamedOnScreen = text;
      }, [feed]);
      return createElement(MessageList, {
        messages: [],
        isStreaming: true,
        feed,
        projectId: PROJECT_ID,
        chatId: CHAT_ID,
        streamError: null,
        endNotice: null,
      });
    }

    render(createElement(Turn), { wrapper });

    // Ждём любого исхода хода, а не только успешного: иначе сломанный транспорт
    // краснит кейс молчанием по таймауту вместо своей настоящей причины.
    await waitFor(
      () =>
        expect(onDone.mock.calls.length + onError.mock.calls.length).toBe(1),
      { timeout: 10000 },
    );
    expect(onError).not.toHaveBeenCalled();
    expect(onDone).toHaveBeenCalledTimes(1);
    // Пачка доехала до ленты целиком, а не оборвалась на пороге сторожа.
    expect(streamedOnScreen).toContain("фрагмент 79");
  }, 15000);
});

/**
 * Владелец хода: чат, зафиксированный в момент `send()`. Пользователь волен уйти
 * в соседний чат посреди хода — компонент при этом не перемонтируется, поэтому
 * колбэк, разбирающий терминальное событие, обязан узнать чат-владельца из
 * контракта, а не из текущего рендера. Кейсы ниже проверяют это на каждой
 * ветке, включая те, где SSE-события не было вовсе, и на двух одновременно
 * живых ходах — том, ради которого трек и заведён.
 */
describe("useAgentStream: владелец хода при переключении чата", () => {
  it("отдаёт onDone владельца хода, а не чата, открытого к моменту события", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const onDone = vi.fn();
    const { result, switchTo } = renderSwitchableStream({ onDone });

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "идёт ответ" });
    await waitFor(async () => expect(await streamedText()).toBe("идёт ответ"));

    switchTo(OTHER_CHAT_ID);
    live.push({ type: "done", message_id: "m-a", trace_id: "t-a" });
    live.close();

    await waitFor(() =>
      expect(onDone).toHaveBeenCalledWith({
        chatId: CHAT_ID,
        messageId: "m-a",
        traceId: "t-a",
      }),
    );
  });

  it("отдаёт onError владельца хода на событии error после переключения", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const onError = vi.fn();
    const { result, switchTo } = renderSwitchableStream({ onError });

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "идёт ответ" });
    await waitFor(async () => expect(await streamedText()).toBe("идёт ответ"));

    switchTo(OTHER_CHAT_ID);
    live.push({ type: "error", detail: "модель упала" });
    live.close();

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(CHAT_ID, "модель упала"),
    );
  });

  it("отдаёт onCancelled владельца хода после переключения", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const onCancelled = vi.fn();
    const { result, switchTo } = renderSwitchableStream({ onCancelled });

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "идёт ответ" });
    await waitFor(async () => expect(await streamedText()).toBe("идёт ответ"));

    switchTo(OTHER_CHAT_ID);
    live.push({ type: "cancelled" });
    live.close();

    await waitFor(() => expect(onCancelled).toHaveBeenCalledWith(CHAT_ID));
  });

  it("отдаёт onSecurityBlock владельца хода после переключения", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const onSecurityBlock = vi.fn();
    const { result, switchTo } = renderSwitchableStream({ onSecurityBlock });

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "идёт ответ" });
    await waitFor(async () => expect(await streamedText()).toBe("идёт ответ"));

    switchTo(OTHER_CHAT_ID);
    live.push({ type: "security_block" });
    live.close();

    await waitFor(() => expect(onSecurityBlock).toHaveBeenCalledWith(CHAT_ID));
  });

  // Ветки без единого SSE-события — там владельца неоткуда взять «из потока»,
  // и именно на них его легче всего потерять.
  it("несёт владельца в таймауте сторожа тишины", async () => {
    setAccessToken(fakeJwt());
    vi.useFakeTimers();
    // Сервер не отвечает вовсе — событий не будет ни одного.
    server.use(http.post(MESSAGES_URL, () => delay("infinite")));
    const onError = vi.fn();
    const { result, switchTo } = renderSwitchableStream({ onError });

    result.current.send("hi");
    switchTo(OTHER_CHAT_ID);
    await vi.advanceTimersByTimeAsync(16000);

    expect(onError).toHaveBeenCalledWith(CHAT_ID, "Превышено время ожидания");
  });

  it("несёт владельца в не-ok ответе на отправку", async () => {
    setAccessToken(fakeJwt());
    const { held, release } = heldResponse();
    server.use(
      http.post(MESSAGES_URL, async () => {
        await held;
        return HttpResponse.json(
          { detail: "Доступ запрещён" },
          { status: 403 },
        );
      }),
    );
    const onError = vi.fn();
    const { result, switchTo } = renderSwitchableStream({ onError });

    result.current.send("hi");
    switchTo(OTHER_CHAT_ID);
    release();

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(CHAT_ID, "Доступ запрещён"),
    );
  });

  it("несёт владельца в обрыве потока без терминального события", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const onError = vi.fn();
    const { result, switchTo } = renderSwitchableStream({ onError });

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "недописанный ответ" });
    await waitFor(async () =>
      expect(await streamedText()).toBe("недописанный ответ"),
    );

    switchTo(OTHER_CHAT_ID);
    live.close();

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(CHAT_ID, "Соединение прервано"),
    );
  });

  // Уход с экрана — единственный неохраняемый путь: cleanup зовёт `reset()`, а
  // не гашение по чату. Владельцем к этому моменту может быть уже покинутый
  // чат, и скоупленное гашение (`endStream` текущего чата) стало бы no-op —
  // стор остался бы с `isStreaming: true` от чужого хода на весь остаток
  // сессии, с композером в режиме отмены на всех экранах.
  it("сбрасывает стор на unmount после ухода в соседний чат", async () => {
    setAccessToken(fakeJwt());
    const live = liveStream();
    server.use(http.post(MESSAGES_URL, () => live.response));
    const { result, switchTo, unmount } = renderSwitchableStream();

    result.current.send("hi");
    live.push({ type: "text_chunk", content: "идёт ответ" });
    await waitFor(async () => expect(await streamedText()).toBe("идёт ответ"));

    // Пользователь в соседнем чате, а стором по-прежнему владеет ход в A —
    // ровно то расхождение, которого нет у одночатового кейса на unmount.
    switchTo(OTHER_CHAT_ID);
    expect(streamOwner()).toBe(CHAT_ID);

    unmount();

    expect(await isStreaming()).toBe(false);
    expect(streamOwner()).toBeNull();
    expect(await streamedFeed()).toEqual([]);
  });

  it("несёт владельца в исключении транспорта", async () => {
    setAccessToken(fakeJwt());
    const { held, release } = heldResponse();
    server.use(
      http.post(MESSAGES_URL, async () => {
        await held;
        return HttpResponse.error();
      }),
    );
    const onError = vi.fn();
    const { result, switchTo } = renderSwitchableStream({ onError });

    result.current.send("hi");
    switchTo(OTHER_CHAT_ID);
    release();

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith(CHAT_ID, "Ошибка соединения"),
    );
  });
});

/**
 * Два хода разом. Поток чата A при переключении не абортится (решение брифа: он
 * дотекает в никуда, результат приезжает рефетчем по `done`), поэтому пока в
 * чате B идёт свой ход, поток A продолжает слать события и рано или поздно
 * пришлёт терминал. Ни то, ни другое не имеет права коснуться живого стрима B —
 * это и есть класс бага, ради которого заведён трек.
 */
describe("useAgentStream: догорающий ход соседнего чата", () => {
  /** Ход в чате A начат и жив; поверх него в чате B начат свой. Стором владеет B. */
  async function startTwoTurns(options?: Parameters<typeof useAgentStream>[2]) {
    const liveA = liveStream();
    const liveB = liveStream();
    server.use(
      http.post(MESSAGES_URL, () => liveA.response),
      http.post(OTHER_MESSAGES_URL, () => liveB.response),
    );
    const rendered = renderSwitchableStream(options);

    rendered.result.current.send("вопрос в A");
    liveA.push({ type: "text_chunk", content: "ответ A" });
    await waitFor(async () => expect(await streamedText()).toBe("ответ A"));

    rendered.switchTo(OTHER_CHAT_ID);
    rendered.result.current.send("вопрос в B");
    liveB.push({ type: "text_chunk", content: "ответ B" });
    await waitFor(async () => expect(await streamedText()).toBe("ответ B"));
    expect(streamOwner()).toBe(OTHER_CHAT_ID);

    return { liveA, liveB, ...rendered };
  }

  it("не пишет события догорающего потока в ленту нового чата", async () => {
    setAccessToken(fakeJwt());
    const onDone = vi.fn();
    const { liveA } = await startTwoTurns({ onDone });

    liveA.push({ type: "text_chunk", content: " и ещё кусок" });
    liveA.push({
      type: "tool_call_started",
      call_id: "call-a",
      tool: "firecrawl_search",
    });
    // Терминал того же потока — точка синхронизации: кадры одного потока
    // разбираются по порядку, значит к моменту `onDone` события выше уже
    // прошли через стор.
    liveA.push({ type: "done", message_id: "m-a", trace_id: null });
    liveA.close();
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));

    // Владелец в колбэке — чат A, хотя открыт (и владеет стором) чат B. Именно
    // это отличает контракт «владелец из замыкания `send()`» от ссылки на чат
    // идущего потока: при живом ходе в B такая ссылка указывала бы на B.
    expect(onDone).toHaveBeenCalledWith({
      chatId: CHAT_ID,
      messageId: "m-a",
      traceId: null,
    });
    expect(await streamedText()).toBe("ответ B");
    expect(await streamedFeed()).toEqual([
      { id: "text-0", type: "text", content: "ответ B" },
    ]);
    // Ход B закрывать нечем и незачем: его обрывает cleanup хука на unmount —
    // тем же путём, что и уход пользователя со страницы.
  });

  it("не гасит терминалом догорающего потока живой стрим нового чата", async () => {
    setAccessToken(fakeJwt());
    const onDone = vi.fn();
    const { liveA, liveB } = await startTwoTurns({ onDone });

    liveA.push({ type: "done", message_id: "m-a", trace_id: null });
    liveA.close();
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));

    // Ход в B продолжается: композер остаётся в режиме отмены, живой регион
    // рисует ленту — до собственного терминала B.
    expect(await isStreaming()).toBe(true);
    expect(streamOwner()).toBe(OTHER_CHAT_ID);

    liveB.push({ type: "done", message_id: "m-b", trace_id: null });
    liveB.close();
    await waitFor(async () => expect(await isStreaming()).toBe(false));
  });
});
