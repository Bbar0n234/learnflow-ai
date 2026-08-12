"""File layer for the per-project workspace (ADR-032).

Single point of contact with the two filesystem roots the agent and REST
layer are allowed to touch: the project's workspace (``<workspaces_root>/
{project_id}``, read-write) and the shared skills library (``<skills_root>``,
read-only). Every path an agent/REST caller supplies is canonicalized
(``resolve()``) and checked with ``is_relative_to()`` against the canonicalized
roots before any filesystem call — the same two-layer pattern already proven
in ``agent/tools/skills.py`` (``load_skill``), generalized to two roots and a
write/read distinction.

Consumers: the agent's file tools (``read_file``/``write_file``/``list_files``),
the execution tools (``execute_code``/``run_command``), ``load_skill``'s
filesystem access, ``run_subagent``'s input-artifact fetch, the artifacts and
uploads REST endpoints, and ``ProjectService.delete_project`` (workspace
lifecycle — ADR-032 § Lifecycle).
"""

from __future__ import annotations

import difflib
import mimetypes
import re
import shutil
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, NoReturn
from uuid import uuid4

import structlog
from siem_contracts import AGENT_RUNTIME_PATH_DENIED

logger = structlog.get_logger()

# Zone of the workspace whose identity (path = identity, ADR-032) backs
# artifacts: SSE `artifact_created`/`artifact_updated`, `ArtifactPart` and the
# REST endpoints all key off a path relative to this directory.
ARTIFACTS_DIR = "artifacts"

# Zone user-uploaded attachments land in (design-brief § Вложения
# пользователя) — write-only from REST (`POST /uploads`), read by the agent
# through the ordinary `read_file`/`execute_code` surface like any other
# workspace path. No snapshot/diff semantics of its own, unlike `artifacts/`.
UPLOADS_DIR = "uploads"

# Shared prefix for every transient file this layer writes: the tmp half of
# `write_text`'s atomic tmp+rename, and the scratch file the code-execution
# tool writes before handing it to the executor. Filtered out of
# `list_dir` and `snapshot_artifacts` so callers never see it.
TMP_FILE_PREFIX = ".workspace-tmp-"

ArtifactChangeKind = Literal["created", "updated"]


def resolve_under_root(root: Path, path: str) -> Path | None:
    """Resolve `path` against `root`; `None` if the result escapes `root`.

    Pure, side-effect-free two-layer defense primitive (`resolve()` +
    `is_relative_to()`, `root` canonicalized here so callers don't have to
    pre-resolve it) — the same check `resolve_path`/`resolve_skill_path`
    below run against their own roots, factored out so a caller that only
    ever needs *one* root (`load_skill`, `agent/tools/skills.py`) can reuse
    it without constructing a full `Workspace` (no `project_id`, no
    read/write/diff surface to thread through). Raises nothing and logs
    nothing — callers that need the security-log-on-denial behavior use
    `Workspace.resolve_path`/`resolve_skill_path` instead.
    """
    root = root.resolve()
    candidate = (root / path).resolve()
    return candidate if candidate.is_relative_to(root) else None


