import { type FormEvent, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/shared/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";
import { Input } from "@/shared/ui/input";
import {
  CHAT_TITLE_MAX_LENGTH,
  useDeleteChat,
  useUpdateChat,
} from "@/shared/api/chats";
import { getApiErrorMessage } from "@/shared/lib/api-error";
import { logger } from "@/shared/lib/logger";

interface ChatActionsProps {
  projectId: string;
  chatId: string;
  title: string;
}

export function ChatActions({ projectId, chatId, title }: ChatActionsProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const updateChat = useUpdateChat();
  const deleteChat = useDeleteChat();

  const [renameOpen, setRenameOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [newTitle, setNewTitle] = useState(title);
  const [renameError, setRenameError] = useState<string | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  function handleRename(e: FormEvent) {
    e.preventDefault();
    const trimmed = newTitle.trim();
    if (!trimmed || trimmed === title) {
      setRenameOpen(false);
      return;
    }
    setRenameError(null);
    updateChat.mutate(
      { projectId, chatId, data: { title: trimmed } },
      {
        onSuccess: () => setRenameOpen(false),
        onError: (err) => {
          logger.error("[Rename chat error]", err);
          setRenameError(getApiErrorMessage(err));
        },
      },
    );
  }

  function handleDelete() {
    const isCurrentChat =
      location.pathname === `/projects/${projectId}/chats/${chatId}`;
    setDeleteError(null);
    deleteChat.mutate(
      { projectId, chatId },
      {
        onSuccess: () => {
          setDeleteOpen(false);
          if (isCurrentChat) {
            navigate(`/projects/${projectId}`);
          }
        },
        onError: (err) => {
          logger.error("[Delete chat error]", err);
          setDeleteError(getApiErrorMessage(err));
        },
      },
    );
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="ghost"
              size="icon-xs"
              className="pointer-events-none opacity-0 group-hover/card:pointer-events-auto group-hover/card:opacity-100 focus-visible:pointer-events-auto focus-visible:opacity-100"
              onClick={(e) => e.preventDefault()}
            />
          }
        >
          <MoreHorizontal className="h-3.5 w-3.5" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem
            onClick={() => {
              setNewTitle(title);
              setRenameError(null);
              setRenameOpen(true);
            }}
          >
            <Pencil />
            Переименовать
          </DropdownMenuItem>
          <DropdownMenuItem
            variant="destructive"
            onClick={() => {
              setDeleteError(null);
              setDeleteOpen(true);
            }}
          >
            <Trash2 />
            Удалить
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      {/* Rename dialog */}
      <Dialog open={renameOpen} onOpenChange={(open) => setRenameOpen(open)}>
        <DialogContent>
          <form onSubmit={handleRename}>
            <DialogHeader>
              <DialogTitle>Переименовать чат</DialogTitle>
              <DialogDescription>
                Введите новое название чата.
              </DialogDescription>
            </DialogHeader>
            <div className="py-4 space-y-2">
              <Input
                value={newTitle}
                onChange={(e) => {
                  setNewTitle(e.target.value);
                  setRenameError(null);
                }}
                maxLength={CHAT_TITLE_MAX_LENGTH}
                autoFocus
              />
              {renameError && (
                <p className="text-sm text-destructive">{renameError}</p>
              )}
            </div>
            <DialogFooter>
              <Button
                variant="outline"
                type="button"
                onClick={() => setRenameOpen(false)}
              >
                Отмена
              </Button>
              <Button
                type="submit"
                disabled={
                  !newTitle.trim() ||
                  newTitle.trim() === title ||
                  updateChat.isPending
                }
              >
                Сохранить
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Delete confirmation dialog */}
      <Dialog open={deleteOpen} onOpenChange={(open) => setDeleteOpen(open)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Удалить чат</DialogTitle>
            <DialogDescription>
              Удалить «{title}»? История сообщений будет удалена. Это действие
              нельзя отменить. Артефакты чата останутся в проекте.
            </DialogDescription>
          </DialogHeader>
          {deleteError && (
            <p className="text-sm text-destructive">{deleteError}</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteOpen(false)}>
              Отмена
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteChat.isPending}
            >
              Удалить
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
