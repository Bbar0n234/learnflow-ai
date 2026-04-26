import { useState, type KeyboardEvent } from "react";
import { SendHorizontal, Square } from "lucide-react";
import { Textarea } from "@/shared/ui/textarea";
import { Button } from "@/shared/ui/button";

interface ChatInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  isStreaming?: boolean;
  onCancel?: () => void;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  disabled,
  isStreaming,
  onCancel,
  placeholder,
}: ChatInputProps) {
  const [value, setValue] = useState("");

  const trimmed = value.trim();

  function handleSend() {
    if (!trimmed) return;
    onSend(trimmed);
    setValue("");
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  return (
    <div className="border-t border-border p-4">
      <div className="mx-auto flex max-w-3xl gap-2">
        <Textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder ?? "Type a message..."}
          disabled={disabled || isStreaming}
          className="min-h-10 resize-none"
        />
        {isStreaming ? (
          <Button size="icon" variant="destructive" onClick={onCancel}>
            <Square className="h-4 w-4" />
          </Button>
        ) : (
          <Button
            size="icon"
            onClick={handleSend}
            disabled={disabled || !trimmed}
          >
            <SendHorizontal className="h-4 w-4" />
          </Button>
        )}
      </div>
    </div>
  );
}
