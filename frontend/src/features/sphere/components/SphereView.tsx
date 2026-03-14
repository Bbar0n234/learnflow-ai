import { useState } from "react";
import { useParams } from "react-router";
import { useSphere } from "../hooks/useSphere";
import { useUpdateSphere } from "../hooks/useUpdateSphere";
import { SphereViewer } from "./SphereViewer";
import { SphereEditor } from "./SphereEditor";

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
    <SphereViewer
      content={data?.content ?? ""}
      onEdit={() => setIsEditing(true)}
    />
  );
}
