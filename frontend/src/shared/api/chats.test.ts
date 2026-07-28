import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { server } from "@/test/msw/server";
import { createTestQueryClient } from "@/test/test-utils";

import {
  CHAT_TITLE_MAX_LENGTH,
  DEFAULT_CHAT_TITLE,
  useCreateChat,
  useDeleteChat,
  useUpdateChat,
  type Chat,
  type ChatDetail,
  type RecentChat,
} from "./chats";
import { queryKeys } from "./query-keys";

// Integration (feat-002, T2.1): the chats data layer. Chat creation carries no
// body at all (the user never names a chat — design-brief § Контракты), while
// rename/delete are pessimistic mutations whose cache fan-out is deliberately
// narrow: the chats list and recents are invalidated with `exact: true`, and the
// open chat's detail is patched in place instead of refetched, so a mutation
// firing mid-stream can never re-pull a chat whose optimistic user message is
// still local (§ Доставка title на фронт). Network is MSW.

const PROJECT_ID = "p1";
const CHAT_ID = "c1";
const CHATS_URL = `/api/projects/${PROJECT_ID}/chats`;
const CHAT_URL = `${CHATS_URL}/${CHAT_ID}`;

const LIST_KEY = queryKeys.projects.chats(PROJECT_ID);
const DETAIL_KEY = queryKeys.projects.chat(PROJECT_ID, CHAT_ID);
const RECENT_KEY = queryKeys.chats.recent;

function chat(over: Partial<Chat> = {}): Chat {
  return {
    thread_id: CHAT_ID,
    title: DEFAULT_CHAT_TITLE,
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-01T10:00:00Z",
    security_blocked: false,
    ...over,
  };
}

function recentChat(over: Partial<RecentChat> = {}): RecentChat {
  return {
    thread_id: CHAT_ID,
    title: DEFAULT_CHAT_TITLE,
    project_id: PROJECT_ID,
    project_name: "Проект",
    updated_at: "2026-07-01T10:00:00Z",
    security_blocked: false,
    ...over,
  };
}

function detail(over: Partial<ChatDetail> = {}): ChatDetail {
  return {
    thread_id: CHAT_ID,
    title: DEFAULT_CHAT_TITLE,
    security_blocked: false,
    messages: [],
    ...over,
  };
}

/** Renders a mutation hook against a fresh client whose caches are pre-primed. */
function renderChatMutation<T>(useHook: () => T) {
  const queryClient = createTestQueryClient();
  queryClient.setQueryData(LIST_KEY, {
    items: [chat()],
    total: 1,
    limit: 200,
    offset: 0,
  });
  queryClient.setQueryData(RECENT_KEY, {
    items: [recentChat()],
    total: 1,
    limit: 10,
    offset: 0,
  });
  queryClient.setQueryData(DETAIL_KEY, detail());
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  const { result } = renderHook(useHook, { wrapper });
  return { result, queryClient };
}

describe("chat domain constants", () => {
  it("expose the placeholder title and the rename length limit agreed with the server", () => {
    expect(DEFAULT_CHAT_TITLE).toBe("Новый чат");
    expect(CHAT_TITLE_MAX_LENGTH).toBe(100);
  });
});

describe("useCreateChat", () => {
  it("creates a chat without sending any body and returns the new thread", async () => {
    let sentBody: string | null = null;
    server.use(
      http.post(CHATS_URL, async ({ request }) => {
        sentBody = await request.text();
        return HttpResponse.json(chat({ thread_id: "c-new" }), { status: 201 });
      }),
    );
    const { result } = renderChatMutation(useCreateChat);

    result.current.mutate(PROJECT_ID);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.thread_id).toBe("c-new");
    // The user names no chat anywhere: the request carries no title payload.
    expect(sentBody).toBe("");
  });

  it("refreshes the chats list and recents without touching the open chat's detail", async () => {
    server.use(
      http.post(CHATS_URL, () =>
        HttpResponse.json(chat({ thread_id: "c-new" }), { status: 201 }),
      ),
    );
    const { result, queryClient } = renderChatMutation(useCreateChat);

    result.current.mutate(PROJECT_ID);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryState(LIST_KEY)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(RECENT_KEY)?.isInvalidated).toBe(true);
    // `exact: true`: the list key is a prefix of the detail key — a prefix
    // invalidation would refetch a chat that may be streaming right now.
    expect(queryClient.getQueryState(DETAIL_KEY)?.isInvalidated).toBe(false);
  });

  it("surfaces a failed creation without invalidating anything", async () => {
    server.use(
      http.post(CHATS_URL, () =>
        HttpResponse.json({ detail: "Проект недоступен" }, { status: 403 }),
      ),
    );
    const { result, queryClient } = renderChatMutation(useCreateChat);

    result.current.mutate(PROJECT_ID);

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(queryClient.getQueryState(LIST_KEY)?.isInvalidated).toBe(false);
    expect(queryClient.getQueryState(RECENT_KEY)?.isInvalidated).toBe(false);
  });
});

