"""Uploads REST — POST-only entry point for user-attached files (ADR-032, T1.8).

One multipart file per request, written into the project workspace's
`uploads/` zone through the file layer — no PG row, no separate ingestion
step: the agent reads the file back itself (`read_file` for text formats,
`execute_code`/`run_command` — pandoc — for binary ones), the same "runtime
*is* ingestion" contract as everywhere else in this workspace model
(design-brief § Вложения пользователя).

Naming and collision handling mirror `generate_image`
(`app/agent/tools/image_generation.py`): sanitize the client-supplied
filename to a safe basename, then append a numeric suffix on collision so a
repeated upload never overwrites the file an older chat message's metadata
still points at. That logic lives in `UploadWorkspaceService`
(`app/services/upload_workspace.py`) — this module never imports
`app.storage` directly (import-linter contract, see that service's
docstring).

No REST read of this zone: the UI chip renders from `MessageOut.attachments`
metadata (populated when the message is sent), not by fetching the file back
— the chip is non-clickable in v1, so only this one write route exists.
"""

from __future__ import annotations

import anyio.to_thread
from fastapi import APIRouter, UploadFile, status
from pydantic import BaseModel

from app.api.deps import SettingsDep, UploadWorkspaceServiceDep, UserProject
from app.services.exceptions import PayloadTooLargeError

router = APIRouter(tags=["uploads"])

# Read in chunks rather than one `await file.read()` so an oversized upload
# is rejected before the whole body sits in memory as a single `bytes`
# object — `UploadFile` itself already spools past ~1MB to a temp file, but
# accumulating unboundedly on our side would defeat that.
_READ_CHUNK_BYTES = 1 << 20


class UploadResponse(BaseModel):
    path: str


def _size_limit_detail(limit: int) -> str:
    human = f"{limit // 1_000_000} МБ" if limit >= 1_000_000 else f"{limit} байт"
    return f"Файл больше {human} — уменьшите его и попробуйте снова"


async def _read_within_limit(file: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise PayloadTooLargeError(detail=_size_limit_detail(limit))
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/projects/{project_id}/uploads",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_file(
    project: UserProject,
    uploads: UploadWorkspaceServiceDep,
    settings: SettingsDep,
    file: UploadFile,
) -> UploadResponse:
    data = await _read_within_limit(file, settings.upload_max_size_bytes)
    path = await anyio.to_thread.run_sync(
        uploads.save_upload, str(project.id), file.filename or "", data
    )
    return UploadResponse(path=path)
