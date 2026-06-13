from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import (
    ArtifactServiceDep,
    ChatServiceDep,
    CurrentUser,
    Pagination,
    UserProject,
    UserThread,
)
from app.api.schemas.artifacts import ArtifactListItem
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


@router.post(
    "/projects/{project_id}/chats",
    response_model=ChatResponse,
    status_code=status.HTTP_201_CREATED,
)
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
    page: Pagination,
) -> ChatListResponse:
    chats, total = await service.list_chats(
        project.id, limit=page.limit, offset=page.offset
    )
    return ChatListResponse(
        items=[ChatResponse.model_validate(c) for c in chats],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/projects/{project_id}/chats/{chat_id}", response_model=ChatDetailResponse)
async def get_chat(
    thread: UserThread,
    service: ChatServiceDep,
    artifact_service: ArtifactServiceDep,
) -> ChatDetailResponse:
    chat_detail = await service.get_chat(thread.thread_id)

    # Get artifacts for this thread, group by message_id
    artifacts = await artifact_service.list_by_thread(thread.thread_id)
    artifacts_by_msg: dict[str | None, list[ArtifactListItem]] = {}
    for a in artifacts:
        artifacts_by_msg.setdefault(a.message_id, []).append(
            ArtifactListItem.model_validate(a)
        )

    def _feedback_for(msg_id: str) -> bool | None:
        tid = chat_detail.trace_ids.get(msg_id)
        if tid is None:
            return None
        return chat_detail.feedback_scores.get(tid)

    return ChatDetailResponse(
        thread_id=chat_detail.thread_view.thread_id,
        title=chat_detail.thread_view.title,
        security_blocked=chat_detail.thread_view.security_blocked,
        messages=[
            MessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                created_at=m.created_at,
                artifacts=artifacts_by_msg.get(m.id, []),
                trace_id=chat_detail.trace_ids.get(m.id),
                feedback_score=_feedback_for(m.id),
                redacted=m.redacted,
            )
            for m in chat_detail.messages
        ],
    )


@router.get("/chats/recent", response_model=ChatRecentResponse)
async def list_recent_chats(
    user: CurrentUser,
    service: ChatServiceDep,
    page: Pagination,
) -> ChatRecentResponse:
    thread_views, total = await service.list_recent(
        user.id, limit=page.limit, offset=page.offset
    )
    return ChatRecentResponse(
        items=[
            ChatRecentItem(
                thread_id=tv.thread_id,
                title=tv.title,
                project_id=tv.project_id,
                project_name=tv.project.name,
                updated_at=tv.updated_at,
                security_blocked=tv.security_blocked,
            )
            for tv in thread_views
        ],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )
