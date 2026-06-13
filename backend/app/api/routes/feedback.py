from __future__ import annotations

from typing import Any

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request, status

from app.api.deps import UserThread
from app.api.schemas.feedback import FeedbackResponse, FeedbackSet
from app.config import Settings
from app.repositories.trace_store import TraceStore

logger = structlog.get_logger()

router = APIRouter(tags=["feedback"])

SCORE_NAME = "user-feedback"


def _score_id(trace_id: str) -> str:
    return f"{trace_id}-user-feedback"


async def _get_owned_trace_store(
    request: Request, thread: UserThread, trace_id: str
) -> TraceStore:
    """Verify the trace belongs to the user's chat; return the trace store."""
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        raise HTTPException(status_code=503, detail="Feedback store unavailable")
    store = TraceStore(redis_client)
    trace_ids = await store.get_by_thread(thread.thread_id)
    if trace_id not in trace_ids.values():
        raise HTTPException(status_code=404, detail="Trace not found")
    return store


def _get_langfuse_client() -> Any:
    # lazy: avoid import error when langfuse is not configured
    from langfuse import get_client  # noqa: PLC0415

    try:
        return get_client()
    except Exception as exc:
        logger.warning("langfuse not available for feedback")
        raise HTTPException(
            status_code=503, detail="Observability service unavailable"
        ) from exc


@router.put(
    "/projects/{project_id}/chats/{chat_id}/feedback/{trace_id}",
    response_model=FeedbackResponse,
)
async def set_feedback(
    trace_id: str,
    body: FeedbackSet,
    thread: UserThread,
    request: Request,
) -> FeedbackResponse:
    store = await _get_owned_trace_store(request, thread, trace_id)
    langfuse = _get_langfuse_client()

    try:
        langfuse.create_score(
            trace_id=trace_id,
            name=SCORE_NAME,
            value=1 if body.score else 0,
            data_type="BOOLEAN",
            score_id=_score_id(trace_id),
        )
        langfuse.flush()
    except Exception as e:
        logger.warning("langfuse feedback error", error=str(e))
        raise HTTPException(
            status_code=503, detail="Observability service unavailable"
        ) from e

    # Persist feedback score in Redis (survives localStorage clearing)
    try:
        await store.save_feedback(trace_id, body.score)
    except Exception:
        logger.warning("feedback redis save failed", exc_info=True)

    return FeedbackResponse(trace_id=trace_id, score=body.score)


@router.delete(
    "/projects/{project_id}/chats/{chat_id}/feedback/{trace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_feedback(
    trace_id: str,
    thread: UserThread,
    request: Request,
) -> None:
    store = await _get_owned_trace_store(request, thread, trace_id)
    langfuse = _get_langfuse_client()

    try:
        settings = Settings()
        _delete_score_via_api(
            base_url=settings.langfuse_base_url,
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            score_id=_score_id(trace_id),
        )
        langfuse.flush()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            pass  # Score already deleted — idempotent
        else:
            logger.warning("langfuse feedback error", error=str(e))
            raise HTTPException(
                status_code=503, detail="Observability service unavailable"
            ) from e
    except Exception as e:
        logger.warning("langfuse feedback error", error=str(e))
        raise HTTPException(
            status_code=503, detail="Observability service unavailable"
        ) from e

    try:
        await store.save_feedback(trace_id, None)
    except Exception:
        logger.warning("feedback redis delete failed", exc_info=True)


def _delete_score_via_api(
    *, base_url: str, public_key: str, secret_key: str, score_id: str
) -> None:
    """Delete a score via Langfuse REST API (no SDK method available)."""
    resp = httpx.delete(
        f"{base_url}/api/public/scores/{score_id}",
        auth=(public_key, secret_key),
    )
    resp.raise_for_status()
