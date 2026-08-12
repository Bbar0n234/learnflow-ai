import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";
import { AppLayout } from "./layouts/AppLayout";
import { ProjectLayout } from "./layouts/ProjectLayout";
import { WelcomePage } from "@/pages/welcome";
import { ChatList } from "@/pages/project-chats";
import { ChatView } from "@/pages/chat";
import { SphereView } from "@/pages/sphere";
import { ArtifactsPage, NoArtifactSelected } from "@/pages/artifacts";
import { ArtifactView } from "@/pages/artifact";
import { SettingsPage } from "@/pages/user-settings";
import { ProjectSettingsPage } from "@/pages/project-settings";
import { SecurityRouteGuard } from "@/pages/security";
import { NotFoundPage } from "@/pages/not-found";
import { SIEM_ENABLED } from "@/shared/config/feature-flags";
import { LoadingState } from "@/shared/ui/StateScreen";

// Lazy load Security page
const SecurityPage = lazy(() =>
  import("@/pages/security").then((m) => ({
    default: m.SecurityPage,
  })),
);

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<WelcomePage />} />
        <Route path="settings" element={<SettingsPage />} />
        {SIEM_ENABLED && (
          <Route
            path="security"
            element={
              <SecurityRouteGuard>
                <Suspense fallback={<LoadingState className="h-full" />}>
                  <SecurityPage />
                </Suspense>
              </SecurityRouteGuard>
            }
          />
        )}
        <Route path="projects/:id" element={<ProjectLayout />}>
          <Route index element={<ChatList />} />
          <Route path="chats/new" element={<ChatView />} />
          <Route path="chats/:cid" element={<ChatView />} />
          <Route path="sphere" element={<SphereView />} />
          <Route path="artifacts" element={<ArtifactsPage />}>
            <Route index element={<NoArtifactSelected />} />
            <Route path=":aid" element={<ArtifactView />} />
          </Route>
          <Route path="settings" element={<ProjectSettingsPage />} />
        </Route>
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
