from __future__ import annotations

import httpx
import structlog
from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser
from app.api.schemas.feedback import FeedbackRequest, FeedbackResponse
from app.config import Settings

logger = structlog.get_logger()

router = APIRouter(tags=["feedback"])

SCORE_NAME = "user-feedback"


def _score_id(trace_id: str) -> str:
    return f"{trace_id}-user-feedback"


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(body: FeedbackRequest, user: CurrentUser) -> FeedbackResponse:
    from langfuse import (
        get_client,  # lazy: avoid import error when langfuse not configured
    )

    try:
        langfuse = get_client()
    except Exception as exc:
        logger.warning("langfuse not available for feedback")
        raise HTTPException(
            status_code=503, detail="Observability service unavailable"
        ) from exc

    try:
        if body.score is None:
            settings = Settings()
            _delete_score_via_api(
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

    return FeedbackResponse(status="success")


def _delete_score_via_api(
    *, base_url: str, public_key: str, secret_key: str, score_id: str
) -> None:
    """Delete a score via Langfuse REST API (no SDK method available)."""
    resp = httpx.delete(
        f"{base_url}/api/public/scores/{score_id}",
        auth=(public_key, secret_key),
    )
    resp.raise_for_status()
