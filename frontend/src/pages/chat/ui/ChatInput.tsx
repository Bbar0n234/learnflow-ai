import { useRef, useState, type ChangeEvent, type KeyboardEvent } from "react";
import { Paperclip, SendHorizontal, Square } from "lucide-react";
import { Textarea } from "@/shared/ui/textarea";
import { AttachmentChip } from "@/shared/ui/AttachmentChip";
import { DragOverlay } from "@/shared/ui/DragOverlay";
import { useComposerAttachments } from "@/shared/lib/use-composer-attachments";
import { useFileDrop } from "@/shared/lib/use-file-drop";

interface ChatInputProps {
  // Второй параметр — файлы, прикреплённые в композере (T2.8, § Вложения
  // пользователя): пусто, когда вложений нет — сигнатура одна на оба случая,
  // а не перегрузка. Возврат — признак успеха отправки: `false` (или
  // отклонённый промис) держит текст и чипы в композере вместо их сброса
  // (§ Тайминг: ошибка загрузки не должна стирать то, что пользователь уже
  // набрал и прикрепил). `void`/`undefined` — как «успех», для обратной
  // совместимости с вызовами без вложений.
  onSend: (content: string, files: File[]) => void | Promise<boolean>;
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
  // Идёт отправка: захватывает окно между кликом «Отправить» и резолвом
  // `onSend` — то есть, при наличии вложений, время их загрузки (до самого
  // `send()`, который лишь заводит стрим и возвращается сразу). `isStreaming`
  // это окно не покрывает: он становится `true` только после того, как
  // `send()` уже вызван.
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const {
    attachments,
    addFiles,
    removeAttachment,
    clear: clearAttachments,
  } = useComposerAttachments();
  const { isDragging, dragHandlers } = useFileDrop(addFiles);

  const isControlled = controlledValue !== undefined;
  const value = isControlled ? controlledValue : internalValue;

  const trimmed = value.trim();
  const hasContent = trimmed.length > 0 || attachments.length > 0;
  const isDisabled = disabled || isStreaming || busy;

  function setValue(next: string) {
    if (isControlled) {
      onValueChange?.(next);
    } else {
      setInternalValue(next);
    }
  }

  async function handleSend() {
    if (!hasContent || isDisabled) return;
    const files = attachments.map((a) => a.file);
    setBusy(true);
    const ok = await onSend(trimmed, files);
    setBusy(false);
    // Отправка допустима при пустом тексте, если есть вложения (§ Тайминг) —
    // `trimmed` тогда пустая строка, `onSend` сам решает, что с ней делать.
    if (ok === false) return;
    // Uncontrolled: always clear after a successful dispatch (existing chat
    // behaviour). Controlled: leave clearing to the parent — the draft
    // composer never clears on error, so the message isn't lost.
    if (!isControlled) setInternalValue("");
    clearAttachments();
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  }

  function handleFileInputChange(e: ChangeEvent<HTMLInputElement>) {
    if (e.target.files) addFiles(e.target.files);
    // Тот же файл повторно даёт `change` только после сброса значения.
    e.target.value = "";
  }

  return (
    <div className="px-4 pb-4 pt-3">
      <div
        className="relative mx-auto rounded-[var(--radius)] bg-card"
        style={{
          maxWidth: "var(--content-max-w)",
          boxShadow: "var(--shadow-input)",
        }}
        {...dragHandlers}
      >
        {isDragging && <DragOverlay />}
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 px-3 pt-3">
            {attachments.map((a) => (
              <AttachmentChip
                key={a.id}
                name={a.file.name}
                size={a.file.size}
                uploading={busy}
                onRemove={() => removeAttachment(a.id)}
              />
            ))}
          </div>
        )}
        <div className="flex items-end gap-2 p-3">
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={isDisabled}
            aria-label="Прикрепить файл"
            title="Прикрепить файл"
            className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 disabled:pointer-events-none disabled:opacity-40"
          >
            <Paperclip className="h-4 w-4" />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            hidden
            onChange={handleFileInputChange}
          />
          <Textarea
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder ?? "Сообщение..."}
            disabled={isDisabled}
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
              onClick={() => void handleSend()}
              disabled={disabled || busy || !hasContent}
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
