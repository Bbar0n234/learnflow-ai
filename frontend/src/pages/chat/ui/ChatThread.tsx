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
  // Три транзиентных состояния экрана — оптимистичная копия отправленного
  // сообщения, ошибка потока и причина остановки хода — живут до следующей
  // отправки и все скоуплены чатом, как `isStreaming` выше. Причина одна:
  // переключение чата этот компонент не перемонтирует (`chats/:cid` рендерит
  // один и тот же `ChatThread` без `key`), поэтому нескоупленное состояние
  // уезжает в соседний чат — там всплывали бы чужое сообщение, чужая красная
  // плашка и сообщение об остановке чужого хода, висящие до первой отправки.
  const [localMessages, setLocalMessages] = useState<{
    chatId: string;
    messages: Message[];
  } | null>(null);
  const [streamError, setStreamError] = useState<{
    chatId: string;
    detail: string;
  } | null>(null);
  // В историю причина остановки не сохраняется — она транзиентна ровно как
  // `streamError`.
  const [endNotice, setEndNotice] = useState<{
    chatId: string;
    reason: StreamEndReason;
  } | null>(null);

  const studio = useStudio();

  // Терминальные колбэки снимают оптимистичную копию безусловно, без сверки с
  // текущим `cid`: копия принадлежит закончившемуся ходу, и его сообщение уже
  // приехало с сервера — держать её дальше значило бы задваивать сообщение в
  // том чате, где ход шёл, независимо от того, на каком экране пользователь.
  const handleDone = useCallback(() => {
    setLocalMessages(null);
  }, []);

  const handleSecurityBlock = useCallback(() => {
    // Server-side already persisted the user message + redacted placeholder
    // and we invalidated the chat query — drop the optimistic local copy
    // to avoid duplicates after refetch.
    setLocalMessages(null);
    // Заглушку заблокированного хода показывает история; карточка объясняет,
    // почему ход схлопнулся и почему ввод заблокирован.
    setEndNotice({ chatId: cid!, reason: "blocked" });
  }, [cid]);

  const handleCancelled = useCallback(() => {
    // Хук уже инвалидировал detail: отменённый ход приезжает из истории вместе
    // с незавершёнными вызовами. Оптимистичную копию снимаем по той же причине,
    // что и на `done`, — иначе после рефетча она задвоится.
    setLocalMessages(null);
    setEndNotice({ chatId: cid!, reason: "cancelled" });
  }, [cid]);

  const { send, cancel } = useAgentStream(id!, cid!, {
    onDone: handleDone,
    onError: (detail) => setStreamError({ chatId: cid!, detail }),
    onSecurityBlock: handleSecurityBlock,
    onCancelled: handleCancelled,
  });

  const feed = useStreamStore((s) => s.feed);

  const handleSend = useCallback(
    (content: string) => {
      const chatId = cid!;
      setStreamError(null);
      setEndNotice(null);
      const message: Message = {
        id: crypto.randomUUID(),
        role: "user",
        content,
        created_at: new Date().toISOString(),
        artifacts: [],
      };
      // Копия принадлежит чату, в который её отправили. Копится она только в
      // пределах одного чата: отправка в другой начинает список заново — двух
      // чатов с неотвеченными сообщениями это состояние не держит, и делать вид,
      // что держит, не надо.
      setLocalMessages((prev) =>
        prev !== null && prev.chatId === chatId
          ? { chatId, messages: [...prev.messages, message] }
          : { chatId, messages: [message] },
      );
      send(content);
    },
    [cid, send],
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

  // Всё транзиентное принадлежит тому чату, в котором ход шёл: в соседнем не
  // показываем ничего из этого, даже пока состояние ещё не сменилось.
  const ownLocalMessages =
    localMessages !== null && localMessages.chatId === cid
      ? localMessages.messages
      : [];
  const ownStreamError =
    streamError !== null && streamError.chatId === cid
      ? streamError.detail
      : null;
  const ownEndNotice =
    endNotice !== null && endNotice.chatId === cid ? endNotice.reason : null;
  const allMessages = [...(data?.messages ?? []), ...ownLocalMessages];

  return (
    <div className={cn("flex h-full", studio.open && "studio-open")}>
      {/* Chat column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <ChatHeader studioOpen={studio.open} onToggleStudio={studio.toggle} />
        <MessageList
          messages={allMessages}
          isStreaming={isStreaming}
          feed={feed}
          projectId={id!}
          chatId={cid!}
          streamError={ownStreamError}
          endNotice={ownEndNotice}
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
