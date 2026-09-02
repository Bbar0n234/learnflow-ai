import { Pencil } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { StateScreen } from "@/shared/ui/StateScreen";
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
      <ScrollArea className="min-h-0 flex-1 px-6 py-6">
        {content ? (
          <div className="sphere-prose max-w-[680px]">
            <MarkdownRenderer>{content}</MarkdownRenderer>
          </div>
        ) : (
          <StateScreen
            scene="empty-sphere"
            alt="Иллюстрация: пустая сфера знаний"
            illustrationClassName="max-w-[440px]"
            description="Сфера знаний пуста — здесь будет накапливаться память проекта."
            action={
              <Button
                variant="outline"
                size="sm"
                onClick={onEdit}
                className="border-ring/60 text-ring hover:bg-accent hover:text-accent-foreground"
              >
                <Pencil className="h-3.5 w-3.5" />
                Редактировать
              </Button>
            }
            className="h-full"
          />
        )}
      </ScrollArea>
    </div>
  );
}
