import { useState } from "react";
import { Link, useMatch } from "react-router";
import { MessageSquare, PanelLeftClose, Plus } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { useUIStore } from "@/stores/ui-store";
import { useRecentChats } from "@/features/chat/hooks/useRecentChats";
import { ProjectList } from "@/features/projects/components/ProjectList";
import { CreateProjectModal } from "@/features/projects/components/CreateProjectModal";

export function Sidebar() {
  const [createOpen, setCreateOpen] = useState(false);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const projectMatch = useMatch("/projects/:id/*");
  const projectId = projectMatch?.params.id;

  const { data: recentChats } = useRecentChats();

  return (
    <div className="flex h-full w-64 flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h2 className="text-lg font-semibold text-sidebar-foreground">LearnFlowAI</h2>
        <Button variant="ghost" size="icon-sm" onClick={toggleSidebar}>
          <PanelLeftClose className="h-4 w-4" />
        </Button>
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-1 px-3 py-3">
        <Button variant="ghost" size="sm" className="justify-start" disabled={!projectId}>
          <Plus className="mr-2 h-4 w-4" />
          New Chat
        </Button>
        <Button
          variant="ghost"
          size="sm"
          className="justify-start"
          onClick={() => setCreateOpen(true)}
        >
          <Plus className="mr-2 h-4 w-4" />
          New Project
        </Button>
      </div>

      {/* Projects */}
      <div className="flex-1 overflow-auto px-3">
        <p className="mb-1 px-3 text-xs font-medium text-muted-foreground uppercase">
          Projects
        </p>
        <ProjectList />

        {/* Recent chats */}
        {recentChats?.items.length ? (
          <div className="mt-4">
            <p className="mb-1 px-3 text-xs font-medium text-muted-foreground uppercase">
              Recents
            </p>
            <div className="flex flex-col gap-0.5">
              {recentChats.items.map((chat) => (
                <Link
                  key={chat.thread_id}
                  to={`/projects/${chat.project_id}/chats/${chat.thread_id}`}
                  className="flex items-center gap-2 rounded-md px-3 py-1.5 text-sm text-sidebar-foreground hover:bg-sidebar-accent"
                >
                  <MessageSquare className="h-4 w-4 shrink-0" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate">{chat.title}</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {chat.project_name}
                    </p>
                  </div>
                </Link>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <CreateProjectModal open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
