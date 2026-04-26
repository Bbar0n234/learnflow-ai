import { useEffect, useState } from "react";
import { useInstructions } from "../hooks/useInstructions";
import { useUpdateInstructions } from "../hooks/useUpdateInstructions";
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
      <label className="mb-1 block text-sm font-medium">
        Custom Instructions
      </label>
      <p className="mb-2 text-xs text-muted-foreground">
        These instructions are included in every conversation.
      </p>
      <textarea
        className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
        rows={6}
        maxLength={5000}
        value={content}
        onChange={(e) => {
          setContent(e.target.value);
          setDirty(true);
        }}
        placeholder="E.g., 'Always respond in Russian' or 'I'm a senior backend developer...'"
      />
      <div className="mt-2 flex items-center gap-2">
        <Button
          size="sm"
          onClick={handleSave}
          disabled={!dirty || update.isPending}
        >
          {update.isPending ? "Saving..." : "Save"}
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
