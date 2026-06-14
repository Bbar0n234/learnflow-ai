from __future__ import annotations

from pydantic import BaseModel


class FeedbackSet(BaseModel):
    score: bool  # true=like, false=dislike


class FeedbackResponse(BaseModel):
    trace_id: str
    score: bool
