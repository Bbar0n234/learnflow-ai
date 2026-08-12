import { useState } from "react";
import { useParams } from "react-router";
import { useSphere } from "@/shared/api/sphere";
import { useUpdateSphere } from "@/shared/api/sphere";
import { Button } from "@/shared/ui/button";
import { LoadingState, StateScreen } from "@/shared/ui/StateScreen";
import { SphereViewer } from "./SphereViewer";
import { SphereEditor } from "./SphereEditor";
import { SphereVersionPanel } from "./SphereVersionPanel";
import { SHOW_GROUP_B_STUBS } from "@/shared/config/feature-flags";

export function SphereView() {
  const { id } = useParams();
  const { data, isLoading, isError, refetch } = useSphere(id);
  const updateSphere = useUpdateSphere();
  const [isEditing, setIsEditing] = useState(false);

  if (isLoading) {
    return <LoadingState className="h-full" label="Загрузка сферы…" />;
  }

  if (isError) {
    return (
      <StateScreen
        scene="error-state"
        alt="Иллюстрация: ошибка"
        illustrationClassName="max-w-[280px]"
        title="Не удалось загрузить сферу знаний"
        description="Что-то пошло не так при загрузке. Проверьте соединение и попробуйте ещё раз."
        action={
          <Button variant="outline" onClick={() => void refetch()}>
            Повторить
          </Button>
        }
        className="h-full"
      />
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
