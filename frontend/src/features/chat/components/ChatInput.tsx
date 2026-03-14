import { useState, type KeyboardEvent } from "react";
import { SendHorizontal } from "lucide-react";
import { Textarea } from "@/shared/ui/textarea";
import { Button } from "@/shared/ui/button";

interface ChatInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
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
          placeholder="Type a message..."
          disabled={disabled}
          className="min-h-10 resize-none"
        />
        <Button
          size="icon"
          onClick={handleSend}
          disabled={disabled || !trimmed}
        >
          <SendHorizontal className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
