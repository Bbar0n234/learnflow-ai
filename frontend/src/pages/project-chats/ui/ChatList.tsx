import { useState, type KeyboardEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { MessageSquare, SendHorizontal } from "lucide-react";
import { Textarea } from "@/shared/ui/textarea";
import { Button } from "@/shared/ui/button";
import { Illustration } from "@/shared/ui/Illustration";
import { useChats } from "@/shared/api/chats";
import { useCreateChat } from "@/shared/api/chats";

export function ChatList() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data, isLoading, isError } = useChats(id);
  const createChat = useCreateChat();
  const [newChatText, setNewChatText] = useState("");

  const trimmed = newChatText.trim();

  function handleCreate() {
    if (!trimmed || !id) return;
    createChat.mutate(
      { projectId: id, data: { title: trimmed } },
      {
        onSuccess: (created) => {
          setNewChatText("");
          navigate(`/projects/${id}/chats/${created.thread_id}`);
        },
      },
    );
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleCreate();
    }
  }

  return (
    <div className="h-full overflow-auto p-6">
      {/* New chat input */}
      <div className="mb-6">
        <div className="flex gap-2">
          <Textarea
            value={newChatText}
            onChange={(e) => setNewChatText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Chat title..."
            disabled={createChat.isPending}
            className="min-h-10 resize-none"
          />
          <Button
            size="icon"
            onClick={handleCreate}
            disabled={createChat.isPending || !trimmed}
          >
            <SendHorizontal className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Chat list */}
      {isLoading && <p className="text-muted-foreground">Loading chats...</p>}
      {isError && <p className="text-destructive">Failed to load chats.</p>}
      {data && data.items.length === 0 && (
        <div className="flex flex-col items-center gap-4 py-8">
          <Illustration
            scene="empty-chats"
            alt="No chats yet"
            className="max-w-[280px] w-full"
          />
          <p className="text-muted-foreground">
            No chats yet. Start one above!
          </p>
        </div>
      )}
      {data && data.items.length > 0 && (
        <div className="flex flex-col gap-1">
          {data.items.map((chat) => (
            <Link
              key={chat.thread_id}
              to={`/projects/${id}/chats/${chat.thread_id}`}
              className="flex items-center gap-3 rounded-lg px-4 py-3 transition-colors hover:bg-muted"
            >
              <MessageSquare className="h-5 w-5 shrink-0 text-muted-foreground" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{chat.title}</p>
                <p className="text-xs text-muted-foreground">
                  {new Date(chat.updated_at).toLocaleDateString()}
                </p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
