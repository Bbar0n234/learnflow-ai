import { useCallback, useState } from "react";
import { useParams } from "react-router";
import { useChat } from "@/shared/api/chats";
import { useAgentStream } from "../model/useAgentStream";
import { useStreamStore } from "@/stores/stream-store";
import { useStudio } from "../model/useStudio";
import { cn } from "@/shared/lib/utils";
import { ChatHeader } from "./ChatHeader";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { StudioPanel } from "./StudioPanel";
import { SphereLens } from "./SphereLens";
import type { Message } from "@/shared/api/chats";

export function ChatView() {
  const { id, cid } = useParams();
  const isStreaming = useStreamStore(
    (s) => s.streamingChatId === cid && s.isStreaming,
  );
  const { data, isLoading, isError } = useChat(id, cid, {
    refetchOnWindowFocus: !isStreaming,
  });
  const [localMessages, setLocalMessages] = useState<Message[]>([]);
  const [streamError, setStreamError] = useState<string | null>(null);

  const studio = useStudio();

  const handleDone = useCallback(() => {
    setLocalMessages([]);
  }, []);

  const handleSecurityBlock = useCallback(() => {
    // Server-side already persisted the user message + redacted placeholder
    // and we invalidated the chat query — drop the optimistic local copy
    // to avoid duplicates after refetch.
    setLocalMessages([]);
  }, []);

  const { send, cancel } = useAgentStream(id!, cid!, {
    onDone: handleDone,
    onError: (detail) => setStreamError(detail),
    onSecurityBlock: handleSecurityBlock,
  });

  const streamingText = useStreamStore((s) => s.streamingText);
  const activeTool = useStreamStore((s) => s.activeTool);
  const streamingArtifacts = useStreamStore((s) => s.streamingArtifacts);

  function handleSend(content: string) {
    setStreamError(null);
    const message: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      created_at: new Date().toISOString(),
      artifacts: [],
    };
    setLocalMessages((prev) => [...prev, message]);
    send(content);
  }

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
          streamingText={streamingText}
          activeTool={activeTool}
          streamingArtifacts={streamingArtifacts}
          projectId={id!}
          chatId={cid!}
          streamError={streamError}
          onOpenLens={() => studio.setLensOpen(true)}
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

      {/* Studio panel dock */}
      {studio.open && (
        <StudioPanel
          studio={studio}
          onOpenLens={() => studio.setLensOpen(true)}
        />
      )}

      {/* Overlay lens */}
      <SphereLens
        open={studio.lensOpen}
        onClose={() => studio.setLensOpen(false)}
      />
    </div>
  );
}
