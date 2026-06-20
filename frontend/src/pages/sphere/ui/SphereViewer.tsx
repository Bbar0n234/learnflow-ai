import { Pencil } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { Illustration } from "@/shared/ui/Illustration";

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
          <div className="flex flex-col items-center gap-4 py-8">
            <Illustration
              scene="empty-sphere"
              alt="Knowledge sphere is empty"
              className="max-w-[280px] w-full"
            />
            <p className="text-muted-foreground">
              Knowledge sphere is empty. Click the edit button to add content.
            </p>
          </div>
        )}
      </ScrollArea>
    </div>
  );
}
