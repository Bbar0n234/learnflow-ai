import { useState } from "react";
import { Button } from "@/shared/ui/button";
import { Textarea } from "@/shared/ui/textarea";
import {
  isSecurityViolation,
  SECURITY_VIOLATION_MESSAGE,
} from "@/shared/lib/security-error";
import { getApiErrorMessage } from "@/shared/lib/api-error";

interface SphereEditorProps {
  content: string;
  isPending: boolean;
  error: unknown;
  onSave: (content: string) => void;
  onCancel: () => void;
}

export function SphereEditor({
  content,
  isPending,
  error,
  onSave,
  onCancel,
}: SphereEditorProps) {
  const [text, setText] = useState(content);

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex h-[56px] shrink-0 items-center justify-between border-b border-border px-6">
        <h2 className="font-serif text-lg font-semibold text-foreground">
          Редактировать сферу
        </h2>
        <div className="flex gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={onCancel}
            disabled={isPending}
          >
            Отмена
          </Button>
          <Button size="sm" onClick={() => onSave(text)} disabled={isPending}>
            {isPending ? "Сохраняется…" : "Сохранить"}
          </Button>
        </div>
      </div>

      {/* Editor area */}
      <div className="flex flex-1 flex-col p-6">
        {isSecurityViolation(error) ? (
          <p className="mb-2 text-sm text-destructive">
            {SECURITY_VIOLATION_MESSAGE}
          </p>
        ) : error ? (
          <p className="mb-2 text-sm text-destructive">
            {getApiErrorMessage(error)}
          </p>
        ) : null}
        <div className="flex flex-1 flex-col rounded-xl border border-border bg-card shadow-none">
          <Textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="h-full min-h-[300px] flex-1 resize-none rounded-xl border-0 bg-transparent font-mono text-sm focus-visible:ring-0 focus-visible:ring-offset-0"
            placeholder="Напишите содержимое сферы знаний в формате Markdown…"
            disabled={isPending}
          />
        </div>
      </div>
    </div>
  );
}