class WorkspacePathError(Exception):
    """A resolved path escaped both allowed roots, or a write targeted `/skills`.

    Internal exception of the storage subsystem, not a member of the
    `AppError` hierarchy (conventions.md § Обработка ошибок → «доменные
    исключения, не транспорт», категория 2): `app.storage` sits below
    `app.services` in the layered-architecture import-linter contract and
    cannot import `app.services.exceptions.AppError`. Callers above this
    layer (agent tools, REST routes) catch it narrowly and translate it into
    their own signal — a tool error string or a route-level `AppError`.
    """

    def __init__(self, *, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        super().__init__(f"path denied: {path!r} ({reason})")


@dataclass(frozen=True)
class ReadResult:
    """Result of `Workspace.read_text`.

    `content` is `None` when the file could not be decoded as UTF-8 text
    (binary file) — callers surface a dedicated message instead of raw bytes
    (design-brief § Контракты файловых инструментов: «binary file, use media
    endpoint», precedent `load_skill`).
    """

    content: str | None
    truncated: bool


def read_text_bounded(target: Path, limit: int) -> ReadResult:
    """Read `target` as UTF-8 text, never materializing more than ~`limit` chars.

    Two read paths, chosen by a `stat()` done up front rather than after the
    fact: a file whose *byte* size already fits under `limit` is guaranteed
    to fit under it in *characters* too (UTF-8 encodes every character in at
    least one byte), so it is read in one call exactly as before. A file over
    that size may still decode to fewer than `limit` characters (multi-byte
    text), so it isn't refused outright — it's read through a text-mode file
    handle capped at `limit + 1` characters (the `+1` is enough to tell
    "exactly at the limit" from "more follows" without reading the rest just
    to find out). Either way the process never holds more than one file's
    worth of *legitimate* content in memory — the OOM shape this closes is a
    multi-gigabyte `artifacts/` file (job output, upload) read whole before
    the existing post-read truncation ever got a chance to run.

    Shared by `Workspace.read_text` and `ArtifactWorkspaceService.
    get_artifact_detail` (`app/services/artifact_workspace.py`) — both read
    an already-resolved `Path` against the same class of ceiling (`Workspace.
    read_limit_chars` for the latter), so the bound lives once, here.

    Raises the same `OSError` subclasses a plain `Path.read_text()`/`.open()`
    would (`FileNotFoundError`, `IsADirectoryError`, ...) — callers already
    handle those; only decoding is special-cased here, same as before.
    """
    size = target.stat().st_size
    if size <= limit:
        try:
            raw = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return ReadResult(content=None, truncated=False)
        return ReadResult(content=raw, truncated=False)

    try:
        with target.open(encoding="utf-8") as f:
            raw = f.read(limit + 1)
    except UnicodeDecodeError:
        return ReadResult(content=None, truncated=False)
    truncated = len(raw) > limit
    return ReadResult(content=raw[:limit] if truncated else raw, truncated=truncated)


@dataclass(frozen=True)
class DiffCounts:
    """Compact line-diff counters for a text file update."""

    added: int
    removed: int


@dataclass(frozen=True)
class WriteResult:
    """Result of `Workspace.write_text`."""

    kind: ArtifactChangeKind
    diff: DiffCounts | None


@dataclass(frozen=True)
class ListEntry:
    """One entry of `Workspace.list_dir`, relative to the listed directory."""

    path: str
    is_dir: bool


@dataclass(frozen=True)
class SnapshotEntry:
    """One file's state in an `artifacts/`-zone snapshot.

    `content` is the file's text read at snapshot time, or `None` when the
    file is binary or exceeds either of the two diff-copy limits (per-file,
    total-per-job) — in which case any later diff against this entry reports
    `diff=None` rather than a (possibly wrong) count.
    """

    mtime_ns: int
    size: int
    content: str | None


ArtifactSnapshot = dict[str, SnapshotEntry]


@dataclass(frozen=True)
class ArtifactDiffEntry:
    """One changed path between two `artifacts/` snapshots."""

    path: str
    kind: ArtifactChangeKind
    diff: DiffCounts | None


class Workspace:
    """File layer bound to a single pair of roots (workspace + skills).

    One instance is long-lived (constructed once from `Settings`, held on
    `app.state` by whichever phase first wires a consumer — not this one).
    `project_id` is a per-call parameter, not constructor state: it is the
    caller's job (agent context / REST ownership dependency) to know which
    project a given call belongs to (design-brief § Workspace: «project_id не
    параметр инструментов»).
    """

    def __init__(
        self,
        *,
        workspaces_root: Path,
        skills_root: Path,
        read_limit_chars: int,
        diff_file_limit_bytes: int,
        diff_total_limit_bytes: int,
    ) -> None:
        # resolve() up front: every later comparison assumes both roots are
        # already canonical, so a symlinked mount point can't shift the
        # boundary underneath repeated is_relative_to() checks.
        self._workspaces_root = workspaces_root.resolve()
        self._skills_root = skills_root.resolve()
        self._read_limit_chars = read_limit_chars
        self._diff_file_limit_bytes = diff_file_limit_bytes
        self._diff_total_limit_bytes = diff_total_limit_bytes

    # -- Path resolution -----------------------------------------------

    def resolve_path(self, project_id: str, path: str, *, write: bool = False) -> Path:
        """Resolve `path` against the project workspace (rw) or `/skills` (ro).

        `path` is normally workspace-relative (e.g. ``"artifacts/x.md"``), but
        may also be an absolute path matching the skills mount (e.g.
        ``"/skills/foo/SKILL.md"``): pathlib's join drops the left-hand side
        entirely when the right-hand side is absolute, so such a path
        canonicalizes to itself and lands under the skills root checked below
        rather than the workspace one — the same mechanism that makes an
        absolute escape attempt (``"/etc/passwd"``) resolve to itself and fail
        *both* checks.

        Both checks run against the *same* canonicalized candidate: a path
        that escapes the workspace is never re-joined to the skills root from
        the original string, because that would let a symlink pointing out of
        the workspace be silently re-based onto a (non-existent) skills path
        instead of being denied (ADR-032 § Границы путей: an escape is a
        domain refusal + security log, never a quiet fallback).

        Raises `WorkspacePathError` — plus an `agent.runtime.path_denied`
        security log — when the canonicalized path escapes both roots, or
        when `write=True` and it only resolves under the read-only skills
        root.
        """
        workspace_root = self._project_root(project_id)
        candidate = (workspace_root / path).resolve()
        if candidate.is_relative_to(workspace_root):
            return candidate

        if candidate.is_relative_to(self._skills_root):
            if write:
                self._deny(path=path, reason="write_to_readonly_root")
            return candidate

        self._deny(path=path, reason="outside_allowed_roots")

    def resolve_artifact_path(self, project_id: str, path: str) -> Path:
        """Resolve an artifact identity (path relative to `artifacts/`) to a file.

        The artifacts REST surface addresses files by their identity — the
        path *relative to the `artifacts/` zone* (ADR-032: «идентификатор =
        путь относительно зоны `artifacts/`») — and reads that zone only:
        `uploads/` has no REST read in v1 and a job's working files are not
        artifacts (design-brief § Артефакты, § Вложения пользователя). So a
        `..` that climbs out of the zone while staying inside the workspace
        (`../uploads/lecture.pdf`) is denied here exactly like an escape out
        of the workspace itself — same canonicalize + `is_relative_to` +
        `agent.runtime.path_denied` log, one zone deeper.

        `path` is joined as a string, not through pathlib: an absolute `path`
        would otherwise drop the zone prefix, and degrading it into a
        relative one inside `artifacts/` is what keeps `?path=/etc/passwd` an
        ordinary "no such artifact" instead of a host read.
        """
        target = self.resolve_path(project_id, f"{ARTIFACTS_DIR}/{path}")
        artifacts_root = (self._project_root(project_id) / ARTIFACTS_DIR).resolve()
        if not target.is_relative_to(artifacts_root):
            self._deny(path=path, reason="outside_artifacts_zone")
        return target

    def resolve_skill_path(self, path: str) -> Path:
        """Resolve `path` against the skills root only (ro).

        For callers that never touch a project workspace (`load_skill`'s
        filesystem access) — same canonicalization + security-log-on-denial
        as `resolve_path`, minus the workspace branch and `project_id`.
        """
        candidate = resolve_under_root(self._skills_root, path)
        if candidate is not None:
            return candidate
        self._deny(path=path, reason="outside_skills_root")

    def _project_root(self, project_id: str) -> Path:
        return (self._workspaces_root / project_id).resolve()

    def _deny(self, *, path: str, reason: str) -> NoReturn:
        logger.warning(
            "workspace path denied",
            security_event=True,
            event_type=AGENT_RUNTIME_PATH_DENIED,
            severity="warning",
            metadata={"path": path, "reason": reason},
        )
        raise WorkspacePathError(path=path, reason=reason)

    @property
    def read_limit_chars(self) -> int:
        """The char ceiling `read_text` truncates to.

        Exposed so `ArtifactWorkspaceService.get_artifact_detail` — a second,
        REST-only read path over an already-resolved `Path` — can cap at the
        same class of limit instead of reading unbounded.
        """
        return self._read_limit_chars

    # -- Read / write / list ---------------------------------------------

    def read_text(self, project_id: str, path: str) -> ReadResult:
        """Read `path` as UTF-8 text, truncated to the configured char limit.

        Raises the usual `OSError` subclasses (`FileNotFoundError`,
        `IsADirectoryError`, ...) for filesystem realities — only the
        path-resolution step has a dedicated exception; a missing file is not
        a security concern for this layer's callers to special-case. Bounded
        by `read_text_bounded` — never reads more of the file into memory
        than the limit could ever need.
        """
        target = self.resolve_path(project_id, path)
        return read_text_bounded(target, self._read_limit_chars)

    def write_text(self, project_id: str, path: str, content: str) -> WriteResult:
        """Write `content` to `path` atomically (tmp + rename in the same dir).

        Parent directories are created as needed (`parents=True`) — this is
        also how a project's workspace directory comes into existence on
        first write (ADR-032 § Lifecycle: lazy creation). Overwrite is silent
        (normal working-directory semantics); `kind`/`diff` on the returned
        `WriteResult` are derived from whether `path` already existed and,
        if so, its previous content — bounded by `diff_file_limit_bytes`, so
        `diff` is `None` for a file too large to diff cheaply.
        """
        target = self.resolve_path(project_id, path, write=True)
        target.parent.mkdir(parents=True, exist_ok=True)

        kind: ArtifactChangeKind = "created"
        diff: DiffCounts | None = None
        if target.exists():
            kind = "updated"
            # The previous content is read only to count changed lines, so it
            # is subject to the same per-file diff ceiling `snapshot_artifacts`
            # applies for the same purpose: over it, the counters are dropped
            # (`diff=None`) rather than paid for with a read of the whole old
            # file. The write itself is unaffected — overwriting a 500MB file
            # succeeds, it just reports no line counts.
            if target.stat().st_size <= self._diff_file_limit_bytes:
                try:
                    old_content = target.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    old_content = None
                if old_content is not None:
                    diff = _line_diff(old_content, content)

        tmp_path = target.parent / f"{TMP_FILE_PREFIX}{uuid4().hex}"
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(target)
        return WriteResult(kind=kind, diff=diff)

    def write_bytes(self, project_id: str, path: str, data: bytes) -> None:
        """Write `data` to `path` atomically (tmp + rename in the same dir).

        Binary counterpart to `write_text`, for content that isn't UTF-8 text
        (`generate_image`'s image bytes; execution-job outputs are written by
        the job itself, not through this method). No `kind`/diff derivation:
        callers that need a collision-safe name resolve one via `unique_path`
        before calling this, so `path` here never already exists.
        """
        target = self.resolve_path(project_id, path, write=True)
        target.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = target.parent / f"{TMP_FILE_PREFIX}{uuid4().hex}"
        tmp_path.write_bytes(data)
        tmp_path.replace(target)

    def list_dir(
        self, project_id: str, path: str = ".", *, recursive: bool = False
    ) -> list[ListEntry]:
        """List `path` (a directory), relative paths + file/dir flag.

        A directory that doesn't exist yet lists as empty rather than
        raising — the common case for a project whose workspace hasn't been
        written to yet (lazy creation, see `write_text`). An existing
        non-directory path is a genuine caller error and raises
        `NotADirectoryError`.
        """
        root = self.resolve_path(project_id, path)
        if not root.exists():
            return []
        if not root.is_dir():
            raise NotADirectoryError(str(root))

        iterator = root.rglob("*") if recursive else root.iterdir()
        entries: list[ListEntry] = []
        for entry in iterator:
            if entry.name.startswith(TMP_FILE_PREFIX):
                continue
            if entry.is_symlink():
                # A symlink is not an artifact/workspace file (ADR-032 § Границы
                # путей already refuses to resolve one that escapes the zone);
                # skipping it here keeps one stray link (job-created or
                # dangling) from failing the whole listing instead of just
                # itself. No security log per skip — that's the resolve-time
                # boundary's job, this is routine filtering.
                logger.warning("workspace listing skipped symlink", path=str(entry))
                continue
            entries.append(
                ListEntry(
                    path=entry.relative_to(root).as_posix(), is_dir=entry.is_dir()
                )
            )
        return sorted(entries, key=lambda e: e.path)

    # -- Lifecycle ---------------------------------------------------------

    def delete_project(self, project_id: str) -> None:
        """Remove the project's entire workspace directory tree, if any.

        Called from `ProjectService.delete_project` (ADR-032 § Lifecycle):
        workspace creation is lazy (first write), so a project that never
        wrote a file has no directory yet — best-effort, not an error. A run
        that outlives the delete may recreate the directory via its own lazy
        `mkdir`; that race is accepted (design-brief § Workspace), not
        guarded against here.
        """
        shutil.rmtree(self._project_root(project_id), ignore_errors=True)

    # -- artifacts/ snapshot + diff --------------------------------------

    def snapshot_artifacts(self, project_id: str) -> ArtifactSnapshot:
        """Snapshot the `artifacts/` zone: `(mtime, size)` + a best-effort text copy.

        The text copy is what lets `diff_artifacts` report line counts for a
        job's before/after pair; it is dropped (`content=None`) per file over
        `diff_file_limit_bytes`, once the running total for this snapshot
        exceeds `diff_total_limit_bytes`, or when the file isn't valid UTF-8.
        """
        artifacts_root = self.resolve_path(project_id, ARTIFACTS_DIR)
        if not artifacts_root.exists():
            return {}

        snapshot: ArtifactSnapshot = {}
        total_bytes = 0
        for entry in sorted(artifacts_root.rglob("*")):
            if entry.name.startswith(TMP_FILE_PREFIX):
                continue
            if entry.is_symlink():
                # Same policy as `list_dir`: a symlink is not an artifact, and
                # reading through one here would follow it out of the zone
                # without the resolve-time boundary check ever running (this
                # loop walks the filesystem directly, not through
                # `resolve_path`/`resolve_artifact_path`).
                logger.warning("artifact snapshot skipped symlink", path=str(entry))
                continue
            if not entry.is_file():
                continue
            stat = entry.stat()
            content: str | None = None
            fits_total = total_bytes + stat.st_size <= self._diff_total_limit_bytes
            if stat.st_size <= self._diff_file_limit_bytes and fits_total:
                try:
                    content = entry.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    content = None
                else:
                    total_bytes += stat.st_size
            relative = entry.relative_to(artifacts_root).as_posix()
            snapshot[relative] = SnapshotEntry(
                mtime_ns=stat.st_mtime_ns, size=stat.st_size, content=content
            )
        return snapshot

    def diff_artifacts(
        self, before: ArtifactSnapshot, after: ArtifactSnapshot
    ) -> list[ArtifactDiffEntry]:
        """Diff two `snapshot_artifacts` results into created/updated entries.

        A path present only in `after` is `created` (`diff=None` always —
        design-brief § Артефакты: a fresh file has nothing to diff against).
        A path present in both with an unchanged `(mtime, size)` pair is
        skipped (nothing happened to it). Everything else is `updated`, with
        a line diff when both snapshots kept a text copy of that path.
        """
        entries: list[ArtifactDiffEntry] = []
        for path in sorted(after):
            after_entry = after[path]
            before_entry = before.get(path)
            if before_entry is None:
                entries.append(ArtifactDiffEntry(path=path, kind="created", diff=None))
                continue
            if (
                before_entry.mtime_ns == after_entry.mtime_ns
                and before_entry.size == after_entry.size
            ):
                continue
            diff = None
            if before_entry.content is not None and after_entry.content is not None:
                diff = _line_diff(before_entry.content, after_entry.content)
            entries.append(ArtifactDiffEntry(path=path, kind="updated", diff=diff))
        return entries


def _line_diff(before: str, after: str) -> DiffCounts:
    """Compact added/removed line counts between two text blobs."""
    matcher = difflib.SequenceMatcher(None, before.splitlines(), after.splitlines())
    added = removed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += j2 - j1
    return DiffCounts(added=added, removed=removed)


# -- Helpers shared by artifact-producing call sites (write_file, job diff,
# generate_image, uploads) -----------------------------------------------


def to_artifact_path(workspace_relative_path: str) -> str | None:
    """Strip the `artifacts/` prefix, or `None` when `path` isn't in that zone.

    The path relative to `artifacts/` *is* an artifact's identity (ADR-032):
    this is the one place that decides whether a given workspace-relative
    path counts as an artifact at all.
    """
    posix = PurePosixPath(workspace_relative_path)
    try:
        return posix.relative_to(ARTIFACTS_DIR).as_posix()
    except ValueError:
        return None


def artifact_type(path: str) -> str:
    """File extension without the leading dot (`"md"`, `"png"`, ...); `""` if none.

    Single semantic reused for the SSE wire payload (`artifact_type`),
    `ArtifactPart.type` and the REST schema — design-brief § Артефакты
    («type = расширение файла без точки»).
    """
    return PurePosixPath(path).suffix.removeprefix(".")


# unicodedata category groups starting with "C" are the control/format/
# surrogate/private-use classes — the "control characters" the sanitizer is
# asked to strip, while every printable Unicode letter (Cyrillic included)
# stays untouched.
_CONTROL_CATEGORY_PREFIX = "C"


def sanitize_filename(name: str, *, fallback_stem: str = "file") -> str:
    """Reduce `name` to a safe basename: no path components, no control chars.

    Splits on both `/` and `\\` and keeps only the last segment (uploads may
    carry either separator depending on the client OS), then drops Unicode
    control characters — everything else, Cyrillic included, survives
    (design-brief: «unicode сохраняется, вычищается лишь недопустимое для
    ФС»). An empty result (all-control input, or `"."`/`".."`) falls back to
    a generated name built from `fallback_stem` (default `"file"`;
    `generate_image` passes `"image"` so an empty/unusable title still reads
    as an image artifact, not a generic one — design-brief § Артефакты:
    «пустой результат → fallback `image-N`»). Collision handling is a
    separate concern, see `unique_path`.
    """
    basename = re.split(r"[/\\]", name)[-1]
    cleaned = "".join(
        ch
        for ch in basename
        if not unicodedata.category(ch).startswith(_CONTROL_CATEGORY_PREFIX)
    ).strip()
    if not cleaned or cleaned in (".", ".."):
        return f"{fallback_stem}-{uuid4().hex[:8]}"
    return cleaned


def unique_path(directory: Path, filename: str) -> Path:
    """`directory / filename`, or a numerically-suffixed variant if that collides.

    Mirrors the `generate_image`/uploads collision rule (design-brief:
    «коллизия → числовой суффикс»): a repeated name never overwrites what an
    older chat message/history entry still points at.
    """
    candidate = directory / filename
    if not candidate.exists():
        return candidate

    stem = PurePosixPath(filename).stem
    suffix = PurePosixPath(filename).suffix
    n = 1
    while True:
        candidate = directory / f"{stem}-{n}{suffix}"
        if not candidate.exists():
            return candidate
        n += 1


_MIME_TO_EXTENSION: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/webp": "webp",
    "image/gif": "gif",
}


def extension_from_mime(mime_type: str) -> str:
    """Map a MIME type to an extension without the leading dot.

    A small curated table for the mimes `generate_image`'s image API
    actually returns takes priority over `mimetypes` (whose registry can
    disagree on the "canonical" extension, e.g. `.jpe` for `image/jpeg` on
    some platforms); falls through to `mimetypes.guess_extension` for
    anything else, then to `"bin"`.
    """
    if mime_type in _MIME_TO_EXTENSION:
        return _MIME_TO_EXTENSION[mime_type]
    guessed = mimetypes.guess_extension(mime_type)
    return guessed.removeprefix(".") if guessed else "bin"
