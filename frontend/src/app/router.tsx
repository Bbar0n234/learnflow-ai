import { Route, Routes } from "react-router";
import { AppLayout } from "./layouts/AppLayout";
import { ProjectLayout } from "./layouts/ProjectLayout";
import { WelcomePage } from "./components/WelcomePage";
import { ProjectChatsStub } from "@/features/projects/components/ProjectChatsStub";
import { ChatStub } from "@/features/chat/components/ChatStub";
import { SphereStub } from "@/features/sphere/components/SphereStub";
import { ArtifactsStub } from "@/features/artifacts/components/ArtifactsStub";
import { ArtifactViewStub } from "@/features/artifacts/components/ArtifactViewStub";

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<WelcomePage />} />
        <Route path="projects/:id" element={<ProjectLayout />}>
          <Route index element={<ProjectChatsStub />} />
          <Route path="chats/:cid" element={<ChatStub />} />
          <Route path="sphere" element={<SphereStub />} />
          <Route path="artifacts" element={<ArtifactsStub />} />
          <Route path="artifacts/:aid" element={<ArtifactViewStub />} />
        </Route>
      </Route>
    </Routes>
  );
}
