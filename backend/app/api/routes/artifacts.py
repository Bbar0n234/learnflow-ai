"""Artifacts REST — file-backed model (ADR-032, T1.6).

Four GETs over the project workspace's `artifacts/` zone. Addressing is a
`path` query parameter (relative to `artifacts/`, no leading prefix — the
artifact's identity, design-brief § Артефакты), not a URL segment: a segment
can't carry `/` through ASGI routing/React matching. `list` and `get` share
one route — `path` absent is list (recursive, flat `Page[T]`), `path` present
is detail — mirroring the exact two calls the frontend already makes
(`frontend/src/shared/api/artifacts.ts`, T2, shipped ahead of this phase).
`media`/`download` are their own routes, `path` required on both.

All actual filesystem access goes through `ArtifactWorkspaceServiceDep`
(`app/services/artifact_workspace.py`) — routes.py itself never imports
`app.storage` (import-linter contract, see that module's docstring).

Path-escape attempts (`WorkspacePathError`) are not handled here — they
propagate to the global handler registered in `app/api/problem.py` (422).
A syntactically valid path whose file doesn't exist is a plain local 404,
same as the old UUID-not-found case.
"""

from __future__ import annotations

import mimetypes
from email.utils import formatdate
from pathlib import PurePosixPath
from typing import Annotated
from urllib.parse import quote

import anyio.to_thread
from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.api.deps import ArtifactWorkspaceServiceDep, Pagination, UserProject
from app.api.schemas.artifacts import (
    ArtifactDetailResponse,
    ArtifactListItem,
    ArtifactListResponse,
)

router = APIRouter(tags=["artifacts"])

# mimetypes has no built-in entry for Markdown; everything else falls
# through to its registry, then to a generic binary fallback.
_EXTRA_MEDIA_TYPES = {".md": "text/markdown"}


def _guess_media_type(filename: str) -> str:
    suffix = PurePosixPath(filename).suffix.lower()
    if suffix in _EXTRA_MEDIA_TYPES:
        return _EXTRA_MEDIA_TYPES[suffix]
    guessed, _ = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _content_disposition(filename: str) -> str:
    encoded = quote(filename)
    return f"attachment; filename*=UTF-8''{encoded}"


def _etag(*, mtime_ns: int, size: int) -> str:
    # Weak ETag from (mtime, size) — design-brief § Кэш media: the path is a
    # rewritable identity, not immutable content, so identity alone (path)
    # can't be the cache key; (mtime, size) is what actually changed.
    return f'W/"{mtime_ns:x}-{size:x}"'


@router.get(
    "/projects/{project_id}/artifacts",
    response_model_exclude_none=True,
)
async def get_artifacts(
    project: UserProject,
    artifacts: ArtifactWorkspaceServiceDep,
    page: Pagination,
    path: Annotated[str | None, Query()] = None,
) -> ArtifactListResponse | ArtifactDetailResponse:
    if path is not None:
        detail = await anyio.to_thread.run_sync(
            artifacts.get_artifact_detail, str(project.id), path
        )
        if detail is None:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return ArtifactDetailResponse(
            path=detail.path,
            title=detail.title,
            type=detail.type,
            content=detail.content,
            updated_at=detail.updated_at,
        )

    items = await anyio.to_thread.run_sync(artifacts.list_artifacts, str(project.id))
    total = len(items)
    page_items = items[page.offset : page.offset + page.limit]
    return ArtifactListResponse(
        items=[
            ArtifactListItem(
                path=item.path,
                title=item.title,
                type=item.type,
                updated_at=item.updated_at,
            )
            for item in page_items
        ],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/projects/{project_id}/artifacts/media")
async def get_artifact_media(
    project: UserProject,
    artifacts: ArtifactWorkspaceServiceDep,
    request: Request,
    path: Annotated[str, Query()],
) -> Response:
    file = await anyio.to_thread.run_sync(
        artifacts.read_artifact_file, str(project.id), path
    )
    if file is None:
        raise HTTPException(status_code=404, detail="Artifact media not found")

    etag = _etag(mtime_ns=file.mtime_ns, size=file.size)
    headers = {
        "ETag": etag,
        "Last-Modified": formatdate(file.mtime, usegmt=True),
        # Not immutable: the path is a rewritable identity (a later
        # write_file/job can change the same path), so the browser must
        # revalidate on every request instead of trusting a cached copy
        # forever (design-brief § Кэш media).
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
    }
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304, headers=headers)

    return Response(
        content=file.data,
        media_type=_guess_media_type(file.name),
        headers=headers,
    )


@router.get("/projects/{project_id}/artifacts/download")
async def download_artifact(
    project: UserProject,
    artifacts: ArtifactWorkspaceServiceDep,
    path: Annotated[str, Query()],
) -> Response:
    file = await anyio.to_thread.run_sync(
        artifacts.read_artifact_file, str(project.id), path
    )
    if file is None:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return Response(
        content=file.data,
        media_type=_guess_media_type(file.name),
        headers={"Content-Disposition": _content_disposition(file.name)},
    )
