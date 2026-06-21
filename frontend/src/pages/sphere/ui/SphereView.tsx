import { useState } from "react";
import { useParams } from "react-router";
import { useSphere } from "@/shared/api/sphere";
import { useUpdateSphere } from "@/shared/api/sphere";
import { SphereViewer } from "./SphereViewer";
import { SphereEditor } from "./SphereEditor";
import { SphereVersionPanel } from "./SphereVersionPanel";
import { SHOW_GROUP_B_STUBS } from "@/shared/config/feature-flags";

export function SphereView() {
  const { id } = useParams();
  const { data, isLoading, isError } = useSphere(id);
  const updateSphere = useUpdateSphere();
  const [isEditing, setIsEditing] = useState(false);

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground">
        Loading sphere...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex h-full items-center justify-center text-destructive">
        Failed to load sphere.
      </div>
    );
  }

  if (isEditing) {
    return (
      <SphereEditor
        content={data?.content ?? ""}
        isPending={updateSphere.isPending}
        error={updateSphere.error}
        onSave={(content) => {
          updateSphere.mutate(
            { projectId: id!, data: { content } },
            { onSuccess: () => setIsEditing(false) },
          );
        }}
        onCancel={() => setIsEditing(false)}
      />
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* Viewer — flex-1 (до правой панели) */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <SphereViewer
          content={data?.content ?? ""}
          onEdit={() => setIsEditing(true)}
        />
      </div>
      {/* Правая панель «Жизнь сферы» — T6b (на моках, group B stub) */}
      {SHOW_GROUP_B_STUBS && <SphereVersionPanel />}
    </div>
  );
}
