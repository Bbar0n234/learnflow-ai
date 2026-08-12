from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

# Sanity ceilings against garbage input, not a business rule (design-brief
# never sizes an attachment count/path length): the backend is meant to be
# the sole source of these strings — `POST /uploads` returns them verbatim
# (§ Вложения пользователя) — but the schema shouldn't trust that a client
# actually round-tripped through it. A generous headroom over any real
# `uploads/<name>` path or realistic drag-and-drop batch.
_MAX_ATTACHMENTS = 50
_MAX_ATTACHMENT_PATH_LENGTH = 1024


class MessageCreate(BaseModel):
    content: str
    # Paths returned by `POST /uploads` (design-brief § Вложения
    # пользователя) — the backend, not the client, turns these into the
    # in-model attachment note and the message's `attachments` metadata.
    attachments: Annotated[
        list[
            Annotated[str, Field(min_length=1, max_length=_MAX_ATTACHMENT_PATH_LENGTH)]
        ],
        Field(max_length=_MAX_ATTACHMENTS),
    ] = []


class CancelResponse(BaseModel):
    ok: bool
