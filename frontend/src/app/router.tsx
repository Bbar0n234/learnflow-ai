import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";
import { AppLayout } from "./layouts/AppLayout";
import { ProjectLayout } from "./layouts/ProjectLayout";
import { WelcomePage } from "@/pages/welcome";
import { ChatList } from "@/pages/project-chats";
import { ChatView } from "@/pages/chat";
import { SphereView } from "@/pages/sphere";
import { ArtifactsPage } from "@/pages/artifacts";
import { ArtifactView } from "@/pages/artifact";
import { SettingsPage } from "@/pages/user-settings";
import { ProjectSettingsPage } from "@/pages/project-settings";
import { SecurityRouteGuard } from "@/pages/security";

// Lazy load Security page
const SecurityPage = lazy(() =>
  import("@/pages/security").then((m) => ({
    default: m.SecurityPage,
  })),
);

const LoadingFallback = () => (
  <div className="flex items-center justify-center h-full">
    <p className="text-muted-foreground">Загрузка...</p>
  </div>
);

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<WelcomePage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route
          path="security"
          element={
            <SecurityRouteGuard>
              <Suspense fallback={<LoadingFallback />}>
                <SecurityPage />
              </Suspense>
            </SecurityRouteGuard>
          }
        />
        <Route path="projects/:id" element={<ProjectLayout />}>
          <Route index element={<ChatList />} />
          <Route path="chats/new" element={<ChatView />} />
          <Route path="chats/:cid" element={<ChatView />} />
          <Route path="sphere" element={<SphereView />} />
          <Route path="artifacts" element={<ArtifactsPage />}>
            <Route
              index
              element={
                <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                  Выберите артефакт из списка
                </div>
              }
            />
            <Route path=":aid" element={<ArtifactView />} />
          </Route>
          <Route path="settings" element={<ProjectSettingsPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
