from __future__ import annotations

import json
from collections.abc import AsyncIterator

import structlog
from fastapi import APIRouter, Depends
from starlette.responses import StreamingResponse

from app.api.deps import (
    ChatServiceDep,
    CurrentUser,
    UserProject,
    UserThread,
    require_unblocked_thread,
)
from app.api.schemas.messages import CancelResponse, MessageCreate
from app.security_pipeline.context import bind_security_context
from app.services.agent_runner import StreamEvent

router = APIRouter(tags=["messages"])

logger = structlog.get_logger()


async def _event_generator(
    events: AsyncIterator[StreamEvent],
) -> AsyncIterator[str]:
    """Map StreamEvent objects to SSE wire format.

    Wraps the iteration in try/except so exceptions in the setup phase of the
    runner (before its own try-block) or in JSON serialisation produce a
    terminal ``{"type":"error"}`` event rather than a silent stream tear.
    The runner (T3) already emits error events for in-graph exceptions; this
    catch covers the residual gap (setup failures, serialisation errors).
    """
    try:
        async for event in events:
            payload = {"type": event.type, **event.data}
            yield f"data: {json.dumps(payload)}\n\n"
    except Exception:
        logger.error("sse stream error", exc_info=True)
        error_payload = json.dumps({"type": "error", "message": "Stream failed"})
        yield f"data: {error_payload}\n\n"


@router.post(
    "/projects/{project_id}/chats/{chat_id}/messages",
    dependencies=[Depends(require_unblocked_thread)],
)
async def send_message(
    body: MessageCreate,
    project: UserProject,
    # Ownership пре-валидируется до создания стрима (контракт из feat-004)
    thread: UserThread,
    user: CurrentUser,
    service: ChatServiceDep,
) -> StreamingResponse:
    # Bind thread_id and project_id to security context for logging
    bind_security_context(
        thread_id=str(thread.thread_id),
        project_id=str(project.id),
    )

    events = service.send_message(
        thread_id=thread.thread_id,
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
    thread: UserThread,
    service: ChatServiceDep,
) -> CancelResponse:
    result = await service.cancel(thread_id=thread.thread_id)
    return CancelResponse(ok=result)
