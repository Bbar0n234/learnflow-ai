import { useParams } from "react-router";
import { ChatThread } from "./ChatThread";
import { ChatDraft } from "./ChatDraft";

// Thin route dispatcher: `/projects/:id/chats/new` has no `:cid` segment, so
// `cid` is present here iff the chat already exists in the DB. The two
// branches are separate components (not a single component with conditional
// hooks) because `ChatThread` calls `useChat`/`useAgentStream`/`useStudio`
// which require a real `cid` and would violate Rules of Hooks if gated by a
// runtime condition inside one component (§ Draft-режим композера, T2.6).
export function ChatView() {
  const { cid } = useParams();
  return cid ? <ChatThread /> : <ChatDraft />;
}
