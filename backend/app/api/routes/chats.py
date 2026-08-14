from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import (
    ChatServiceDep,
    CurrentUser,
    Pagination,
    UserProject,
    UserThread,
)
from app.api.schemas.chats import (
    ArtifactDiffOut,
    ArtifactPartOut,
    AttachmentOut,
    ChatDetailResponse,
    ChatListResponse,
    ChatRecentItem,
    ChatRecentResponse,
    ChatResponse,
    ChatUpdate,
    MessageOut,
    MessagePartOut,
    ReasoningPartOut,
    TextPartOut,
    ToolCallPartOut,
)
from app.services.agent_runner import (
    ArtifactPart,
    Part,
    ReasoningPart,
    TextPart,
    ToolCallPart,
)
from app.services.exceptions import EntityNotFoundError

router = APIRouter(tags=["chats"])


def _part_out(part: Part) -> MessagePartOut:
    """Map the internal typed ``Part`` (services layer) to its API shape."""
    if isinstance(part, ReasoningPart):
        return ReasoningPartOut(content=part.content)
    if isinstance(part, TextPart):
        return TextPartOut(content=part.content)
    if isinstance(part, ToolCallPart):
        return ToolCallPartOut(
            call_id=part.call_id,
            tool=part.tool,
            args=part.args,
            args_truncated=part.args_truncated,
            status=part.status,
            result_preview=part.result_preview,
            result_truncated=part.result_truncated,
        )
    if isinstance(part, ArtifactPart):
        return ArtifactPartOut(
            path=part.path,
            title=part.title,
            artifact_type=part.type,
            kind=part.kind,
            diff=ArtifactDiffOut(**part.diff) if part.diff else None,
        )
    raise AssertionError(f"unhandled part type: {type(part).__name__}")


@router.post(
    "/projects/{project_id}/chats",
    response_model=ChatResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat(
    project: UserProject,
    service: ChatServiceDep,
) -> ChatResponse:
    thread_view = await service.create_chat(project_id=project.id)
    return ChatResponse.model_validate(thread_view)


@router.put("/projects/{project_id}/chats/{chat_id}", response_model=ChatResponse)
async def rename_chat(
    body: ChatUpdate,
    thread: UserThread,
    service: ChatServiceDep,
) -> ChatResponse:
    updated = await service.rename_chat(thread.thread_id, title=body.title)
    return ChatResponse.model_validate(updated)


@router.delete(
    "/projects/{project_id}/chats/{chat_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_chat(
    chat_id: uuid.UUID,
    project: UserProject,
    service: ChatServiceDep,
) -> Response:
    # Idempotent DELETE (api.md): ownership resolved manually here instead of
    # via the UserThread dependency, which would 404 an already-deleted chat
    # and break idempotency. Mirrors delete_project's manual pattern
    # (routes/projects.py) — a documented, deliberate exception to "ownership
    # only through dependencies" (design-brief § Rename и delete).
    try:
        thread_view = await service.get_thread_view(chat_id)
    except EntityNotFoundError:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if thread_view.project_id != project.id:
        raise HTTPException(status_code=404, detail="Чат не найден")
    await service.delete_chat(thread_view.thread_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
) -> ChatDetailResponse:
    chat_detail = await service.get_chat(thread.thread_id)

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
                trace_id=chat_detail.trace_ids.get(m.id),
                feedback_score=_feedback_for(m.id),
                redacted=m.redacted,
                parts=[_part_out(p) for p in m.parts],
                attachments=[
                    AttachmentOut(path=a.path, title=a.title) for a in m.attachments
                ],
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
