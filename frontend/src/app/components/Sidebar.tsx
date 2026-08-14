import { useState } from "react";
import { Link, useMatch, useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/shared/api/query-keys";
import {
  LogOut,
  MessageSquare,
  Moon,
  PanelLeftClose,
  Plus,
  Settings,
  Sun,
  User,
  Shield,
} from "lucide-react";
import { getIsAdminFromAccessToken, getMe, logout } from "@/shared/api/auth";
import { clearAccessToken, getAccessToken } from "@/shared/api/client";
import { Button } from "@/shared/ui/button";
import { Wordmark } from "@/shared/ui/Wordmark";
import { Illustration } from "@/shared/ui/Illustration";
import { TypedTitle } from "@/shared/ui/TypedTitle";
import { useUIStore } from "@/stores/ui-store";
import { useThemeStore } from "@/stores/theme-store";
import { DEFAULT_CHAT_TITLE, useRecentChats } from "@/shared/api/chats";
import { SIEM_ENABLED } from "@/shared/config/feature-flags";
import { ChatActions } from "@/features/chat-actions";
import { ProjectList } from "./ProjectList";
import { CreateProjectModal } from "./CreateProjectModal";
import { NewChatModal } from "./NewChatModal";

export function Sidebar() {
  const [createOpen, setCreateOpen] = useState(false);
  const [newChatOpen, setNewChatOpen] = useState(false);
  const toggleSidebar = useUIStore((s) => s.toggleSidebar);
  const theme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);
  const navigate = useNavigate();
  const isSettings = !!useMatch("/settings");

  const { data: recentChats } = useRecentChats();
  const { data: user } = useQuery({
    queryKey: queryKeys.auth.me,
    queryFn: getMe,
    staleTime: Infinity,
  });
  const token = getAccessToken();
  const isAdmin = user?.is_admin === true || getIsAdminFromAccessToken(token);

  function handleLogout() {
    logout().catch(() => {});
    clearAccessToken();
    window.location.reload();
  }

  return (
    <div className="flex h-full w-[252px] flex-col">
      {/* Header — target height 52–58px per handoff */}
      <div className="flex h-[56px] items-center justify-between border-b border-border px-4">
        <h2 className="text-lg text-sidebar-foreground">
          <Wordmark short />
        </h2>
        <Button variant="ghost" size="icon-sm" onClick={toggleSidebar}>
          <PanelLeftClose className="h-4 w-4" />
        </Button>
      </div>

      {/* Actions */}
      <div className="flex flex-col gap-1 px-3 py-3">
        <Button
          variant="default"
          size="sm"
          className="w-full justify-start"
          onClick={() => setNewChatOpen(true)}
        >
          <Plus className="mr-2 h-4 w-4" />+ Новый чат
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="w-full justify-start"
          onClick={() => setCreateOpen(true)}
        >
          <Plus className="mr-2 h-4 w-4" />
          Новый проект
        </Button>
        {SIEM_ENABLED && isAdmin && (
          <Button
            variant="ghost"
            size="sm"
            className="justify-start"
            onClick={() => navigate("/security")}
          >
            <Shield className="mr-2 h-4 w-4" />
            Безопасность
          </Button>
        )}
      </div>

      {/* Projects */}
      <div className="flex-1 overflow-auto px-3">
        <p className="mb-1 px-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Проекты
        </p>
        <ProjectList />

        {/* Recent chats */}
        {recentChats?.items.length ? (
          <div className="mt-4">
            <p className="mb-1 px-3 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Недавнее
            </p>
            <div className="flex flex-col gap-0.5">
              {recentChats.items.map((chat) => (
                <div
                  key={chat.thread_id}
                  className="group/card relative flex items-center"
                >
                  <Link
                    to={`/projects/${chat.project_id}/chats/${chat.thread_id}`}
                    className="flex min-w-0 flex-1 items-center gap-2 rounded-md px-3 py-1.5 text-sm text-sidebar-foreground hover:bg-sidebar-accent"
                  >
                    <MessageSquare className="h-4 w-4 shrink-0" />
                    <div className="min-w-0 flex-1">
                      <TypedTitle
                        as="p"
                        text={chat.title}
                        animateFrom={DEFAULT_CHAT_TITLE}
                        className="truncate"
                      />
                      <p className="truncate text-xs text-muted-foreground">
                        {chat.project_name}
                      </p>
                    </div>
                  </Link>
                  <div className="absolute right-1">
                    <ChatActions
                      projectId={chat.project_id}
                      chatId={chat.thread_id}
                      title={chat.title}
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      {/* Sidebar vignette illustration */}
      <Illustration
        scene="sidebar-vignette"
        alt=""
        className="pointer-events-none w-full select-none"
      />

      {/* User footer */}
      {user && (
        <div className="border-t border-border px-3 py-3">
          <div
            className={`flex items-center justify-between rounded-lg px-2 py-1 transition-colors ${
              isSettings ? "bg-sidebar-accent" : ""
            }`}
          >
            <div className="flex min-w-0 items-center gap-2">
              <User className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="truncate text-sm text-sidebar-foreground">
                {user.name}
              </span>
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={toggleTheme}
              title={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
            >
              {theme === "dark" ? (
                <Sun className="h-4 w-4" />
              ) : (
                <Moon className="h-4 w-4" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => navigate("/settings")}
              title="Настройки"
            >
              <Settings className="h-4 w-4" />
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={handleLogout}
              title="Выйти"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      <CreateProjectModal open={createOpen} onOpenChange={setCreateOpen} />
      <NewChatModal open={newChatOpen} onOpenChange={setNewChatOpen} />
    </div>
  );
}
