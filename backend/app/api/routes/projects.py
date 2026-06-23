from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import CurrentUser, Pagination, ProjectServiceDep, UserProject
from app.api.schemas.projects import (
    ProjectCreate,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdate,
)
from app.services.exceptions import EntityNotFoundError

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
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
    page: Pagination,
) -> ProjectListResponse:
    projects, total = await service.list_projects(
        user.id, limit=page.limit, offset=page.offset
    )
    return ProjectListResponse(
        items=[ProjectResponse.model_validate(p) for p in projects],
        total=total,
        limit=page.limit,
        offset=page.offset,
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
    project_id: uuid.UUID,
    user: CurrentUser,
    service: ProjectServiceDep,
) -> Response:
    # Idempotent DELETE (api.md): an already-removed project resolves as a
    # no-op 204 instead of 404. Ownership is still enforced — an existing
    # project owned by another user stays hidden behind a 404.
    try:
        project = await service.get_project(project_id)
    except EntityNotFoundError:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    await service.delete_project(project.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
