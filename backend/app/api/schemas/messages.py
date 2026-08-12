from __future__ import annotations

from pydantic import BaseModel


class MessageCreate(BaseModel):
    content: str
    # Paths returned by `POST /uploads` (design-brief § Вложения
    # пользователя) — the backend, not the client, turns these into the
    # in-model attachment note and the message's `attachments` metadata.
    attachments: list[str] = []


class CancelResponse(BaseModel):
    ok: bool
