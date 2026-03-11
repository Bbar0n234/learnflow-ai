from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import ChatServiceDep, CurrentUser, UserProject
from app.api.schemas.chats import (
    ChatCreate,
    ChatDetailResponse,
    ChatListResponse,
    ChatRecentItem,
    ChatRecentResponse,
    ChatResponse,
    MessageOut,
)

router = APIRouter(tags=["chats"])


@router.post("/projects/{project_id}/chats", response_model=ChatResponse)
async def create_chat(
    body: ChatCreate,
    project: UserProject,
    service: ChatServiceDep,
) -> ChatResponse:
    title = body.title or "New Chat"
    thread_view = await service.create_chat(project_id=project.id, title=title)
    return ChatResponse.model_validate(thread_view)


@router.get("/projects/{project_id}/chats", response_model=ChatListResponse)
async def list_chats(
    project: UserProject,
    service: ChatServiceDep,
) -> ChatListResponse:
    chats = await service.list_chats(project.id)
    return ChatListResponse(items=[ChatResponse.model_validate(c) for c in chats])


@router.get("/projects/{project_id}/chats/{chat_id}", response_model=ChatDetailResponse)
async def get_chat(
    chat_id: uuid.UUID,
    project: UserProject,
    service: ChatServiceDep,
) -> ChatDetailResponse:
    chat_detail = await service.get_chat(chat_id)
    # Verify chat belongs to this project
    if chat_detail.thread_view.project_id != project.id:
        raise HTTPException(status_code=404, detail="Chat not found")
    return ChatDetailResponse(
        thread_id=chat_detail.thread_view.thread_id,
        title=chat_detail.thread_view.title,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
            )
            for m in chat_detail.messages
        ],
    )


@router.get("/chats/recent", response_model=ChatRecentResponse)
async def list_recent_chats(
    user: CurrentUser,
    service: ChatServiceDep,
    limit: int = Query(default=10, ge=1, le=100),
) -> ChatRecentResponse:
    thread_views = await service.list_recent(user.id, limit=limit)
    return ChatRecentResponse(
        items=[
            ChatRecentItem(
                thread_id=tv.thread_id,
                title=tv.title,
                project_id=tv.project_id,
                project_name=tv.project.name,
                updated_at=tv.updated_at,
            )
            for tv in thread_views
        ]
    )
