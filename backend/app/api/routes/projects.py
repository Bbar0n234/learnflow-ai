from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import CurrentUser, ProjectServiceDep, UserProject
from app.api.schemas.projects import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse)
async def create_project(
    body: ProjectCreate,
    user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectResponse:
    project = await service.create_project(user_id=user.id, name=body.name)
    return ProjectResponse.model_validate(project)


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    user: CurrentUser,
    service: ProjectServiceDep,
) -> ProjectListResponse:
    projects = await service.list_projects(user.id)
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in projects]
    )


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project: UserProject,
) -> ProjectResponse:
    return ProjectResponse.model_validate(project)


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    body: ProjectUpdate,
    project: UserProject,
    service: ProjectServiceDep,
) -> ProjectResponse:
    updated = await service.update_project(project.id, name=body.name)
    return ProjectResponse.model_validate(updated)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project: UserProject,
    service: ProjectServiceDep,
) -> Response:
    await service.delete_project(project.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
