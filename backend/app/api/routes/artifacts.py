from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

import anyio.to_thread
from fastapi import APIRouter, HTTPException, Query, Response

from app.api.deps import ArtifactServiceDep, Pagination, UserProject
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


@router.get("/projects/{project_id}/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: uuid.UUID,
    project: UserProject,
    service: ArtifactServiceDep,
    format: Annotated[str, Query(pattern="^(md|pdf)$")] = "md",
) -> Response:
    artifact = await service.get_artifact(artifact_id)
    if artifact.project_id != project.id:
        raise HTTPException(status_code=404, detail="Artifact not found")

    def _content_disposition(filename: str) -> str:
        encoded = quote(filename)
        return f"attachment; filename*=UTF-8''{encoded}"

    if format == "pdf":
        # wkhtmltopdf — блокирующий вызов (~5s javascript-delay), уводим из event loop
        pdf_bytes = await anyio.to_thread.run_sync(convert_md_to_pdf, artifact.content)
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
