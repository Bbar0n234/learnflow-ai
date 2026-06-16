import { Pencil } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";

interface SphereViewerProps {
  content: string;
  onEdit: () => void;
}

export function SphereViewer({ content, onEdit }: SphereViewerProps) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-6 py-3">
        <h2 className="text-lg font-semibold">Knowledge Sphere</h2>
        <Button variant="ghost" size="icon" onClick={onEdit}>
          <Pencil className="h-4 w-4" />
        </Button>
      </div>
      <ScrollArea className="flex-1 px-6 py-4">
        {content ? (
          <MarkdownRenderer>{content}</MarkdownRenderer>
        ) : (
          <p className="text-muted-foreground">
            Knowledge sphere is empty. Click the edit button to add content.
          </p>
        )}
      </ScrollArea>
    </div>
  );
}
