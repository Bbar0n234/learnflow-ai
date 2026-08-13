import { lazy, Suspense } from "react";
import { Route, Routes, useSearchParams } from "react-router";
import { AppLayout } from "./layouts/AppLayout";
import { ProjectLayout } from "./layouts/ProjectLayout";
import { RequireAuth } from "./components/RequireAuth";
import { WelcomePage } from "@/pages/welcome";
import { LoginPage } from "@/pages/login";
import { ChatList } from "@/pages/project-chats";
import { ChatView } from "@/pages/chat";
import { SphereView } from "@/pages/sphere";
import { ArtifactsPage } from "@/pages/artifacts";
import { ArtifactView } from "@/pages/artifact";
import { SettingsPage } from "@/pages/user-settings";
import { ProjectSettingsPage } from "@/pages/project-settings";
import { SecurityRouteGuard } from "@/pages/security";
import { SIEM_ENABLED } from "@/shared/config/feature-flags";

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

// Артефакт любой вложенности адресуется query-параметром `?path=` (T2.2) —
// React-роут не матчит слэши внутри одного сегмента (`lecture-1/slides.md`).
// Выбор между вьюером и пустым состоянием живёт здесь, в `app`, а не в
// `pages/artifacts/ui/ArtifactsPage.tsx`: `pages/artifact` — соседний
// слайс, и FSD-границы (`eslint.config.mjs`, `boundaries/dependencies`)
// запрещают импорт pages→pages — `app` остаётся единственным слоем, которому
// можно скомпоновать оба слайса напрямую.
function ArtifactsViewerSlot() {
  const [searchParams] = useSearchParams();
  const path = searchParams.get("path");

  if (!path) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        Выберите артефакт из списка
      </div>
    );
  }

  return <ArtifactView />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route index element={<WelcomePage />} />
          <Route path="settings" element={<SettingsPage />} />
          {SIEM_ENABLED && (
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
          )}
          <Route path="projects/:id" element={<ProjectLayout />}>
            <Route index element={<ChatList />} />
            <Route path="chats/new" element={<ChatView />} />
            <Route path="chats/:cid" element={<ChatView />} />
            <Route path="sphere" element={<SphereView />} />
            <Route path="artifacts" element={<ArtifactsPage />}>
              <Route index element={<ArtifactsViewerSlot />} />
              <Route path=":aid" element={<ArtifactView />} />
            </Route>
            <Route path="settings" element={<ProjectSettingsPage />} />
          </Route>
        </Route>
      </Route>
    </Routes>
  );
}
