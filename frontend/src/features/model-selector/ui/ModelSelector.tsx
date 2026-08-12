import { useId } from "react";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/shared/ui/select";
import { useModels } from "@/shared/api/models";
import { useSettings } from "@/shared/api/settings";
import { useUpdateSettings } from "@/shared/api/settings";

interface Props {
  scope: "user" | "project" | "thread";
  projectId?: string;
  threadId?: string;
}

export function ModelSelector({ scope, projectId, threadId }: Props) {
  const labelId = useId();
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

  const defaultChoiceLabel = scope === "user" ? "По умолчанию" : "Наследовать";

  const selectedDisplayName =
    currentValue === "__default__"
      ? defaultChoiceLabel
      : (models?.items.find((m) => m.name === currentValue)?.display_name ??
        currentValue);

  const resolvedDisplayName =
    models?.items.find((m) => m.name === settings?.resolved_model)
      ?.display_name ?? settings?.resolved_model;

  return (
    <div>
      {/* Триггер Base UI — кнопка с `role="combobox"`, а не нативный контрол:
          подпись связывается с ним через `aria-labelledby` (тот же приём, что
          и у селекта транспорта в `features/mcp-servers/ui/MCPServerForm.tsx`).
          Имя контрола — «Модель», текущее значение остаётся содержимым
          триггера. */}
      <span
        id={labelId}
        className="mb-1.5 block text-sm font-medium text-foreground"
      >
        Модель
      </span>
      <Select
        value={currentValue}
        onValueChange={handleChange}
        disabled={updateSettings.isPending}
      >
        <SelectTrigger className="w-full" aria-labelledby={labelId}>
          <SelectValue placeholder={selectedDisplayName}>
            {selectedDisplayName}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__default__">{defaultChoiceLabel}</SelectItem>
          {models?.items.map((m) => (
            <SelectItem key={m.name} value={m.name}>
              {m.display_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {settings && (
        <p className="mt-1 text-xs text-muted-foreground">
          Активная модель: {resolvedDisplayName}
        </p>
      )}
    </div>
  );
}
