import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
import { useModels } from "../hooks/useModels";
import { useSettings } from "../hooks/useSettings";
import { useUpdateSettings } from "../hooks/useUpdateSettings";

interface Props {
  scope: "user" | "project" | "thread";
  projectId?: string;
  threadId?: string;
}

export function ModelSelector({ scope, projectId, threadId }: Props) {
  const { data: models } = useModels();
  const { data: settings } = useSettings(scope, projectId, threadId);
  const updateSettings = useUpdateSettings(scope, projectId, threadId);

  const handleChange = (value: string | null) => {
    if (value === null) return;
    updateSettings.mutate({
      model_name: value === "__default__" ? null : value,
    });
  };

  const currentValue = settings?.model_name ?? "__default__";

  const selectedDisplayName =
    currentValue === "__default__"
      ? scope === "user"
        ? "Default"
        : "Inherit"
      : (models?.items.find((m) => m.name === currentValue)?.display_name ??
        currentValue);

  const resolvedDisplayName =
    models?.items.find((m) => m.name === settings?.resolved_model)
      ?.display_name ?? settings?.resolved_model;

  return (
    <div>
      <label className="mb-1 block text-sm font-medium">Model</label>
      <Select
        value={currentValue}
        onValueChange={handleChange}
        disabled={updateSettings.isPending}
      >
        <SelectTrigger className="w-full">
          <SelectValue placeholder={selectedDisplayName}>
            {selectedDisplayName}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__default__">
            {scope === "user" ? "Default" : "Inherit"}
          </SelectItem>
          {models?.items.map((m) => (
            <SelectItem key={m.name} value={m.name}>
              {m.display_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {settings && (
        <p className="mt-1 text-xs text-muted-foreground">
          Current: {resolvedDisplayName}
        </p>
      )}
    </div>
  );
}
