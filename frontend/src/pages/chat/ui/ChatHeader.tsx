import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { ArrowLeft, Bot, Settings2 } from "lucide-react";
import { useProject } from "@/shared/api/projects";
import { useChat } from "@/shared/api/chats";
import { ModelSelector } from "@/features/model-selector";
import { MCPServersSection } from "@/features/mcp-servers";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/ui/dialog";

export function ChatHeader() {
  const { id: projectId, cid: threadId } = useParams();
  const navigate = useNavigate();
  const { data: project } = useProject(projectId!);
  const { data: chat } = useChat(projectId, threadId);
  const [modelOpen, setModelOpen] = useState(false);
  const [toolsOpen, setToolsOpen] = useState(false);

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
        <span className="truncate font-serif text-[17px] font-semibold tracking-tight text-foreground">
          {chat?.title ?? "Чат"}
        </span>
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
        </div>
      </div>
    </div>
  );
}
