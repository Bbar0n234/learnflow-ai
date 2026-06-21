import { Pencil } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { Illustration } from "@/shared/ui/Illustration";
import { SaveVersionDropdown } from "./SaveVersionDropdown";
import { SHOW_GROUP_B_STUBS } from "@/shared/config/feature-flags";

interface SphereViewerProps {
  content: string;
  onEdit: () => void;
}

export function SphereViewer({ content, onEdit }: SphereViewerProps) {
  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex h-[56px] shrink-0 items-center justify-between border-b border-border px-6">
        <h2 className="font-serif text-lg font-semibold text-foreground">
          Сфера знаний
        </h2>
        <div className="flex items-center gap-2">
          {SHOW_GROUP_B_STUBS && <SaveVersionDropdown />}
          <Button
            variant="outline"
            size="sm"
            onClick={onEdit}
            className="border-ring/60 text-ring hover:bg-accent hover:text-accent-foreground"
          >
            <Pencil className="h-3.5 w-3.5" />
            Редактировать
          </Button>
        </div>
      </div>

      {/* Content */}
      <ScrollArea className="flex-1 px-6 py-6">
        {content ? (
          <div className="sphere-prose max-w-[680px]">
            <MarkdownRenderer>{content}</MarkdownRenderer>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-4 py-8">
            <Illustration
              scene="empty-sphere"
              alt="Knowledge sphere is empty"
              className="w-full max-w-[280px]"
            />
            <p className="text-center text-sm text-muted-foreground">
              Сфера знаний пуста. Нажмите «Редактировать», чтобы добавить
              содержимое.
            </p>
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
