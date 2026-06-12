from __future__ import annotations

import anyio.to_thread
import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request

from app.api.deps import CurrentUser, SettingsDep
from app.api.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.repositories.trace_store import TraceStore

logger = structlog.get_logger()

router = APIRouter(tags=["feedback"])

SCORE_NAME = "user-feedback"


def _score_id(trace_id: str) -> str:
    return f"{trace_id}-user-feedback"


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    body: FeedbackRequest, user: CurrentUser, request: Request, settings: SettingsDep
) -> FeedbackResponse:
    # lazy: avoid import error when langfuse is not configured
    from langfuse import get_client  # noqa: PLC0415

    try:
        langfuse = get_client()
    except Exception as exc:
        logger.warning("langfuse not available for feedback")
        raise HTTPException(
            status_code=503, detail="Observability service unavailable"
        ) from exc

    try:
        if body.score is None:
            await _delete_score_via_api(
                base_url=settings.langfuse_base_url,
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                score_id=_score_id(body.trace_id),
            )
        else:
            langfuse.create_score(
                trace_id=body.trace_id,
                name=SCORE_NAME,
                value=1 if body.score else 0,
                data_type="BOOLEAN",
                score_id=_score_id(body.trace_id),
            )
        # flush() блокирует до выгрузки очереди SDK — уводим из event loop
        await anyio.to_thread.run_sync(langfuse.flush)
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

    # Persist feedback score in Redis (survives localStorage clearing)
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client:
        try:
            store = TraceStore(redis_client)
            await store.save_feedback(body.trace_id, body.score)
        except Exception:
            logger.warning("feedback redis save failed", exc_info=True)

    return FeedbackResponse(status="success")


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
