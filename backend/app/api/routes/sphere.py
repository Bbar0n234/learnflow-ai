from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import SphereServiceDep, UserProject
from app.api.schemas.sphere import SphereResponse, SphereUpdate

router = APIRouter(tags=["sphere"])


@router.get(
    "/projects/{project_id}/sphere",
    response_model=SphereResponse,
)
async def get_sphere(
    project: UserProject,
    service: SphereServiceDep,
) -> SphereResponse:
    data = await service.get(project_id=project.id)
    return SphereResponse(
        project_id=data.project_id,
        content=data.content,
        updated_at=data.updated_at,
    )


@router.put(
    "/projects/{project_id}/sphere",
    response_model=SphereResponse,
)
async def update_sphere(
    body: SphereUpdate,
    project: UserProject,
    service: SphereServiceDep,
) -> SphereResponse:
    data = await service.update(project_id=project.id, content=body.content)
    return SphereResponse(
        project_id=data.project_id,
        content=data.content,
        updated_at=data.updated_at,
    )
