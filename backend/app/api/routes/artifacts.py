from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Response

from app.api.deps import ArtifactServiceDep, UserProject
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
) -> ArtifactListResponse:
    artifacts = await service.list_artifacts(project.id)
    return ArtifactListResponse(
        items=[ArtifactListItem.model_validate(a) for a in artifacts]
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
    format: str = Query(default="md", pattern="^(md|pdf)$"),
) -> Response:
    artifact = await service.get_artifact(artifact_id)
    if artifact.project_id != project.id:
        raise HTTPException(status_code=404, detail="Artifact not found")

    def _content_disposition(filename: str) -> str:
        encoded = quote(filename)
        return f"attachment; filename*=UTF-8''{encoded}"

    if format == "pdf":
        pdf_bytes = convert_md_to_pdf(artifact.content)
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
