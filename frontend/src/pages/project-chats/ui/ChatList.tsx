import { useState, type KeyboardEvent } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { SendHorizontal } from "lucide-react";
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
      {/* New chat input — card+shadow per handoff screen 9 */}
      <div
        className="mb-6 rounded-xl border border-border bg-card p-3"
        style={{ boxShadow: "var(--shadow-input)" }}
      >
        <Textarea
          value={newChatText}
          onChange={(e) => setNewChatText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Название нового чата..."
          disabled={createChat.isPending}
          className="min-h-[52px] resize-none border-0 bg-transparent text-sm focus-visible:ring-0"
        />
        <div className="mt-2 flex items-center justify-between">
          <div className="flex gap-1.5">
            <span className="rounded-full bg-secondary px-3 py-0.5 text-xs text-secondary-foreground">
              Прикрепить
            </span>
            <span className="rounded-full bg-secondary px-3 py-0.5 text-xs text-secondary-foreground">
              Модель
            </span>
          </div>
          <Button
            size="icon"
            onClick={handleCreate}
            disabled={createChat.isPending || !trimmed}
            className="h-[34px] w-[34px] rounded-full"
          >
            <SendHorizontal className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* Chat list */}
      {isLoading && (
        <p className="text-sm text-muted-foreground">Загрузка чатов...</p>
      )}
      {isError && (
        <p className="text-sm text-destructive">Не удалось загрузить чаты.</p>
      )}
      {data && data.items.length === 0 && (
        <div className="flex flex-col items-center gap-4 py-8">
          <Illustration
            scene="empty-chats"
            alt="Нет чатов"
            className="w-full max-w-[280px]"
          />
          <p className="text-sm text-muted-foreground">
            Нет чатов. Создайте выше!
          </p>
        </div>
      )}
      {data && data.items.length > 0 && (
        <div className="flex flex-col gap-0.5">
          {data.items.map((chat, i) => (
            <Link
              key={chat.thread_id}
              to={`/projects/${id}/chats/${chat.thread_id}`}
              className="group flex items-start rounded-lg px-3 py-3 transition-colors hover:bg-muted"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-serif text-sm font-semibold text-foreground">
                  {chat.title}
                </p>
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  Нет превью
                </p>
                <div className="mt-1.5 flex items-center gap-2">
                  {/* Stub contribution chips — visual only, no backend contract */}
                  {i % 2 === 0 && (
                    <span className="rounded-full bg-secondary px-2 text-[10px] leading-5 text-secondary-foreground">
                      {(i + 1) * 2} артефакта
                    </span>
                  )}
                  {i % 3 !== 2 && (
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
          ))}
        </div>
      )}
    </div>
  );
}
