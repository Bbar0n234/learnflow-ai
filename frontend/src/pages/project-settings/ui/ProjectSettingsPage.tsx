import { useParams } from "react-router";
import { ModelSelector } from "@/features/model-selector";
import { MCPServersSection } from "@/features/mcp-servers";

export function ProjectSettingsPage() {
  const { id: projectId } = useParams();

  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <h2 className="mb-6 text-lg font-semibold">Project Settings</h2>
      <div className="space-y-8">
        <section>
          <ModelSelector scope="project" projectId={projectId} />
        </section>
        <section>
          <MCPServersSection scope="project" projectId={projectId} />
        </section>
      </div>
    </div>
  );
}
