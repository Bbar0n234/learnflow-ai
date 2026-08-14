from __future__ import annotations

from typing import Any

import anyio.to_thread
import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request, status
from langfuse import get_client

from app.api.deps import SettingsDep, UserThread
from app.api.schemas.feedback import FeedbackResponse, FeedbackSet
from app.services.exceptions import UpstreamUnavailableError
from app.storage.trace_store import TraceStore

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
        raise HTTPException(
            status_code=503, detail="Хранилище фидбека недоступно, попробуйте позже"
        )
    store = TraceStore(redis_client)
    trace_ids = await store.get_by_thread(thread.thread_id)
    if trace_id not in trace_ids.values():
        raise HTTPException(status_code=404, detail="Трейс не найден")
    return store


def _get_langfuse_client() -> Any:
    try:
        return get_client()
    except Exception as exc:
        logger.warning("langfuse not available for feedback", exc_info=True)
        raise UpstreamUnavailableError(
            code="langfuse-unavailable",
            status=503,
            detail="Сервис фидбека недоступен, попробуйте позже",
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
        # flush() блокирует до выгрузки очереди SDK — уводим из event loop
        await anyio.to_thread.run_sync(langfuse.flush)
    except (httpx.HTTPError, httpx.TimeoutException, OSError, ConnectionError) as e:
        logger.warning("langfuse feedback error", exc_info=True)
        raise UpstreamUnavailableError(
            code="langfuse-unavailable",
            status=503,
            detail="Сервис фидбека недоступен, попробуйте позже",
        ) from e
    # Other exceptions (TypeError, AttributeError, etc.) bubble to the
    # generic barrier (500) — not masked as 503.

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
    settings: SettingsDep,
) -> None:
    store = await _get_owned_trace_store(request, thread, trace_id)
    langfuse = _get_langfuse_client()

    try:
        await _delete_score_via_api(
            base_url=settings.langfuse_base_url,
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            score_id=_score_id(trace_id),
        )
        # flush() блокирует до выгрузки очереди SDK — уводим из event loop
        await anyio.to_thread.run_sync(langfuse.flush)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            pass  # Score already deleted — idempotent
        else:
            logger.warning("langfuse feedback delete error", exc_info=True)
            raise UpstreamUnavailableError(
                code="langfuse-unavailable",
                status=503,
                detail="Сервис фидбека недоступен, попробуйте позже",
            ) from e
    except (httpx.HTTPError, httpx.TimeoutException, OSError, ConnectionError) as e:
        logger.warning("langfuse feedback delete error", exc_info=True)
        raise UpstreamUnavailableError(
            code="langfuse-unavailable",
            status=503,
            detail="Сервис фидбека недоступен, попробуйте позже",
        ) from e
    # Other exceptions (TypeError, AttributeError, etc.) bubble to the
    # generic barrier (500) — not masked as 503.

    try:
        await store.save_feedback(trace_id, None)
    except Exception:
        logger.warning("feedback redis delete failed", exc_info=True)


async def _delete_score_via_api(
    *, base_url: str, public_key: str, secret_key: str, score_id: str
) -> None:
    """Delete a score via Langfuse REST API (no SDK method available)."""
    async with httpx.AsyncClient() as client:
        resp = await client.delete(
            f"{base_url}/api/public/scores/{score_id}",
            auth=(public_key, secret_key),
        )
    resp.raise_for_status()
