from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Request

from app.api.deps import CurrentUser, DBSession, UserProject, UserThread
from app.api.schemas.settings import SettingsResponse, SettingsUpdate
from app.repositories.settings import SettingsRepository
from app.services.model_config_resolver import ModelConfigResolver

router = APIRouter(tags=["settings"])


def _get_resolver(request: Request) -> ModelConfigResolver:
    return request.app.state.agent_runner._model_resolver


def _get_allowed_models(request: Request) -> set[str]:
    return {m.name for m in request.app.state.agent_config.available_models}


def _validate_model(model_name: str | None, allowed: set[str]) -> None:
    if model_name is not None and model_name not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Model '{model_name}' is not in the allowed models list",
        )


async def _build_response(
    repo: SettingsRepository,
    resolver: ModelConfigResolver,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None,
    thread_id: uuid.UUID | None,
    raw_model_name: str | None,
    raw_extra_body: dict | None,
) -> SettingsResponse:
    resolved = await resolver.resolve(repo, user_id, project_id, thread_id)
    return SettingsResponse(
        model_name=raw_model_name,
        extra_body=raw_extra_body,
        resolved_model=resolved.model,
        resolved_source=resolved.source,
    )


# --- User Settings ---


@router.get("/users/me/settings", response_model=SettingsResponse)
async def get_user_settings(
    user: CurrentUser,
    session: DBSession,
    request: Request,
) -> SettingsResponse:
    repo = SettingsRepository(session)
    s = await repo.get_user_settings(user.id)
    return await _build_response(
        repo,
        _get_resolver(request),
        user.id,
        None,
        None,
        s.model_name if s else None,
        s.extra_body if s else None,
    )


@router.put("/users/me/settings", response_model=SettingsResponse)
async def update_user_settings(
    body: SettingsUpdate,
    user: CurrentUser,
    session: DBSession,
    request: Request,
) -> SettingsResponse:
    _validate_model(body.model_name, _get_allowed_models(request))
    repo = SettingsRepository(session)
    s = await repo.upsert_user_settings(
        user.id, model_name=body.model_name, extra_body=body.extra_body
    )
    return await _build_response(
        repo,
        _get_resolver(request),
        user.id,
        None,
        None,
        s.model_name,
        s.extra_body,
    )


# --- Project Settings ---


@router.get("/projects/{project_id}/settings", response_model=SettingsResponse)
async def get_project_settings(
    project: UserProject,
    user: CurrentUser,
    session: DBSession,
    request: Request,
) -> SettingsResponse:
    repo = SettingsRepository(session)
    s = await repo.get_project_settings(project.id)
    return await _build_response(
        repo,
        _get_resolver(request),
        user.id,
        project.id,
        None,
        s.model_name if s else None,
        s.extra_body if s else None,
    )


@router.put("/projects/{project_id}/settings", response_model=SettingsResponse)
async def update_project_settings(
    body: SettingsUpdate,
    project: UserProject,
    user: CurrentUser,
    session: DBSession,
    request: Request,
) -> SettingsResponse:
    _validate_model(body.model_name, _get_allowed_models(request))
    repo = SettingsRepository(session)
    s = await repo.upsert_project_settings(
        project.id, model_name=body.model_name, extra_body=body.extra_body
    )
    return await _build_response(
        repo,
        _get_resolver(request),
        user.id,
        project.id,
        None,
        s.model_name,
        s.extra_body,
    )


# --- Thread Settings ---


@router.get(
    "/projects/{project_id}/chats/{chat_id}/settings",
    response_model=SettingsResponse,
)
async def get_thread_settings(
    thread: UserThread,
    project: UserProject,
    user: CurrentUser,
    session: DBSession,
    request: Request,
) -> SettingsResponse:
    repo = SettingsRepository(session)
    s = await repo.get_thread_settings(thread.thread_id)
    return await _build_response(
        repo,
        _get_resolver(request),
        user.id,
        project.id,
        thread.thread_id,
        s.model_name if s else None,
        s.extra_body if s else None,
    )


@router.put(
    "/projects/{project_id}/chats/{chat_id}/settings",
    response_model=SettingsResponse,
)
async def update_thread_settings(
    body: SettingsUpdate,
    thread: UserThread,
    project: UserProject,
    user: CurrentUser,
    session: DBSession,
    request: Request,
) -> SettingsResponse:
    _validate_model(body.model_name, _get_allowed_models(request))
    repo = SettingsRepository(session)
    s = await repo.upsert_thread_settings(
        thread.thread_id, model_name=body.model_name, extra_body=body.extra_body
    )
    return await _build_response(
        repo,
        _get_resolver(request),
        user.id,
        project.id,
        thread.thread_id,
        s.model_name,
        s.extra_body,
    )
