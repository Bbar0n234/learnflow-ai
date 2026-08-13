from __future__ import annotations

import unicodedata
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

# Sanity ceilings against garbage input, not a business rule (design-brief
# never sizes an attachment count/path length): the backend is meant to be
# the sole source of these strings — `POST /uploads` returns them verbatim
# (§ Вложения пользователя) — but the schema shouldn't trust that a client
# actually round-tripped through it. A generous headroom over any real
# `uploads/<name>` path or realistic drag-and-drop batch.
_MAX_ATTACHMENTS = 50
_MAX_ATTACHMENT_PATH_LENGTH = 1024

# The one shape `POST /uploads` ever hands back (`UploadWorkspaceService.
# save_upload`): the `uploads/` zone name — `app.storage.workspace.
# UPLOADS_DIR`, spelled out here because the API layer reaches storage only
# through services — plus one sanitized basename. Not imported from there and
# not derived from the request: this is a literal echo of the contract the
# upload response already published.
_UPLOADS_PREFIX = "uploads/"

# unicodedata categories starting with "C" are control/format/surrogate —
# `sanitize_filename` strips exactly those from an upload's basename, so a
# genuine path never carries one. A newline is the one that matters most: the
# note built from these paths is prose handed to the model, and a control
# character is how a client would try to forge structure inside it.
_CONTROL_CATEGORY_PREFIX = "C"


def _validate_attachment_path(value: str) -> str:
    """Accept only the canonical `uploads/<name>` path the backend itself issued.

    These strings are not data the model merely sees — they are pasted into
    the attachment note appended to the user's message (`AgentRunner.stream`,
    design-brief § Вложения пользователя: «пометку формирует backend, не
    фронт») and stored in the checkpoint. A free-form string there is client
    input wearing the system's voice, so the schema pins the exact form the
    upload endpoint produces instead of the length ceilings alone: the zone
    prefix, then a single path segment that is neither a traversal step nor a
    nested path. Anything else is a 422 through the ordinary validation
    handler (`app/api/problem.py` → `urn:learnflow:validation-error`).

    Not a security boundary in its own right — the file layer refuses to
    resolve a path out of the workspace regardless (ADR-032 § Границы путей).
    This closes the injection surface that sits *before* that boundary.
    """
    if not value.startswith(_UPLOADS_PREFIX):
        raise ValueError("attachment path must be inside the uploads/ zone")

    name = value.removeprefix(_UPLOADS_PREFIX)
    # A basename, not a path: `save_upload` writes straight into `uploads/`,
    # so a separator (either one — uploads may arrive from any client OS) or
    # a `.`/`..` step is something no upload response ever returned.
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise ValueError("attachment path must be uploads/<filename>")
    if any(
        unicodedata.category(ch).startswith(_CONTROL_CATEGORY_PREFIX) for ch in name
    ):
        raise ValueError("attachment filename must not contain control characters")
    return value


AttachmentPath = Annotated[
    str,
    Field(min_length=1, max_length=_MAX_ATTACHMENT_PATH_LENGTH),
    AfterValidator(_validate_attachment_path),
]


class MessageCreate(BaseModel):
    content: str
    # Paths returned by `POST /uploads` (design-brief § Вложения
    # пользователя) — the backend, not the client, turns these into the
    # in-model attachment note and the message's `attachments` metadata.
    attachments: Annotated[
        list[AttachmentPath],
        Field(max_length=_MAX_ATTACHMENTS),
    ] = []


class CancelResponse(BaseModel):
    ok: bool
