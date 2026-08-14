import { useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Paperclip, SendHorizontal } from "lucide-react";
import { Textarea } from "@/shared/ui/textarea";
import { Button } from "@/shared/ui/button";
import { Illustration } from "@/shared/ui/Illustration";
import { TypedTitle } from "@/shared/ui/TypedTitle";
import { Skeleton } from "@/shared/ui/skeleton";
import { ErrorCard } from "@/shared/ui/StateScreen";
import { AttachmentChip } from "@/shared/ui/AttachmentChip";
import { DragOverlay } from "@/shared/ui/DragOverlay";
import { DEFAULT_CHAT_TITLE, useChats } from "@/shared/api/chats";
import { useCreateChat } from "@/shared/api/chats";
import { uploadFile } from "@/shared/api/uploads";
import { SHOW_GROUP_B_STUBS } from "@/shared/config/feature-flags";
import { ChatActions } from "@/features/chat-actions";
import { getApiErrorMessage } from "@/shared/lib/api-error";
import { logger } from "@/shared/lib/logger";
import { useComposerAttachments } from "@/shared/lib/use-composer-attachments";
import { useFileDrop } from "@/shared/lib/use-file-drop";

export function ChatList() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, isError, refetch } = useChats(id);
  const createChat = useCreateChat();
  const [newChatText, setNewChatText] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  // Идёт upload вложений + создание чата — тот же смысл, что `busy` в
  // `ChatInput.tsx` (T2.8): окно между кликом и вызовом `send`, которое
  // `createChat.isPending` в одиночку не покрывает (он про сам `POST /chats`,
  // а не про upload перед ним).
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // Успех уводит со страницы (навигация размонтирует список), поэтому
  // `clear()` хука здесь не нужен — только `attachments`/`addFiles`/
  // `removeAttachment` для рендера и ✕.
  const { attachments, addFiles, removeAttachment } = useComposerAttachments();
  const { isDragging, dragHandlers } = useFileDrop(addFiles);

  const trimmed = newChatText.trim();
  const canCreate = (trimmed.length > 0 || attachments.length > 0) && !busy;

  // Скрепка есть и в поле первого сообщения проекта (решение архитектора,
  // T2.8 OQ-6 — «лекция №1» начинается именно отсюда): та же схема, что в
  // `ChatDraft.tsx` — upload в проект до `createChat`, готовые пути едут в
  // router state создающегося чата.
  async function handleCreate() {
    if (!canCreate || !id) return;
    setCreateError(null);
    setBusy(true);
    try {
      // Пары «файл → загруженный путь» держим вместе (не индексируем два
      // параллельных массива по `i`) — `noUncheckedIndexedAccess` иначе
      // типизировал бы `files[i]` как возможный `undefined`.
      const uploaded = await Promise.all(
        attachments.map(async ({ file }) => ({
          file,
          result: await uploadFile(id, file),
        })),
      );
      const uploadedAttachments = uploaded.map(({ file, result }) => ({
        path: result.path,
        title: file.name,
      }));
      const created = await createChat.mutateAsync(id);
      navigate(`/projects/${id}/chats/${created.thread_id}`, {
        replace: true,
        state: { initialMessage: trimmed, attachments: uploadedAttachments },
      });
      // Успех уводит со страницы (навигация размонтирует список) — `busy` и
      // локальные чипы можно не сбрасывать, компонента уже не будет.
    } catch (err) {
      logger.error("[Create chat error]", err);
      setCreateError(getApiErrorMessage(err));
      setBusy(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleCreate();
    }
  }

  function handleFileInputChange(e: ChangeEvent<HTMLInputElement>) {
    if (e.target.files) addFiles(e.target.files);
    e.target.value = "";
  }

  return (
    <div className="h-full overflow-auto p-6">
      {/* First-message input — creates the chat and opens it with the message queued (handoff screen 9) */}
      <div className="mb-6">
        <div
          className="relative rounded-xl border border-border bg-card p-3"
          style={{ boxShadow: "var(--shadow-input)" }}
          {...dragHandlers}
        >
          {isDragging && <DragOverlay />}
          {attachments.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-1.5">
              {attachments.map((a) => (
                <AttachmentChip
                  key={a.id}
                  name={a.file.name}
                  size={a.file.size}
                  uploading={busy}
                  onRemove={() => removeAttachment(a.id)}
                />
              ))}
            </div>
          )}
          <Textarea
            value={newChatText}
            onChange={(e) => {
              setNewChatText(e.target.value);
              setCreateError(null);
            }}
            onKeyDown={handleKeyDown}
            placeholder="Спросите о чём угодно — начнётся новый чат…"
            disabled={busy}
            className="min-h-[52px] resize-none border-0 bg-transparent text-sm focus-visible:ring-0"
          />
          <div className="mt-2 flex items-center justify-between">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={busy}
              aria-label="Прикрепить файл"
              title="Прикрепить файл"
              className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-40"
            >
              <Paperclip className="h-4 w-4" />
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              hidden
              onChange={handleFileInputChange}
            />
            <Button
              size="icon"
              aria-label="Отправить"
              onClick={() => void handleCreate()}
              disabled={!canCreate}
              className="h-[34px] w-[34px] rounded-full"
            >
              <SendHorizontal className="h-4 w-4" />
            </Button>
          </div>
        </div>
        {createError && (
          <p className="mt-2 text-sm text-destructive">{createError}</p>
        )}
      </div>

      {/* Chat list */}
      {isLoading && (
        <div className="flex flex-col gap-0.5">
          <div className="flex flex-col gap-2 rounded-[var(--radius)] p-3">
            <Skeleton className="h-3.5 w-[46%]" />
            <Skeleton className="mt-[7px] h-2.5 w-[68%]" />
            <div className="mt-[9px] flex items-center gap-2">
              <Skeleton className="h-4 w-16 rounded-full" />
              <Skeleton className="mt-[3px] h-2.5 w-[34px]" />
            </div>
          </div>
          <div className="flex flex-col gap-2 rounded-[var(--radius)] p-3">
            <Skeleton className="h-3.5 w-[58%]" />
            <Skeleton className="mt-[7px] h-2.5 w-[44%]" />
            <div className="mt-[9px] flex items-center gap-2">
              <Skeleton className="h-4 w-[52px] rounded-full" />
              <Skeleton className="mt-[3px] h-2.5 w-[34px]" />
            </div>
          </div>
        </div>
      )}
      {isError && (
        <ErrorCard
          message="Не удалось загрузить чаты."
          onRetry={() => void refetch()}
        />
      )}
      {data && data.items.length === 0 && (
        <div className="flex flex-col items-center gap-4 py-8">
          <Illustration
            scene="empty-chats"
            alt="Нет чатов"
            className="w-full max-w-[280px]"
          />
          <p className="text-sm text-muted-foreground">
            Нет чатов. Начните с первого сообщения выше.
          </p>
        </div>
      )}
      {data && data.items.length > 0 && (
        <div className="flex flex-col gap-0.5">
          {data.items.map((chat, i) => (
            <div
              key={chat.thread_id}
              className="group/card relative flex items-start"
            >
              <Link
                to={`/projects/${id}/chats/${chat.thread_id}`}
                className="flex min-w-0 flex-1 items-start rounded-lg px-3 py-3 transition-colors hover:bg-muted"
              >
                <div className="min-w-0 flex-1">
                  <TypedTitle
                    as="p"
                    text={chat.title}
                    animateFrom={DEFAULT_CHAT_TITLE}
                    className="truncate font-serif text-sm font-semibold text-foreground"
                  />
                  <p className="mt-0.5 truncate text-xs text-muted-foreground">
                    Нет превью
                  </p>
                  <div className="mt-1.5 flex items-center gap-2">
                    {/* Stub contribution chips — visual only, no backend contract (group B stub) */}
                    {SHOW_GROUP_B_STUBS && i % 2 === 0 && (
                      <span className="rounded-full bg-secondary px-2 text-[10px] leading-5 text-secondary-foreground">
                        {(i + 1) * 2} артефакта
                      </span>
                    )}
                    {SHOW_GROUP_B_STUBS && i % 3 !== 2 && (
                      <span className="rounded-full bg-secondary px-2 text-[10px] leading-5 text-secondary-foreground">
                        +{(i + 1) * 3} в сферу
                      </span>
                    )}
                    <span className="text-[10px] text-muted-foreground">
                      {new Date(chat.updated_at).toLocaleDateString("ru-RU", {
                        day: "numeric",
                        month: "short",
                      })}
                    </span>
                  </div>
                </div>
              </Link>
              <div className="absolute right-1 top-3">
                <ChatActions
                  projectId={id!}
                  chatId={chat.thread_id}
                  title={chat.title}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
