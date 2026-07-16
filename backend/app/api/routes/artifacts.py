from __future__ import annotations

import functools
import uuid
from typing import Annotated
from urllib.parse import quote

import anyio.to_thread
from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.api.deps import ArtifactServiceDep, BlobStorageDep, Pagination, UserProject
from app.api.export import convert_md_to_pdf
from app.api.schemas.artifacts import (
    ArtifactDetailResponse,
    ArtifactListItem,
    ArtifactListResponse,
)

router = APIRouter(tags=["artifacts"])


@router.get(
    "/projects/{project_id}/artifacts",
    response_model=ArtifactListResponse,
)
async def list_artifacts(
    project: UserProject,
    service: ArtifactServiceDep,
    page: Pagination,
) -> ArtifactListResponse:
    artifacts, total = await service.list_artifacts(
        project.id, limit=page.limit, offset=page.offset
    )
    return ArtifactListResponse(
        items=[ArtifactListItem.model_validate(a) for a in artifacts],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get(
    "/projects/{project_id}/artifacts/{artifact_id}",
    response_model=ArtifactDetailResponse,
)
async def get_artifact(
    artifact_id: uuid.UUID,
    project: UserProject,
    service: ArtifactServiceDep,
) -> ArtifactDetailResponse:
    artifact = await service.get_artifact(artifact_id)
    if artifact.project_id != project.id:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return ArtifactDetailResponse.model_validate(artifact)


@router.get("/projects/{project_id}/artifacts/{artifact_id}/media")
async def get_artifact_media(
    artifact_id: uuid.UUID,
    project: UserProject,
    service: ArtifactServiceDep,
    blob_storage: BlobStorageDep,
) -> Response:
    artifact = await service.get_artifact(artifact_id)
    if artifact.project_id != project.id:
        raise HTTPException(status_code=404, detail="Artifact not found")

    blob = await blob_storage.get(artifact_id)
    if blob is None:
        raise HTTPException(status_code=404, detail="Artifact media not found")
    data, mime_type = blob

    return Response(
        content=data,
        media_type=mime_type,
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/projects/{project_id}/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: uuid.UUID,
    project: UserProject,
    service: ArtifactServiceDep,
    request: Request,
    format: Annotated[str, Query(pattern="^(md|pdf)$")] = "md",
) -> Response:
    artifact = await service.get_artifact(artifact_id)
    if artifact.project_id != project.id:
        raise HTTPException(status_code=404, detail="Artifact not found")

    def _content_disposition(filename: str) -> str:
        encoded = quote(filename)
        return f"attachment; filename*=UTF-8''{encoded}"

    if format == "pdf":
        # wkhtmltopdf — блокирующий вызов (~5s javascript-delay), уводим из event loop.
        # Timeout comes from Settings.pdf_conversion_timeout_seconds (D-ERR-11).
        pdf_timeout = request.app.state.settings.pdf_conversion_timeout_seconds
        pdf_bytes = await anyio.to_thread.run_sync(
            functools.partial(convert_md_to_pdf, timeout=pdf_timeout),
            artifact.content,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": _content_disposition(f"{artifact.title}.pdf"),
            },
        )

    return Response(
        content=artifact.content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": _content_disposition(f"{artifact.title}.md"),
        },
    )
