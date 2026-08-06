import { useState } from "react";
import { ChevronDown, Pencil, Trash2 } from "lucide-react";
import {
  useSkillContexts,
  useUpdateSkillContext,
  useDeleteSkillContext,
  type SkillContextDocument,
  type SkillGroup,
} from "@/shared/api/skill-context";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { MarkdownRenderer } from "@/shared/ui/MarkdownRenderer";
import { cn } from "@/shared/lib/utils";
import {
  isSecurityViolation,
  SECURITY_VIOLATION_MESSAGE,
} from "@/shared/lib/security-error";

/** Русская плюрализация: 1 скилл / 2 скилла / 5 скиллов. */
function pluralizeRu(n: number, one: string, few: string, many: string) {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 10 || mod100 >= 20)) return few;
  return many;
}

function SkillDocumentRow({
  skillName,
  document,
}: {
  skillName: string;
  document: SkillContextDocument;
}) {
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draftContent, setDraftContent] = useState(document.content);
  const update = useUpdateSkillContext();
  const remove = useDeleteSkillContext();

  const toggleOpen = () => {
    if (open) {
      setEditing(false);
      update.reset();
    }
    setOpen(!open);
  };

  const handleEdit = () => {
    setDraftContent(document.content);
    setEditing(true);
  };

  const handleCancel = () => {
    setEditing(false);
    update.reset();
  };

  const handleSave = () => {
    update.mutate(
      {
        skillName,
        key: document.key,
        payload: { description: document.description, content: draftContent },
      },
      { onSuccess: () => setEditing(false) },
    );
  };

  const handleDelete = () => {
    remove.mutate({ skillName, key: document.key });
  };

  return (
    <div className="border-t border-border first:border-t-0">
      <button
        type="button"
        aria-expanded={open}
        onClick={toggleOpen}
        className="flex w-full items-start gap-2 px-3 py-2.5 text-left hover:bg-muted focus-visible:-outline-offset-2 focus-visible:outline-2 focus-visible:outline-ring"
      >
        <div className="min-w-0 flex-1">
          <span className="font-mono text-sm font-medium text-foreground">
            {document.key}
          </span>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {document.description}
          </p>
        </div>
        <ChevronDown
          className={cn(
            "mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180",
          )}
        />
      </button>
      {open && (
        <div className="px-3 pb-3">
          {editing ? (
            <div className="rounded-lg border border-border bg-background p-3">
              <textarea
                aria-label={`Документ ${document.key} (Markdown)`}
                className="h-40 w-full resize-none rounded-md border border-border bg-transparent p-2 font-mono text-xs outline-none focus-visible:border-ring"
                value={draftContent}
                onChange={(e) => setDraftContent(e.target.value)}
              />
              <div className="mt-2 flex items-center gap-2">
                <Button
                  size="sm"
                  onClick={handleSave}
                  disabled={update.isPending}
                >
                  {update.isPending ? "Сохраняем…" : "Сохранить"}
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCancel}
                  disabled={update.isPending}
                >
                  Отмена
                </Button>
              </div>
              {isSecurityViolation(update.error) && (
                <p className="mt-2 text-sm text-destructive">
                  {SECURITY_VIOLATION_MESSAGE}
                </p>
              )}
            </div>
          ) : (
            <>
              <div className="max-h-80 overflow-y-auto rounded-lg border border-border bg-card p-3">
                <div className="sphere-prose text-sm">
                  <MarkdownRenderer>{document.content}</MarkdownRenderer>
                </div>
              </div>
              <div className="mt-2 flex items-center gap-2">
                <Button variant="ghost" size="sm" onClick={handleEdit}>
                  <Pencil /> Править
                </Button>
                <Button
                  variant="destructive"
                  size="sm"
                  onClick={handleDelete}
                  disabled={remove.isPending}
                >
                  <Trash2 /> Удалить
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SkillGroupCard({ group }: { group: SkillGroup }) {
  return (
    <div className="rounded-lg border border-border bg-background">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
        <span className="font-mono text-sm font-medium text-foreground">
          {group.skill_name}
        </span>
        {!group.in_library && (
          <Badge className="border-dashed border-muted-foreground/50 bg-transparent text-[0.65rem] font-normal text-muted-foreground">
            скилла нет в библиотеке
          </Badge>
        )}
      </div>
      <div>
        {group.documents.map((doc) => (
          <SkillDocumentRow
            key={doc.key}
            skillName={group.skill_name}
            document={doc}
          />
        ))}
      </div>
    </div>
  );
}

export function SkillContextSection() {
  const { data, isLoading } = useSkillContexts();

  if (isLoading) {
    return (
      <p className="text-sm text-muted-foreground">
        Загрузка контекста скиллов…
      </p>
    );
  }

  const groups = (data?.skills ?? []).filter((g) => g.documents.length > 0);
  const totalDocs = groups.reduce((n, g) => n + g.documents.length, 0);

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between">
        <label className="text-sm font-medium text-foreground">
          Контекст скиллов
        </label>
        {totalDocs > 0 && (
          <span className="text-xs text-muted-foreground">
            {groups.length}{" "}
            {pluralizeRu(groups.length, "скилл", "скилла", "скиллов")} ·{" "}
            {totalDocs}{" "}
            {pluralizeRu(totalDocs, "документ", "документа", "документов")}
          </span>
        )}
      </div>
      <p className="mb-3 text-xs text-muted-foreground">
        Личные материалы, которые скиллы используют в работе: профили стиля,
        образцы, предпочтения. Создаёт их агент по ходу работы — здесь их можно
        просмотреть, поправить или удалить.
      </p>
      {groups.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          Пока пусто. Скиллы будут сохранять сюда ваши профили и предпочтения по
          ходу работы.
        </p>
      ) : (
        <div className="space-y-2">
          {groups.map((group) => (
            <SkillGroupCard key={group.skill_name} group={group} />
          ))}
        </div>
      )}
    </div>
  );
}
