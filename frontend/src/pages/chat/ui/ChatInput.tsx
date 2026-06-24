import { useState, type KeyboardEvent } from "react";
import { SendHorizontal, Square } from "lucide-react";
import { Textarea } from "@/shared/ui/textarea";

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
    <div className="px-4 pb-4 pt-3">
      <div
        className="mx-auto rounded-[var(--radius)] bg-card"
        style={{
          maxWidth: "var(--content-max-w)",
          boxShadow: "var(--shadow-input)",
        }}
      >
        <div className="flex items-end gap-2 p-3">
          <Textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder ?? "Сообщение..."}
            disabled={disabled || isStreaming}
            className="min-h-10 resize-none border-0 shadow-none focus-visible:ring-0 dark:bg-transparent"
          />
          {isStreaming ? (
            <button
              type="button"
              onClick={onCancel}
              aria-label="Отменить"
              className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-destructive text-destructive-foreground transition-colors hover:bg-destructive/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1"
            >
              <Square className="h-3.5 w-3.5" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSend}
              disabled={disabled || !trimmed}
              aria-label="Отправить"
              className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-40"
            >
              <SendHorizontal className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
