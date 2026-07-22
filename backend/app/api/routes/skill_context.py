from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser
from app.api.schemas.skill_context import (
    SkillContextDocument,
    SkillContextGroup,
    SkillContextListResponse,
    SkillContextUpdate,
)
from app.services.skill_context import LangGraphSkillContextService

router = APIRouter(tags=["skill-context"])


def _get_skill_context_service(request: Request) -> LangGraphSkillContextService:
    return LangGraphSkillContextService(
        store=request.app.state.store,
        guard=getattr(request.app.state, "security_guard", None),
        skill_names=request.app.state.skill_names,
    )


@router.get("/users/me/skill-contexts", response_model=SkillContextListResponse)
async def list_skill_contexts(
    user: CurrentUser,
    request: Request,
) -> SkillContextListResponse:
    svc = _get_skill_context_service(request)
    groups = await svc.list_skill_contexts(str(user.id))
    return SkillContextListResponse(
        skills=[
            SkillContextGroup(
                skill_name=g.skill_name,
                in_library=g.in_library,
                documents=[
                    SkillContextDocument(
                        key=d.key,
                        description=d.description,
                        content=d.content,
                        created_at=d.created_at,
                        updated_at=d.updated_at,
                    )
                    for d in g.documents
                ],
            )
            for g in groups
        ]
    )


@router.get(
    "/users/me/skill-contexts/{skill_name}/{key}",
    response_model=SkillContextDocument,
)
async def get_skill_context(
    skill_name: str,
    key: str,
    user: CurrentUser,
    request: Request,
) -> SkillContextDocument:
    svc = _get_skill_context_service(request)
    doc = await svc.get_document(str(user.id), skill_name, key)
    return SkillContextDocument(
        key=doc.key,
        description=doc.description,
        content=doc.content,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.put(
    "/users/me/skill-contexts/{skill_name}/{key}",
    response_model=SkillContextDocument,
)
async def update_skill_context(
    skill_name: str,
    key: str,
    body: SkillContextUpdate,
    user: CurrentUser,
    request: Request,
) -> SkillContextDocument:
    svc = _get_skill_context_service(request)
    doc = await svc.update_document(
        str(user.id),
        skill_name,
        key,
        description=body.description,
        content=body.content,
    )
    return SkillContextDocument(
        key=doc.key,
        description=doc.description,
        content=doc.content,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.delete("/users/me/skill-contexts/{skill_name}/{key}", status_code=204)
async def delete_skill_context(
    skill_name: str,
    key: str,
    user: CurrentUser,
    request: Request,
) -> None:
    svc = _get_skill_context_service(request)
    await svc.delete_document(str(user.id), skill_name, key)
