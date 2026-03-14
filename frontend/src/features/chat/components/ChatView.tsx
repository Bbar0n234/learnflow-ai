import { useState } from "react";
import { useParams } from "react-router";
import { useChat } from "../hooks/useChat";
import { MessageList } from "./MessageList";
import { ChatInput } from "./ChatInput";
import type { Message } from "@/shared/api/types";

export function ChatView() {
  const { id, cid } = useParams();
  const { data, isLoading, isError } = useChat(id, cid);
  const [localMessages, setLocalMessages] = useState<Message[]>([]);

  function handleSend(content: string) {
    const message: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setLocalMessages((prev) => [...prev, message]);
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
        Failed to load chat.
      </div>
    );
  }

  const allMessages = [...(data?.messages ?? []), ...localMessages];

  return (
    <div className="flex h-full flex-col">
      <MessageList messages={allMessages} />
      <ChatInput onSend={handleSend} />
    </div>
  );
}
