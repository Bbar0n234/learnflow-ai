"""Service-layer wrapper around `Workspace` for the uploads REST surface.

Same import-linter constraint `ArtifactWorkspaceService`
(`app/services/artifact_workspace.py`) documents in its own module
docstring applies here: `app.api.routes` may not import `app.storage`
directly (layered-architecture contract, `pyproject.toml`), so
`routes/uploads.py`'s one filesystem call goes through this thin service
instead of `WorkspaceDep` directly.

A separate module rather than a method on `ArtifactWorkspaceService`: that
service is documented and typed as a read-only view of the `artifacts/`
zone; an upload is a write into a different zone (`uploads/`) with its own
naming rule (sanitize + collision suffix, no diff/kind semantics of its
own) — folding it into the artifacts service would blur what each one
actually promises.
"""

from __future__ import annotations

from app.storage.workspace import (
    UPLOADS_DIR,
    Workspace,
    sanitize_filename,
    unique_path,
)


class UploadWorkspaceService:
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def save_upload(self, project_id: str, filename: str, data: bytes) -> str:
        """Pick a collision-free name under `uploads/` and write `data` there.

        Directory resolution, the collision check (`unique_path`) and the
        atomic write happen inside one call — the caller runs it off the
        event loop (`anyio.to_thread.run_sync`) — so the window between
        "name chosen" and "file written" stays minimal, the same reasoning
        `image_generation._save_image` documents for `generate_image`.
        Returns the workspace-relative path (`"uploads/<name>"`).
        """
        name = sanitize_filename(filename)
        uploads_dir = self._workspace.resolve_path(project_id, UPLOADS_DIR, write=True)
        target = unique_path(uploads_dir, name)
        self._workspace.write_bytes(project_id, f"{UPLOADS_DIR}/{target.name}", data)
        return f"{UPLOADS_DIR}/{target.name}"
