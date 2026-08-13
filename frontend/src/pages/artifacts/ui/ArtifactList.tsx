import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import {
  ChevronRight,
  FileText,
  Folder,
  Image as ImageIcon,
} from "lucide-react";
import { Illustration } from "@/shared/ui/Illustration";
import { useArtifacts, type Artifact } from "@/shared/api/artifacts";
import { getArtifactCategory } from "@/shared/lib/artifact-category";
import { cn } from "@/shared/lib/utils";

// Бэкенд отдаёт плоский `ListResponse<Artifact>` (id артефакта = путь,
// ADR-032) — дерево строит фронт. Директории — раскрывающиеся группы
// (счётчик = все файлы в поддереве, не только прямые потомки), файлы корня
// `artifacts/` — плоские строки. Сортировка: директории по имени, файлы
// внутри группы (включая корень) — по `updated_at`, новые сверху.

interface DirTreeNode {
  kind: "dir";
  name: string;
  path: string;
  children: TreeNode[];
  fileCount: number;
}

interface FileTreeNode {
  kind: "file";
  artifact: Artifact;
}

type TreeNode = DirTreeNode | FileTreeNode;

interface MutableDir {
  name: string;
  files: Artifact[];
  subdirs: Map<string, MutableDir>;
}

function countFiles(nodes: TreeNode[]): number {
  return nodes.reduce(
    (sum, node) => sum + (node.kind === "file" ? 1 : node.fileCount),
    0,
  );
}

function toTreeNodes(dir: MutableDir, parentPath: string): TreeNode[] {
  const dirNodes: DirTreeNode[] = Array.from(dir.subdirs.values())
    .sort((a, b) => a.name.localeCompare(b.name))
    .map((sub) => {
      const path = parentPath ? `${parentPath}/${sub.name}` : sub.name;
      const children = toTreeNodes(sub, path);
      return {
        kind: "dir" as const,
        name: sub.name,
        path,
        children,
        fileCount: countFiles(children),
      };
    });

  const fileNodes: FileTreeNode[] = [...dir.files]
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .map((artifact) => ({ kind: "file" as const, artifact }));

  return [...dirNodes, ...fileNodes];
}

/** Группирует плоский список путей в дерево директорий произвольной глубины. */
function buildArtifactTree(items: Artifact[]): TreeNode[] {
  const root: MutableDir = { name: "", files: [], subdirs: new Map() };

  for (const artifact of items) {
    const segments = artifact.path.split("/");
    const dirSegments = segments.slice(0, -1);
    let dir = root;
    for (const segment of dirSegments) {
      let next = dir.subdirs.get(segment);
      if (!next) {
        next = { name: segment, files: [], subdirs: new Map() };
        dir.subdirs.set(segment, next);
      }
      dir = next;
    }
    dir.files.push(artifact);
  }

  return toTreeNodes(root, "");
}

/** Пути директорий-предков файла: "a/b/c.md" → ["a", "a/b"]. */
function ancestorDirs(path: string): string[] {
  const dirSegments = path.split("/").slice(0, -1);
  const dirs: string[] = [];
  let acc = "";
  for (const segment of dirSegments) {
    acc = acc ? `${acc}/${segment}` : segment;
    dirs.push(acc);
  }
  return dirs;
}

function artifactHref(projectId: string, path: string): string {
  return `/projects/${projectId}/artifacts?${new URLSearchParams({ path })}`;
}

/** Иконка строки файла по категории словаря (T2.2) — вьюер, список, карточка чата используют один и тот же словарь. */
function ArtifactRowIcon({ type }: { type: string }) {
  const cls = "h-[18px] w-[18px] shrink-0 text-muted-foreground";
  return getArtifactCategory(type) === "image" ? (
    <ImageIcon className={cls} />
  ) : (
    <FileText className={cls} />
  );
}

function ArtifactFileRow({
  artifact,
  projectId,
  isSelected,
}: {
  artifact: Artifact;
  projectId: string;
  isSelected: boolean;
}) {
  return (
    <Link
      to={artifactHref(projectId, artifact.path)}
      className={cn(
        "flex items-center gap-3 rounded-lg px-3 py-2.5 transition-colors",
        isSelected
          ? "border border-secondary bg-secondary/30 [border-left-color:var(--ring)] [border-left-width:3px]"
          : "hover:bg-muted",
      )}
    >
      {/* Type icon container — 36px */}
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-muted">
        <ArtifactRowIcon type={artifact.type} />
      </div>

      {/* Title + type · дата обновления */}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-foreground">
          {artifact.title}
        </p>
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {artifact.type}
          {" · изменён "}
          {new Date(artifact.updated_at).toLocaleDateString("ru-RU")}
        </p>
      </div>
    </Link>
  );
}

