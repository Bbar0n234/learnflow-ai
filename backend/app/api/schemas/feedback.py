from __future__ import annotations

from pydantic import BaseModel


class FeedbackRequest(BaseModel):
    trace_id: str
    score: bool | None  # true=like, false=dislike, null=delete


class FeedbackResponse(BaseModel):
    status: str
