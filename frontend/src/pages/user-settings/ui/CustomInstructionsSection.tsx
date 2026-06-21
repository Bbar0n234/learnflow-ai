import { useEffect, useState } from "react";
import { useInstructions } from "@/shared/api/user-memory";
import { useUpdateInstructions } from "@/shared/api/user-memory";
import { Button } from "@/shared/ui/button";
import {
  isSecurityViolation,
  SECURITY_VIOLATION_MESSAGE,
} from "@/shared/lib/security-error";

export function CustomInstructionsSection() {
  const { data } = useInstructions();
  const update = useUpdateInstructions();
  const [content, setContent] = useState("");
  const [dirty, setDirty] = useState(false);

  useEffect(() => {
    if (data) {
      setContent(data.content);
      setDirty(false);
    }
  }, [data]);

  const handleSave = () => {
    update.mutate(content, {
      onSuccess: () => setDirty(false),
    });
  };

  return (
    <div>
      <label className="mb-1.5 block text-sm font-medium text-foreground">
        Свои инструкции
      </label>
      <p className="mb-2 text-xs text-muted-foreground">
        Включаются в каждый разговор с агентом.
      </p>
      <div className="rounded-lg border border-border bg-background">
        <textarea
          className="w-full resize-none bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground"
          rows={6}
          maxLength={5000}
          value={content}
          onChange={(e) => {
            setContent(e.target.value);
            setDirty(true);
          }}
          placeholder="Например: «Всегда отвечай на русском» или «Я старший бэкенд-разработчик…»"
        />
      </div>
      <div className="mt-2 flex items-center gap-2">
        <Button
          size="sm"
          onClick={handleSave}
          disabled={!dirty || update.isPending}
        >
          {update.isPending ? "Сохраняем…" : "Сохранить"}
        </Button>
        <span className="text-xs text-muted-foreground">
          {content.length}/5000
        </span>
      </div>
      {isSecurityViolation(update.error) && (
        <p className="mt-2 text-sm text-destructive">
          {SECURITY_VIOLATION_MESSAGE}
        </p>
      )}
    </div>
  );
}
