import { File, X } from "lucide-react";
import { formatFileSize } from "@/shared/lib/use-composer-attachments";
import { cn } from "@/shared/lib/utils";

interface AttachmentChipProps {
  name: string;
  size: number;
  /** Идёт upload этого чипа — полоса прогресса, ✕ выключена (§ Тайминг). */
  uploading?: boolean;
  onRemove?: () => void;
}

/**
 * Чип вложения композера (мокап `mockups/attachments-artifacts.html`, блок 1,
 * `.chip`). Отдельная сущность от истории (`MessageItem.tsx` рисует свой
 * `.hchip`-ряд из `message.attachments`): у композерного чипа есть размер и
 * кнопка ✕, которых нет и не будет у чипа истории (некликабелен, без
 * размера — контракт `MessageOut` его не отдаёт).
 */
export function AttachmentChip({
  name,
  size,
  uploading,
  onRemove,
}: AttachmentChipProps) {
  return (
    <span
      className={cn(
        "relative flex max-w-[230px] items-center gap-1.5 overflow-hidden rounded-md border border-border bg-muted py-1.5 pl-2 pr-1.5 text-xs",
        uploading && "opacity-75",
      )}
    >
      <File className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <span className="truncate">{name}</span>
      <span className="shrink-0 text-[0.69rem] text-muted-foreground">
        {formatFileSize(size)}
      </span>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          disabled={uploading}
          aria-label={`Убрать ${name}`}
          className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:bg-muted-foreground/15 hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
        >
          <X className="h-3 w-3" />
        </button>
      )}
      <span
        aria-hidden
        className="absolute inset-x-0 bottom-0 h-0.5 bg-primary transition-[width] duration-700 ease-out"
        style={{ width: uploading ? "100%" : "0%" }}
      />
    </span>
  );
}
