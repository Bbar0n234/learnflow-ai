from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from starlette.responses import StreamingResponse

from app.api.deps import (
    ChatServiceDep,
    CurrentUser,
    DBSession,
    UserProject,
    require_unblocked_thread,
)
from app.api.schemas.messages import CancelResponse, MessageCreate
from app.repositories.thread_view import ThreadViewRepository
from app.security_pipeline.context import bind_security_context
from app.services.agent_runner import StreamEvent

router = APIRouter(tags=["messages"])


async def _validate_thread_ownership(
    session: DBSession,
    chat_id: uuid.UUID,
    project_id: uuid.UUID,
) -> None:
    """Pre-validate that thread belongs to project before streaming."""
    repo = ThreadViewRepository(session)
    thread_view = await repo.get_by_id(chat_id)
    if thread_view is None or thread_view.project_id != project_id:
        raise HTTPException(status_code=404, detail="Chat not found")


async def _event_generator(
    events: AsyncIterator[StreamEvent],
) -> AsyncIterator[str]:
    """Map StreamEvent objects to SSE wire format."""
    async for event in events:
        payload = {"type": event.type, **event.data}
        yield f"data: {json.dumps(payload)}\n\n"


@router.post(
    "/projects/{project_id}/chats/{chat_id}/messages",
    dependencies=[Depends(require_unblocked_thread)],
)
async def send_message(
    chat_id: uuid.UUID,
    body: MessageCreate,
    project: UserProject,
    user: CurrentUser,
    service: ChatServiceDep,
    session: DBSession,
) -> StreamingResponse:
    # Pre-validate before creating stream (contract from feat-004)
    await _validate_thread_ownership(session, chat_id, project.id)

    # Bind thread_id and project_id to security context for logging
    bind_security_context(
        thread_id=str(chat_id),
        project_id=str(project.id),
    )

    events = service.send_message(
        thread_id=chat_id,
        project_id=project.id,
        user_id=user.id,
        content=body.content,
    )
    return StreamingResponse(
        _event_generator(events),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/projects/{project_id}/chats/{chat_id}/cancel",
    response_model=CancelResponse,
)
async def cancel_message(
    chat_id: uuid.UUID,
    project: UserProject,
    service: ChatServiceDep,
    session: DBSession,
) -> CancelResponse:
    await _validate_thread_ownership(session, chat_id, project.id)
    result = await service.cancel(thread_id=chat_id)
    return CancelResponse(ok=result)
