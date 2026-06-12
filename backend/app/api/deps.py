from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated, Any

import jwt
import structlog
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models.project import Project
from app.models.user import User
from app.repositories import (
    ArtifactRepository,
    ProjectRepository,
    ThreadViewRepository,
    TraceStore,
    UserRepository,
)
from app.services import (
    ArtifactService,
    ChatService,
    ProjectService,
)
from app.services.security import decode_access_token
from app.services.sphere import LangGraphSphereService, SphereService


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_security_guard(request: Request) -> Any:
    return request.app.state.security_guard


def get_security_config(request: Request) -> Any:
    return request.app.state.security_config


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
    settings: SettingsDep,
) -> User:
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth_header.removeprefix("Bearer ")
    try:
        user_id = decode_access_token(token, settings.jwt_secret)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        raise HTTPException(
            status_code=401, detail="Invalid or expired token"
        ) from None

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    # Bind user context for security events
    structlog.contextvars.bind_contextvars(user_id=str(user.id))

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_project_service(session: DBSession) -> ProjectService:
    return ProjectService(project_repo=ProjectRepository(session))


def get_artifact_service(session: DBSession) -> ArtifactService:
    return ArtifactService(artifact_repo=ArtifactRepository(session))


def get_chat_service(session: DBSession, request: Request) -> ChatService:
    redis = getattr(request.app.state, "redis", None)
    trace_store = TraceStore(redis) if redis else None
    return ChatService(
        thread_view_repo=ThreadViewRepository(session),
        agent_runner=request.app.state.agent_runner,
        artifact_repo=ArtifactRepository(session),
        trace_store=trace_store,
        session=session,
    )


def get_sphere_service(request: Request) -> SphereService:
    return LangGraphSphereService(
        store=request.app.state.store,
        guard=getattr(request.app.state, "security_guard", None),
    )


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


async def require_unblocked_thread(
    chat_id: uuid.UUID,
    session: DBSession,
) -> None:
    """Reject requests against threads that are security-blocked."""
    repo = ThreadViewRepository(session)
    if await repo.is_security_blocked(chat_id):
        raise HTTPException(status_code=403, detail="Thread blocked by security policy")
