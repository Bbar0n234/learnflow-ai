import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { ArrowLeft, Settings2 } from "lucide-react";
import { useProject } from "@/features/projects/hooks/useProject";
import { ModelSelector } from "@/features/settings/components/ModelSelector";
import { MCPServersSection } from "@/features/settings/components/MCPServersSection";
import { Button } from "@/shared/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/ui/dialog";

export function ChatHeader() {
  const { id: projectId, cid: threadId } = useParams();
  const navigate = useNavigate();
  const { data: project } = useProject(projectId!);
  const [toolsOpen, setToolsOpen] = useState(false);

  return (
    <div className="border-b border-border px-4 py-2">
      <button
        onClick={() => navigate(`/projects/${projectId}`)}
        className="mb-1 flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        <span>{project?.name ?? "Project"}</span>
      </button>
      <div className="flex items-center gap-2">
        <div className="w-64">
          <ModelSelector
            scope="thread"
            projectId={projectId}
            threadId={threadId}
          />
        </div>
        <Dialog open={toolsOpen} onOpenChange={setToolsOpen}>
          <DialogTrigger
            render={
              <Button variant="ghost" size="icon-sm" title="Chat tools">
                <Settings2 className="h-4 w-4" />
              </Button>
            }
          />
          <DialogContent className="sm:max-w-md">
            <DialogHeader>
              <DialogTitle>Chat Tools</DialogTitle>
            </DialogHeader>
            <MCPServersSection
              scope="thread"
              projectId={projectId}
              threadId={threadId}
            />
          </DialogContent>
        </Dialog>
      </div>
    </div>
  );
}
