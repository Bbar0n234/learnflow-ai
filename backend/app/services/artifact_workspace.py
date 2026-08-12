"""Service-layer wrapper around `Workspace` for the artifacts REST surface.

`app.api.routes` may not import `app.storage`/`app.repositories`/`app.agent`
directly — the layered-architecture import-linter contract ("Backend:
api/routes must not import repositories, storage or agent directly",
`pyproject.toml`) requires the API to reach data only through the service
layer; `api/deps.py` is the one place allowed to wire storage/repositories
for DI. This module is that service-layer step for the file-backed artifacts
endpoints (ADR-032, T1.6): the one place a route's injected `Workspace`
(via `WorkspaceDep`) actually gets called. Deliberately storage-shaped, not
schema-shaped — no `app.api.schemas`/`fastapi` import here, so routes.py owns
HTTP concerns (status codes, headers, response-schema construction) and this
module owns none of them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.storage.workspace import (
    ARTIFACTS_DIR,
    Workspace,
    artifact_type,
    read_text_bounded,
)


@dataclass(frozen=True)
class ArtifactListEntry:
    path: str
    title: str
    type: str
    updated_at: datetime


@dataclass(frozen=True)
class ArtifactDetail:
    path: str
    title: str
    type: str
    content: str | None
    updated_at: datetime


@dataclass(frozen=True)
class ArtifactFile:
    """Where the file is + cache-validator metadata for `media`/`download`.

    Deliberately the location, not the bytes: the size of an artifact is set
    by whatever job wrote it (no schema ceiling since ADR-032), so reading it
    whole to hand a `bytes` to the route would put an arbitrary number of
    megabytes into the process per open/download. The route streams from
    `path` instead; this dataclass carries the `stat()` the cache validators
    (`ETag`, `Last-Modified`) are derived from, taken once here.
    """

    path: Path
    name: str
    mtime: float
    mtime_ns: int
    size: int


class ArtifactWorkspaceService:
    """Read-only view of a project's `artifacts/` zone for REST handlers."""

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def list_artifacts(self, project_id: str) -> list[ArtifactListEntry]:
        """Every file under `artifacts/`, recursively, most recently updated first."""
        entries = self._workspace.list_dir(project_id, ARTIFACTS_DIR, recursive=True)
        items = []
        for entry in entries:
            if entry.is_dir:
                continue
            target = self._resolve(project_id, entry.path)
            items.append(
                ArtifactListEntry(
                    path=entry.path,
                    title=target.name,
                    type=artifact_type(entry.path),
                    updated_at=_to_datetime(target.stat().st_mtime),
                )
            )
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return items

    def get_artifact_detail(self, project_id: str, path: str) -> ArtifactDetail | None:
        """`None` when `path` doesn't resolve to an existing file (caller → 404)."""
        target = self._resolve(project_id, path)
        try:
            stat_result = target.stat()
        except FileNotFoundError:
            return None
        if target.is_dir():
            return None

        # Same ceiling `read_text` truncates to, same bounded-read primitive
        # — this REST path has no lower entry point than the raw file, so it
        # must bound itself rather than rely on a caller having already done
        # so (unlike the agent's `read_file` tool, which always goes through
        # `Workspace.read_text`).
        content = read_text_bounded(target, self._workspace.read_limit_chars).content

        return ArtifactDetail(
            path=path,
            title=target.name,
            type=artifact_type(path),
            content=content,
            updated_at=_to_datetime(stat_result.st_mtime),
        )

    def stat_artifact_file(self, project_id: str, path: str) -> ArtifactFile | None:
        """Resolve `path` and stat it; `None` when it isn't an existing file (→ 404).

        Resolution + existence check only — the bytes never pass through this
        layer (see `ArtifactFile`). Doing the `stat()` here rather than
        leaving it to the response keeps the zone check (`resolve_artifact_
        path`) and the metadata the route needs in one call off the event
        loop.
        """
        target = self._resolve(project_id, path)
        try:
            stat_result = target.stat()
        except FileNotFoundError:
            return None
        if target.is_dir():
            return None

        return ArtifactFile(
            path=target,
            name=target.name,
            mtime=stat_result.st_mtime,
            mtime_ns=stat_result.st_mtime_ns,
            size=stat_result.st_size,
        )

    def _resolve(self, project_id: str, path: str) -> Path:
        # `path` is an artifact identity — relative to the `artifacts/` zone,
        # which is also the boundary of this REST surface, so leaving the zone
        # (`../uploads/...`) is denied by the file layer just like leaving the
        # workspace. WorkspacePathError propagates uncaught — the global
        # handler in app/api/problem.py maps it to 422 (path-escape attempt,
        # distinct from the plain "file doesn't exist" 404 the methods above
        # return).
        return self._workspace.resolve_artifact_path(project_id, path)


def _to_datetime(epoch_seconds: float) -> datetime:
    return datetime.fromtimestamp(epoch_seconds, tz=UTC)
