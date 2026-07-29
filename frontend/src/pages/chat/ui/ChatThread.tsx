import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router";
import { useChat } from "@/shared/api/chats";
import { useAgentStream } from "../model/useAgentStream";
import { useStreamStore } from "@/stores/stream-store";
import { useStudio } from "../model/useStudio";
import { cn } from "@/shared/lib/utils";
import { ChatHeader } from "./ChatHeader";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import type { StreamEndReason } from "./StreamEndNotice";
import { StudioPanel } from "./StudioPanel";
import { SphereLens } from "./SphereLens";
import { SHOW_GROUP_B_STUBS } from "@/shared/config/feature-flags";
import type { Message } from "@/shared/api/chats";

// Router state carried by both entry paths (project page field, composer
// draft) — set by the caller right before navigating to this chat, cleared
// here immediately once the initial message has been dispatched (§ Создание
// чата и первое сообщение design-brief'а).
interface ChatEntryState {
  initialMessage?: string;
}

// The chat that already exists in the DB — `useChat`/`useAgentStream`/
// `useStudio` all assume a real `cid`. The draft branch (`/chats/new`,
// `ChatDraft`) has no `thread_id` yet, so it lives in a separate component:
// Rules of Hooks forbid making these hooks conditional inside one component.
export function ChatThread() {
  const { id, cid } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const isStreaming = useStreamStore(
    (s) => s.streamingChatId === cid && s.isStreaming,
  );
  const { data, isLoading, isError } = useChat(id, cid, {
    refetchOnWindowFocus: !isStreaming,
  });
  const [localMessages, setLocalMessages] = useState<Message[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);
  // Чем закончился ход, если он закончился не ответом. В историю причина
  // остановки не сохраняется — это транзиентное состояние экрана, живущее до
  // следующей отправки, ровно как `streamError`.
  const [endNotice, setEndNotice] = useState<StreamEndReason | null>(null);

  const studio = useStudio();

  const handleDone = useCallback(() => {
    setLocalMessages([]);
  }, []);

  const handleSecurityBlock = useCallback(() => {
    // Server-side already persisted the user message + redacted placeholder
    // and we invalidated the chat query — drop the optimistic local copy
    // to avoid duplicates after refetch.
    setLocalMessages([]);
    // Заглушку заблокированного хода показывает история; карточка объясняет,
    // почему ход схлопнулся и почему ввод заблокирован.
    setEndNotice("blocked");
  }, []);

  const handleCancelled = useCallback(() => {
    // Хук уже инвалидировал detail: отменённый ход приезжает из истории вместе
    // с незавершёнными вызовами. Оптимистичную копию снимаем по той же причине,
    // что и на `done`, — иначе после рефетча она задвоится.
    setLocalMessages([]);
    setEndNotice("cancelled");
  }, []);

  const { send, cancel } = useAgentStream(id!, cid!, {
    onDone: handleDone,
    onError: (detail) => setStreamError(detail),
    onSecurityBlock: handleSecurityBlock,
    onCancelled: handleCancelled,
  });

  const feed = useStreamStore((s) => s.feed);
  const streamingArtifacts = useStreamStore((s) => s.streamingArtifacts);

  const handleSend = useCallback(
    (content: string) => {
      setStreamError(null);
      setEndNotice(null);
      const message: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        created_at: new Date().toISOString(),
        artifacts: [],
      };
      setLocalMessages((prev) => [...prev, message]);
      send(content);
    },
    [send],
  );

  // One-shot auto-send of the message queued by the entry path (project page
  // field or composer draft): the chat was just created and is guaranteed
  // empty, so we don't wait for `useChat` to load.
  //
  // Отправка не выполняется прямо в теле эффекта, а планируется задачей и
  // снимается в cleanup. Причина — двойной прогон эффектов в dev (React Strict
  // Mode гоняет их как mount → cleanup → mount): синхронный `send()` с первого
  // mount успевал завести `AbortController`, но уходил в `await
  // ensureFreshToken()` и не успевал дойти до `fetch`, а cleanup-хук
  // `useAgentStream` (тот, что рвёт стрим при уходе со страницы) тут же звал
  // `abort()` — запрос отправлялся с уже прерванным сигналом и не покидал
  // браузер, тогда как повторный mount упирался в ref-гвард и не переотправлял.
  // Отложенный запуск переживает этот цикл: таймер первого mount снимает его
  // собственный cleanup, отправку делает единственный таймер второго mount —
  // когда фаза размонтирования уже позади и abort'а не будет. В prod цикл
  // единственный, поведение то же. Abort при настоящем уходе со страницы не
  // тронут: там повторного mount нет.
  //
  // Однократность держат `initialMessageRef` (флаг «для этого чата уже
  // отправлено») и затирание router state (`state: null`) сразу после запуска:
  // refresh и back/forward на этом URL не переотправляют сообщение.
  const initialMessageRef = useRef<string | null>(null);
  useEffect(() => {
    const initialMessage = (location.state as ChatEntryState | null)
      ?.initialMessage;
    if (!initialMessage || !cid) return;
    if (initialMessageRef.current === cid) return;
    const dispatch = setTimeout(() => {
      initialMessageRef.current = cid;
      handleSend(initialMessage);
      navigate(location.pathname, { replace: true, state: null });
    }, 0);
    return () => clearTimeout(dispatch);
  }, [cid, location.pathname, location.state, navigate, handleSend]);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        Loading chat...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex h-full items-center justify-center text-destructive">
        Не удалось загрузить чат.
      </div>
    );
  }

  const allMessages = [...(data?.messages ?? []), ...localMessages];

  return (
    <div className={cn("flex h-full", studio.open && "studio-open")}>
      {/* Chat column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <ChatHeader studioOpen={studio.open} onToggleStudio={studio.toggle} />
        <MessageList
          messages={allMessages}
          isStreaming={isStreaming}
          feed={feed}
          streamingArtifacts={streamingArtifacts}
          projectId={id!}
          chatId={cid!}
          streamError={streamError}
          endNotice={endNotice}
        />
        <ChatInput
          onSend={handleSend}
          isStreaming={isStreaming}
          onCancel={cancel}
          disabled={data?.security_blocked}
          placeholder={
            data?.security_blocked
              ? "Чат заблокирован системой безопасности"
              : undefined
          }
        />
      </div>

      {/* Studio panel dock (group B stub) */}
      {SHOW_GROUP_B_STUBS && studio.open && (
        <StudioPanel
          studio={studio}
          onOpenLens={() => studio.setLensOpen(true)}
        />
      )}

      {/* Overlay lens (group B stub) */}
      {SHOW_GROUP_B_STUBS && (
        <SphereLens
          open={studio.lensOpen}
          onClose={() => studio.setLensOpen(false)}
        />
      )}
    </div>
  );
}
