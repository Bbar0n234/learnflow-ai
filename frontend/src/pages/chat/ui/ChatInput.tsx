import { useState, type KeyboardEvent } from "react";
import { SendHorizontal, Square } from "lucide-react";
import { Textarea } from "@/shared/ui/textarea";

interface ChatInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  isStreaming?: boolean;
  onCancel?: () => void;
  placeholder?: string;
  // Controlled value pair — optional. Uncontrolled callers (default: existing
  // chat) keep the previous behaviour (internal state, cleared on send).
  // The draft composer (T2.6) passes these to keep the typed text on a
  // failed `POST /chats`: clearing happens only via internal state, so a
  // controlled parent decides when (or whether) to reset it.
  value?: string;
  onValueChange?: (value: string) => void;
}

export function ChatInput({
  onSend,
  disabled,
  isStreaming,
  onCancel,
  placeholder,
  value: controlledValue,
  onValueChange,
}: ChatInputProps) {
  const [internalValue, setInternalValue] = useState("");
  const isControlled = controlledValue !== undefined;
  const value = isControlled ? controlledValue : internalValue;

  const trimmed = value.trim();

  function setValue(next: string) {
    if (isControlled) {
      onValueChange?.(next);
    } else {
      setInternalValue(next);
    }
  }

  function handleSend() {
    if (!trimmed) return;
    onSend(trimmed);
    // Uncontrolled: always clear after dispatch (existing chat behaviour).
    // Controlled: leave clearing to the parent — the draft composer never
    // clears on error, so the message isn't lost.
    if (!isControlled) setInternalValue("");
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