describe("useUpdateChat", () => {
  it("renames the chat through PUT and patches the open detail in place", async () => {
    let sentBody: unknown = null;
    server.use(
      http.put(CHAT_URL, async ({ request }) => {
        sentBody = await request.json();
        return HttpResponse.json(chat({ title: "Производные функции" }));
      }),
    );
    const { result, queryClient } = renderChatMutation(useUpdateChat);

    result.current.mutate({
      projectId: PROJECT_ID,
      chatId: CHAT_ID,
      data: { title: "Производные функции" },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(sentBody).toEqual({ title: "Производные функции" });
    expect(queryClient.getQueryData<ChatDetail>(DETAIL_KEY)?.title).toBe(
      "Производные функции",
    );
  });

  it("invalidates the list and recents but never the detail of the open chat", async () => {
    server.use(
      http.put(CHAT_URL, () => HttpResponse.json(chat({ title: "Новое имя" }))),
    );
    const { result, queryClient } = renderChatMutation(useUpdateChat);

    result.current.mutate({
      projectId: PROJECT_ID,
      chatId: CHAT_ID,
      data: { title: "Новое имя" },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryState(LIST_KEY)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(RECENT_KEY)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(DETAIL_KEY)?.isInvalidated).toBe(false);
  });

  it("takes the title the server returned, not the one the caller sent", async () => {
    // The server is the source of truth for the stored value (trim/normalize).
    server.use(
      http.put(CHAT_URL, () =>
        HttpResponse.json(chat({ title: "Нормализовано сервером" })),
      ),
    );
    const { result, queryClient } = renderChatMutation(useUpdateChat);

    result.current.mutate({
      projectId: PROJECT_ID,
      chatId: CHAT_ID,
      data: { title: "  что-то своё  " },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(queryClient.getQueryData<ChatDetail>(DETAIL_KEY)?.title).toBe(
      "Нормализовано сервером",
    );
  });

  it("surfaces a failed rename and leaves the cached title untouched", async () => {
    server.use(
      http.put(CHAT_URL, () =>
        HttpResponse.json(
          { detail: "Название слишком длинное" },
          { status: 422 },
        ),
      ),
    );
    const { result, queryClient } = renderChatMutation(useUpdateChat);

    result.current.mutate({
      projectId: PROJECT_ID,
      chatId: CHAT_ID,
      data: { title: "x".repeat(CHAT_TITLE_MAX_LENGTH + 1) },
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(queryClient.getQueryData<ChatDetail>(DETAIL_KEY)?.title).toBe(
      DEFAULT_CHAT_TITLE,
    );
    expect(queryClient.getQueryState(LIST_KEY)?.isInvalidated).toBe(false);
  });
});

describe("useDeleteChat", () => {
  it("deletes the chat and refreshes the list and recents", async () => {
    let deleted = false;
    server.use(
      http.delete(CHAT_URL, () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { result, queryClient } = renderChatMutation(useDeleteChat);

    result.current.mutate({ projectId: PROJECT_ID, chatId: CHAT_ID });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(deleted).toBe(true);
    expect(queryClient.getQueryState(LIST_KEY)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(RECENT_KEY)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(DETAIL_KEY)?.isInvalidated).toBe(false);
  });

  it("surfaces a failed delete without invalidating anything", async () => {
    server.use(
      http.delete(CHAT_URL, () =>
        HttpResponse.json({ detail: "Ошибка сервера" }, { status: 500 }),
      ),
    );
    const { result, queryClient } = renderChatMutation(useDeleteChat);

    result.current.mutate({ projectId: PROJECT_ID, chatId: CHAT_ID });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(queryClient.getQueryState(LIST_KEY)?.isInvalidated).toBe(false);
    expect(queryClient.getQueryState(RECENT_KEY)?.isInvalidated).toBe(false);
  });
});
