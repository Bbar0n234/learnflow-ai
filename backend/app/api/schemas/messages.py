from __future__ import annotations

from pydantic import BaseModel


class MessageCreate(BaseModel):
    content: str


class CancelResponse(BaseModel):
    ok: bool
