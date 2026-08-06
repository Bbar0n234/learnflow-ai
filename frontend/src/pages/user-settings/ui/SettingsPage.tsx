import { ModelSelector } from "@/features/model-selector";
import { MCPServersSection } from "@/features/mcp-servers";
import { CustomInstructionsSection } from "./CustomInstructionsSection";
import { AgentMemorySection } from "./AgentMemorySection";
import { SkillContextSection } from "./SkillContextSection";

export function SettingsPage() {
  return (
    <div className="mx-auto max-w-[640px] px-6 py-8">
      <h1 className="mb-6 font-serif text-xl font-semibold text-foreground">
        Настройки
      </h1>
      <div className="space-y-4">
        <section className="rounded-xl border border-border bg-card p-5">
          <ModelSelector scope="user" />
        </section>
        <section className="rounded-xl border border-border bg-card p-5">
          <CustomInstructionsSection />
        </section>
        <section className="rounded-xl border border-border bg-card p-5">
          <AgentMemorySection />
        </section>
        <section className="rounded-xl border border-border bg-card p-5">
          <SkillContextSection />
        </section>
        <section className="rounded-xl border border-border bg-card p-5">
          <MCPServersSection scope="user" />
        </section>
      </div>
    </div>
  );
}
