from __future__ import annotations

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser, Pagination
from app.api.schemas.user_memory import (
    InstructionsResponse,
    InstructionsUpdate,
    MemoryItem,
    MemoryListResponse,
)
from app.services.user_memory import LangGraphUserMemoryService

router = APIRouter(tags=["user-memory"])


def _get_memory_service(request: Request) -> LangGraphUserMemoryService:
    return LangGraphUserMemoryService(
        store=request.app.state.store,
        guard=getattr(request.app.state, "security_guard", None),
    )


@router.get("/users/me/instructions", response_model=InstructionsResponse)
async def get_instructions(
    user: CurrentUser,
    request: Request,
) -> InstructionsResponse:
    svc = _get_memory_service(request)
    content = await svc.get_instructions(str(user.id))
    return InstructionsResponse(content=content)


@router.put("/users/me/instructions", response_model=InstructionsResponse)
async def update_instructions(
    body: InstructionsUpdate,
    user: CurrentUser,
    request: Request,
) -> InstructionsResponse:
    svc = _get_memory_service(request)
    content = await svc.update_instructions(str(user.id), body.content)
    return InstructionsResponse(content=content)


@router.delete("/users/me/memories/{key}", status_code=204)
async def delete_memory(
    key: str,
    user: CurrentUser,
    request: Request,
) -> None:
    svc = _get_memory_service(request)
    await svc.delete_memory(str(user.id), key)


@router.get("/users/me/memories", response_model=MemoryListResponse)
async def list_memories(
    user: CurrentUser,
    request: Request,
    page: Pagination,
) -> MemoryListResponse:
    svc = _get_memory_service(request)
    memories = await svc.list_memories(str(user.id))
    items = memories[page.offset : page.offset + page.limit]
    return MemoryListResponse(
        items=[
            MemoryItem(
                key=i.key,
                description=i.description,
                content=i.content,
                created_at=i.created_at,
            )
            for i in items
        ],
        total=len(memories),
        limit=page.limit,
        offset=page.offset,
    )
