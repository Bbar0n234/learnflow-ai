from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.user import User
from app.repositories import (
    ArtifactRepository,
    ProjectRepository,
    ThreadViewRepository,
    UserRepository,
)
from app.services import (
    ArtifactService,
    ChatService,
    ProjectService,
)
from app.services.sphere import LangGraphSphereService, SphereService


async def get_db_session(request: Request) -> AsyncGenerator[AsyncSession]:
    session: AsyncSession = request.app.state.session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


DBSession = Annotated[AsyncSession, Depends(get_db_session)]


async def get_current_user(
    request: Request,
    session: DBSession,
) -> User:
    user_name = request.headers.get("X-User-Name")
    if not user_name:
        raise HTTPException(status_code=401, detail="X-User-Name header required")
    user_repo = UserRepository(session)
    return await user_repo.get_or_create(user_name)


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_project_service(session: DBSession) -> ProjectService:
    return ProjectService(project_repo=ProjectRepository(session))


def get_artifact_service(session: DBSession) -> ArtifactService:
    return ArtifactService(artifact_repo=ArtifactRepository(session))


def get_chat_service(session: DBSession, request: Request) -> ChatService:
    return ChatService(
        thread_view_repo=ThreadViewRepository(session),
        agent_runner=request.app.state.agent_runner,
        artifact_repo=ArtifactRepository(session),
    )


def get_sphere_service(request: Request) -> SphereService:
    return LangGraphSphereService(store=request.app.state.store)


ProjectServiceDep = Annotated[ProjectService, Depends(get_project_service)]
ArtifactServiceDep = Annotated[ArtifactService, Depends(get_artifact_service)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
SphereServiceDep = Annotated[SphereService, Depends(get_sphere_service)]


async def get_user_project(
    project_id: uuid.UUID,
    user: CurrentUser,
    project_service: ProjectServiceDep,
) -> Project:
    project = await project_service.get_project(project_id)
    if project.user_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


UserProject = Annotated[Project, Depends(get_user_project)]
