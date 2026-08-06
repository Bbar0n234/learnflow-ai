import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { useCreateChat } from "@/shared/api/chats";
import { getApiErrorMessage } from "@/shared/lib/api-error";
import { logger } from "@/shared/lib/logger";
import { ChatHeader } from "./ChatHeader";
import { ChatInput } from "./ChatInput";

// Draft branch of the composer entry path (`/projects/:id/chats/new`,
// § Создание чата и первое сообщение design-brief'а): the chat doesn't exist
// in the DB yet, so unlike `ChatThread` this component never calls `useChat`
// or `useAgentStream` — there's no `thread_id` to scope them to. Sending the
// first message creates the chat and hands off to `ChatThread` via
// `navigate(..., { state: { initialMessage } })`, the same mechanic as the
// project-page entry field (T2.5).
export function ChatDraft() {
  const { id: projectId } = useParams();
  const navigate = useNavigate();
  const createChat = useCreateChat();
  const [draftText, setDraftText] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);

  function handleSend(content: string) {
    if (!projectId) return;
    setCreateError(null);
    createChat.mutate(projectId, {
      onSuccess: (created) => {
        navigate(`/projects/${projectId}/chats/${created.thread_id}`, {
          replace: true,
          state: { initialMessage: content },
        });
      },
      onError: (err) => {
        logger.error("[Create chat error]", err);
        setCreateError(getApiErrorMessage(err));
      },
    });
  }

  return (
    <div className="flex h-full flex-col">
      <ChatHeader draft />
      <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
        <p className="font-serif text-[17px] font-semibold text-foreground">
          Новый чат
        </p>
        <p className="text-sm text-muted-foreground">
          Напишите первое сообщение — чат появится вместе с ним, а название
          придумает модель.
        </p>
        {createError && (
          <p className="text-sm text-destructive">{createError}</p>
        )}
      </div>
      {/* Text is preserved on error: `value` is controlled by this component,
          not cleared internally by `ChatInput` — only a successful create
          navigates away (unmounting this component). */}
      <ChatInput
        value={draftText}
        onValueChange={setDraftText}
        onSend={handleSend}
        disabled={createChat.isPending}
      />
    </div>
  );
}
