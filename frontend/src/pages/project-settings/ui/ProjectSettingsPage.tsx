import { useEffect, useId, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router";
import { Check, Pencil, X } from "lucide-react";
import { ModelSelector } from "@/features/model-selector";
import { MCPServersSection } from "@/features/mcp-servers";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import {
  useProject,
  useUpdateProject,
  useDeleteProject,
} from "@/shared/api/projects";

export function ProjectSettingsPage() {
  const { id: projectId } = useParams();
  const navigate = useNavigate();
  const { data: project } = useProject(projectId!);
  const updateProject = useUpdateProject();
  const deleteProject = useDeleteProject();

  // null — режим просмотра: источник истины `project.name` из квери, рендерится
  // напрямую. Не-null — режим редактирования: черновик заводится снапшотом
  // `project.name` в момент входа и живёт независимо от квери до выхода, поэтому
  // внешний rename (модалка сайдбара, вторая вкладка, focus-refetch) меняет
  // только то, что видит просмотр, и не клобберит открытый ввод.
  const [draft, setDraft] = useState<string | null>(null);
  const isEditing = draft !== null;

  // Кадр «старое имя рядом с зелёным „Сохранено“» (правка plan-review 4):
  // между закрытием режима и приходом рефетча `useProject` квери ещё отдаёт
  // старое `project.name`. `confirmed` держит только что записанное имя
  // локально и подменяет им просмотр, пока квери не догонит.
  //
  // Снимается подмена по приходу любых свежих данных, а не по совпадению с
  // записанным именем: рядом с `name` хранится `staleName` — значение квери,
  // поверх которого мы писали, — и как только квери отдаёт что-то другое,
  // локальный кадр уступает серверу. Сравнение «пока не совпадёт с моим»
  // залипало навсегда, если между нашим PUT и нашим же рефетчем проект
  // переименовывал кто-то ещё (вторая вкладка, модалка сайдбара): совпадение
  // не наступало никогда, и страница до перезагрузки показывала наше
  // устаревшее имя (code review A, находка о `confirmedName`).
  const [confirmed, setConfirmed] = useState<{
    name: string;
    staleName: string | undefined;
  } | null>(null);
  const displayName = confirmed !== null ? confirmed.name : project?.name;

  useEffect(() => {
    if (confirmed !== null && project?.name !== confirmed.staleName) {
      setConfirmed(null);
    }
  }, [project?.name, confirmed]);

  // Краткое подтверждение «Сохранено» (мокап, `.pn-saved`, ~1.6с). Таймер
  // хранится в ref, а не в переменной эффекта, — его нужно снимать из двух
  // разных мест (успех новой мутации, повторный вход в редактирование), а не
  // только при размонтировании.
  const [showSaved, setShowSaved] = useState(false);
  const savedTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  function clearSavedTimer() {
    if (savedTimerRef.current !== null) {
      clearTimeout(savedTimerRef.current);
      savedTimerRef.current = null;
    }
  }

  useEffect(() => clearSavedTimer, []);

  const nameInputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const pencilRef = useRef<HTMLButtonElement>(null);
  const focusPencilOnCloseRef = useRef(false);

  useEffect(() => {
    if (isEditing) {
      inputRef.current?.focus();
      inputRef.current?.select();
    } else if (focusPencilOnCloseRef.current) {
      focusPencilOnCloseRef.current = false;
      pencilRef.current?.focus();
    }
  }, [isEditing]);

  function startEdit() {
    if (!project) return;
    // Повторный вход гасит висящее подтверждение прошлого сохранения — иначе
    // его тик мог бы погасить свежее «Сохранено» от следующего коммита.
    clearSavedTimer();
    setShowSaved(false);
    setDraft(displayName ?? project.name);
  }

  function closeEdit() {
    focusPencilOnCloseRef.current = true;
    setDraft(null);
  }

  function cancelEdit() {
    // Мутация в полёте — отмена (Esc / крестик / blur) игнорируется: запись уже
    // ушла и режим закроется только по её результату, не по потере фокуса.
    if (updateProject.isPending) return;
    closeEdit();
  }

  function commitEdit() {
    if (draft === null || !projectId || updateProject.isPending) return;
    const trimmed = draft.trim();
    if (!trimmed) return;
    // Сравнение с показанным именем, а не с `project.name`: пока локальный
    // кадр держит только что записанное имя, Enter без правки не должен
    // отправлять второй PUT с тем же значением.
    if (trimmed === displayName) {
      closeEdit();
      return;
    }
    const staleName = project?.name;
    updateProject.mutate(
      { id: projectId, data: { name: trimmed } },
      {
        onSuccess: () => {
          setConfirmed({ name: trimmed, staleName });
          closeEdit();
          clearSavedTimer();
          setShowSaved(true);
          savedTimerRef.current = setTimeout(() => setShowSaved(false), 1600);
        },
      },
    );
  }

  function handleDelete() {
    if (!projectId) return;
    deleteProject.mutate(projectId, {
      onSuccess: () => navigate("/"),
    });
  }

  return (
    <div className="mx-auto max-w-[640px] px-6 py-8">
      <h2 className="mb-6 font-serif text-xl font-semibold text-foreground">
        Настройки проекта
      </h2>
      <div className="space-y-4">
        <section className="rounded-xl border border-border bg-card p-5">
          <ModelSelector scope="project" projectId={projectId} />
        </section>

        <section className="rounded-xl border border-border bg-card p-5">
          <MCPServersSection scope="project" projectId={projectId} />
        </section>

        <section className="rounded-xl border border-border bg-card p-5">
          {/* Подпись — `<label htmlFor>` только там, где есть что подписывать:
              поле существует лишь в режиме редактирования. В просмотре на его
              месте статический текст с карандашом (у кнопки свой `aria-label`),
              поэтому подпись рендерится обычным абзацем, а не `<label>` с
              висящим `for`, который ни к какому контролу не ведёт. */}
          {draft === null ? (
            <p className="mb-1.5 text-sm font-medium text-foreground">
              Имя проекта
            </p>
          ) : (
            <label
              htmlFor={nameInputId}
              className="mb-1.5 block text-sm font-medium text-foreground"
            >
              Имя проекта
            </label>
          )}
          {draft === null ? (
            <div className="flex min-h-8 items-center gap-2">
              <span className="text-sm font-medium text-foreground">
                {displayName}
              </span>
              <Button
                ref={pencilRef}
                type="button"
                variant="ghost"
                size="icon-sm"
                aria-label="Переименовать проект"
                title="Переименовать проект"
                onClick={startEdit}
              >
                <Pencil className="size-3.5" />
              </Button>
              {showSaved && (
                <span
                  role="status"
                  className="inline-flex items-center gap-1 text-xs text-success"
                >
                  <Check className="size-3.5" />
                  Сохранено
                </span>
              )}
            </div>
          ) : (
            <div className="flex min-h-8 items-center gap-2">
              <Input
                ref={inputRef}
                id={nameInputId}
                className="flex-1"
                value={draft}
                maxLength={100}
                disabled={updateProject.isPending}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={cancelEdit}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    commitEdit();
                  } else if (e.key === "Escape") {
                    e.preventDefault();
                    cancelEdit();
                  }
                }}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="hover:text-success"
                aria-label="Сохранить"
                title="Сохранить (Enter)"
                disabled={updateProject.isPending || !draft.trim()}
                onMouseDown={(e) => e.preventDefault()}
                onClick={commitEdit}
              >
                <Check />
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                className="hover:text-destructive"
                aria-label="Отменить"
                title="Отменить (Esc)"
                disabled={updateProject.isPending}
                onMouseDown={(e) => e.preventDefault()}
                onClick={cancelEdit}
              >
                <X />
              </Button>
            </div>
          )}
          <p className="mt-1 text-xs text-muted-foreground">
            Клик по карандашу — редактирование · Enter — сохранить · Esc —
            отменить
          </p>
        </section>

        <section className="rounded-xl border border-border bg-card p-5">
          <p className="mb-0.5 text-sm font-medium text-foreground">
            Удалить проект
          </p>
          <p className="mb-3 text-xs text-muted-foreground">
            Необратимо — все чаты, артефакты и данные сферы будут потеряны.
          </p>
          <button
            onClick={handleDelete}
            disabled={deleteProject.isPending}
            className="text-sm text-destructive-warm underline-offset-2 hover:underline disabled:opacity-50"
          >
            {deleteProject.isPending ? "Удаляем…" : "Удалить проект…"}
          </button>
        </section>
      </div>
    </div>
  );
}
