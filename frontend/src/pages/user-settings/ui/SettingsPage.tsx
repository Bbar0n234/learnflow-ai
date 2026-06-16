import { ModelSelector } from "@/features/model-selector";
import { CustomInstructionsSection } from "./CustomInstructionsSection";
import { AgentMemorySection } from "./AgentMemorySection";
import { MCPServersSection } from "@/features/mcp-servers";

export function SettingsPage() {
  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <h1 className="mb-6 text-xl font-semibold">Settings</h1>
      <div className="space-y-8">
        <section>
          <ModelSelector scope="user" />
        </section>
        <section>
          <CustomInstructionsSection />
        </section>
        <section>
          <AgentMemorySection />
        </section>
        <section>
          <MCPServersSection scope="user" />
        </section>
      </div>
    </div>
  );
}
