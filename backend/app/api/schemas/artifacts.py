"""Artifact REST schemas — file-backed model (ADR-032).

`path` (relative to the `artifacts/` zone) is the artifact's identity, not a
PG UUID; `type` is the file extension without the leading dot (same helper as
`ArtifactPart`/the SSE wire payload — `app.storage.workspace.artifact_type`);
`updated_at` is the file's mtime, not a PG `created_at` column (a rewrite
changes it — design-brief § Метаданные). `thread_id`/`message_id` are gone
with the PG «artifact ↝ message» link (superseded by `ArtifactPart` in the
checkpoint history, T1.2).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.api.schemas.common import Page


class ArtifactListItem(BaseModel):
    path: str
    title: str
    type: str
    updated_at: datetime


class ArtifactListResponse(Page[ArtifactListItem]):
    pass


class ArtifactDetailResponse(BaseModel):
    path: str
    title: str
    type: str
    updated_at: datetime
    # None for a binary file — metadata only, body comes from `/media`
    # (design-brief § Метаданные). Excluded from the wire payload rather than
    # emitted as a JSON `null` (`response_model_exclude_none` on the route) —
    # matches the frontend DTO's optional `content?` (T2, already shipped).
    content: str | None = None
