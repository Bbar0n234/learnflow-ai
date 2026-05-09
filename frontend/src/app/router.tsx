import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";
import { AppLayout } from "./layouts/AppLayout";
import { ProjectLayout } from "./layouts/ProjectLayout";
import { WelcomePage } from "./components/WelcomePage";
import { ChatList } from "@/features/chat/components/ChatList";
import { ChatView } from "@/features/chat/components/ChatView";
import { SphereView } from "@/features/sphere/components/SphereView";
import { ArtifactList } from "@/features/artifacts/components/ArtifactList";
import { ArtifactView } from "@/features/artifacts/components/ArtifactView";
import { SettingsPage } from "@/features/settings/components/SettingsPage";
import { ProjectSettingsPage } from "@/features/settings/components/ProjectSettingsPage";
import { SecurityRouteGuard } from "@/features/security/components/SecurityRouteGuard";

// Lazy load Security page
const SecurityPage = lazy(() =>
  import("@/features/security/pages/SecurityPage").then((m) => ({
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
          <Route path="chats/:cid" element={<ChatView />} />
          <Route path="sphere" element={<SphereView />} />
          <Route path="artifacts" element={<ArtifactList />} />
          <Route path="artifacts/:aid" element={<ArtifactView />} />
          <Route path="settings" element={<ProjectSettingsPage />} />
        </Route>
      </Route>
    </Routes>
  );
}
