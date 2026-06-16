import { useState } from "react";
import { Button } from "@/shared/ui/button";
import { Textarea } from "@/shared/ui/textarea";
import {
  isSecurityViolation,
  SECURITY_VIOLATION_MESSAGE,
} from "@/shared/lib/security-error";

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
  const showSecurityError = isSecurityViolation(error);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-3">
        <h2 className="text-lg font-semibold">Edit Knowledge Sphere</h2>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onCancel} disabled={isPending}>
            Cancel
          </Button>
          <Button onClick={() => onSave(text)} disabled={isPending}>
            {isPending ? "Saving..." : "Save"}
          </Button>
        </div>
      </div>
      <div className="flex flex-1 flex-col p-6">
        {showSecurityError && (
          <p className="mb-2 text-sm text-destructive">
            {SECURITY_VIOLATION_MESSAGE}
          </p>
        )}
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          className="h-full min-h-[300px] resize-none font-mono text-sm"
          placeholder="Write your knowledge sphere content in Markdown..."
          disabled={isPending}
        />
      </div>
    </div>
  );
}
