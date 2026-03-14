import { Route, Routes } from "react-router";
import { AppLayout } from "./layouts/AppLayout";
import { ProjectLayout } from "./layouts/ProjectLayout";
import { WelcomePage } from "./components/WelcomePage";
import { ChatList } from "@/features/chat/components/ChatList";
import { ChatView } from "@/features/chat/components/ChatView";
import { SphereStub } from "@/features/sphere/components/SphereStub";
import { ArtifactsStub } from "@/features/artifacts/components/ArtifactsStub";
import { ArtifactViewStub } from "@/features/artifacts/components/ArtifactViewStub";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<WelcomePage />} />
        <Route path="projects/:id" element={<ProjectLayout />}>
          <Route index element={<ChatList />} />
          <Route path="chats/:cid" element={<ChatView />} />
          <Route path="sphere" element={<SphereStub />} />
          <Route path="artifacts" element={<ArtifactsStub />} />
          <Route path="artifacts/:aid" element={<ArtifactViewStub />} />
        </Route>
      </Route>
    </Routes>
  );
}
