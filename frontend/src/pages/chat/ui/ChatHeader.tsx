import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { ArrowLeft, Bot, Settings2, PanelRight } from "lucide-react";
import { useProject } from "@/shared/api/projects";
import { DEFAULT_CHAT_TITLE } from "@/shared/api/chats";
import { useChatHistory } from "../model/useChatHistory";
import { TypedTitle } from "@/shared/ui/TypedTitle";
import { ModelSelector } from "@/features/model-selector";
import { MCPServersSection } from "@/features/mcp-servers";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/ui/dialog";
import { cn } from "@/shared/lib/utils";
import { SHOW_GROUP_B_STUBS } from "@/shared/config/feature-flags";

interface ChatHeaderProps {
  // Draft mode (`/projects/:id/chats/new`, § Draft-режим композера): чата ещё
  // нет, поэтому thread-scoped контролы (модель, инструменты, студия) скрыты
  // целиком, а название всегда — плейсхолдер. `studioOpen`/`onToggleStudio`
  // не нужны в draft — студия недоступна до появления `thread_id`.
  draft?: boolean;
  studioOpen?: boolean;
  onToggleStudio?: () => void;
}

export function ChatHeader({
  draft = false,
  studioOpen = false,
  onToggleStudio,
}: ChatHeaderProps) {
  const { id: projectId, cid: threadId } = useParams();
  const navigate = useNavigate();
  const { data: project } = useProject(projectId!);
  // В draft `threadId` отсутствует (маршрут `chats/new` не заводит `:cid`),
  // так что запрос уже выключен встроенным `enabled: !!chatId` в `useChat` —
  // сетевого `GET /projects/{id}/chats/new` не происходит. Обёртка
  // `useChatHistory` держит гейт фоновых рефетчей на время активного хода —
  // без неё observer заголовка рефетчил бы историю в обход гейта `ChatThread`.
  const { data: chat } = useChatHistory(projectId, threadId);
  const [modelOpen, setModelOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);
  const title = draft ? DEFAULT_CHAT_TITLE : (chat?.title ?? "Чат");

  return (
    <div className="flex h-[56px] flex-col justify-center border-b border-border px-4">
      <button
        onClick={() => navigate(`/projects/${projectId}`)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3 w-3" />
        <span>{project?.name ?? "Проект"}</span>
      </button>
      <div className="flex items-center gap-2">
        <TypedTitle
          as="span"
          text={title}
          animateFrom={DEFAULT_CHAT_TITLE}
          className="truncate font-serif text-[17px] font-semibold tracking-tight text-foreground"
        />
        {/* Draft: блок чипов пуст целиком (мокап `tplChatHeader(title, draft=true)`) —
            модель, инструменты и stub «Студия» появляются только после
            создания чата, когда есть `thread_id`. */}
        {!draft && (
          <div className="ml-auto flex shrink-0 items-center gap-1.5">
            <Dialog open={modelOpen} onOpenChange={setModelOpen}>
              <DialogTrigger
                render={
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-1 text-xs text-secondary-foreground transition-colors hover:bg-secondary/80"
                  >
                    <Bot className="h-3 w-3" />
                    Модель
                  </button>
                }
              />
              <DialogContent className="sm:max-w-md">
                <DialogHeader>
                  <DialogTitle>Модель чата</DialogTitle>
                </DialogHeader>
                <ModelSelector
                  scope="thread"
                  projectId={projectId}
                  threadId={threadId}
                />
              </DialogContent>
            </Dialog>

            <Dialog open={toolsOpen} onOpenChange={setToolsOpen}>
              <DialogTrigger
                render={
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded-full bg-secondary px-2.5 py-1 text-xs text-secondary-foreground transition-colors hover:bg-secondary/80"
                  >
                    <Settings2 className="h-3 w-3" />
                    Инструменты
                  </button>
                }
              />
              <DialogContent className="sm:max-w-md">
                <DialogHeader>
                  <DialogTitle>Инструменты чата</DialogTitle>
                </DialogHeader>
                <MCPServersSection
                  scope="thread"
                  projectId={projectId}
                  threadId={threadId}
                />
              </DialogContent>
            </Dialog>

            {/* Studio toggle chip (group B stub) */}
            {SHOW_GROUP_B_STUBS && (
              <button
                type="button"
                onClick={onToggleStudio}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition-colors",
                  studioOpen
                    ? "bg-secondary text-secondary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-secondary/50 hover:text-secondary-foreground",
                )}
              >
                <PanelRight className="h-3 w-3" />
                Студия
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