function ArtifactDirRow({
  node,
  projectId,
  selectedPath,
  expandedDirs,
  onToggle,
}: {
  node: DirTreeNode;
  projectId: string;
  selectedPath: string | undefined;
  expandedDirs: ReadonlySet<string>;
  onToggle: (path: string) => void;
}) {
  const isOpen = expandedDirs.has(node.path);

  return (
    <div className="flex flex-col gap-0.5">
      <button
        type="button"
        onClick={() => onToggle(node.path)}
        aria-expanded={isOpen}
        className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-foreground transition-colors hover:bg-muted"
      >
        <ChevronRight
          className={cn(
            "h-[13px] w-[13px] shrink-0 text-muted-foreground transition-transform",
            isOpen && "rotate-90",
          )}
        />
        <Folder className="h-[17px] w-[17px] shrink-0 text-muted-foreground" />
        <span className="truncate text-sm font-medium">{node.name}</span>
        <span className="ml-auto shrink-0 text-xs text-muted-foreground">
          {node.fileCount}
        </span>
      </button>

      {isOpen && (
        <div className="flex flex-col gap-0.5 pl-[1.35rem]">
          <ArtifactTree
            nodes={node.children}
            projectId={projectId}
            selectedPath={selectedPath}
            expandedDirs={expandedDirs}
            onToggle={onToggle}
          />
        </div>
      )}
    </div>
  );
}

function ArtifactTree({
  nodes,
  projectId,
  selectedPath,
  expandedDirs,
  onToggle,
}: {
  nodes: TreeNode[];
  projectId: string;
  selectedPath: string | undefined;
  expandedDirs: ReadonlySet<string>;
  onToggle: (path: string) => void;
}) {
  return (
    <>
      {nodes.map((node) =>
        node.kind === "dir" ? (
          <ArtifactDirRow
            key={node.path}
            node={node}
            projectId={projectId}
            selectedPath={selectedPath}
            expandedDirs={expandedDirs}
            onToggle={onToggle}
          />
        ) : (
          <ArtifactFileRow
            key={node.artifact.path}
            artifact={node.artifact}
            projectId={projectId}
            isSelected={node.artifact.path === selectedPath}
          />
        ),
      )}
    </>
  );
}

export function ArtifactList() {
  const { id } = useParams();
  const [searchParams] = useSearchParams();
  const selectedPath = searchParams.get("path") ?? undefined;
  const { data, isLoading, isError } = useArtifacts(id);

  const tree = useMemo(() => buildArtifactTree(data?.items ?? []), [data]);

  // Раскрытие/схлопывание — локальное состояние панели, серверных данных в
  // сторе не держим (§ Ось состояния). Директория предка выбранного файла
  // авто-раскрывается при смене `?path=` (переход из карточки чата,
  // перезагрузка страницы) — дальше пользователь схлопывает/раскрывает
  // группы вручную, эффект их обратно не закрывает.
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(
    () => new Set(),
  );

  useEffect(() => {
    if (!selectedPath) return;
    const dirs = ancestorDirs(selectedPath);
    if (dirs.length === 0) return;
    setExpandedDirs((prev) => {
      const missing = dirs.filter((dir) => !prev.has(dir));
      if (missing.length === 0) return prev;
      return new Set([...prev, ...missing]);
    });
  }, [selectedPath]);

  const toggleDir = (path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  return (
    <div className="flex h-full flex-col">
      {/* Panel header */}
      <div className="flex h-[56px] shrink-0 items-center border-b border-border px-4">
        <h2 className="font-serif text-base font-semibold text-foreground">
          Артефакты
        </h2>
      </div>

      {/* List body */}
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {isLoading && (
          <p className="px-3 py-2 text-sm text-muted-foreground">Загрузка…</p>
        )}
        {isError && (
          <p className="px-3 py-2 text-sm text-destructive">
            Ошибка загрузки артефактов.
          </p>
        )}

        {data && data.items.length === 0 && (
          <div className="flex flex-col items-center gap-4 px-4 py-8">
            <Illustration
              scene="empty-artifacts"
              alt="No artifacts yet"
              className="w-full max-w-[200px]"
            />
            <p className="text-center text-sm text-muted-foreground">
              Артефактов пока нет. Они появятся по мере работы ИИ.
            </p>
          </div>
        )}

        {data && data.items.length > 0 && (
          <div className="flex flex-col gap-0.5">
            <ArtifactTree
              nodes={tree}
              projectId={id!}
              selectedPath={selectedPath}
              expandedDirs={expandedDirs}
              onToggle={toggleDir}
            />
          </div>
        )}
      </div>
    </div>
  );
}
