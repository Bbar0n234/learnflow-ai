"""PgBlobStorage — integration against real Postgres (transactional rollback).

Blobs are the first binary data in the system. This pins the storage contract
the media endpoint and the ``generate_image`` tool depend on: ``put`` then
``get`` round-trips exact bytes + mime; ``get`` of an absent artifact is
``None`` (the endpoint's 404 signal); ``delete`` removes the row. Real Postgres
because this is the SQL/``bytea`` layer — a fake would test nothing.
"""

from __future__ import annotations

import uuid

import pytest
from app.repositories.artifact import ArtifactRepository
from app.repositories.blob_storage import PgBlobStorage
from learnflow_testing.factories import ProjectFactory
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration

_PNG = bytes(range(256)) * 4  # non-ASCII bytes -> proves true binary round-trip


async def _make_image_artifact(session: AsyncSession) -> uuid.UUID:
    project = await ProjectFactory.create()
    artifact = await ArtifactRepository(session).create(
        project_id=project.id, title="img", type="image", content="the prompt"
    )
    return artifact.id


async def test_put_then_get_round_trips_bytes_and_mime(
    db_session: AsyncSession,
) -> None:
    artifact_id = await _make_image_artifact(db_session)
    storage = PgBlobStorage(db_session)

    await storage.put(artifact_id=artifact_id, data=_PNG, mime_type="image/png")
    result = await storage.get(artifact_id)

    assert result is not None
    data, mime_type = result
    assert data == _PNG
    assert mime_type == "image/png"


async def test_get_missing_returns_none(db_session: AsyncSession) -> None:
    storage = PgBlobStorage(db_session)

    assert await storage.get(uuid.uuid4()) is None


async def test_delete_removes_blob(db_session: AsyncSession) -> None:
    artifact_id = await _make_image_artifact(db_session)
    storage = PgBlobStorage(db_session)
    await storage.put(artifact_id=artifact_id, data=_PNG, mime_type="image/png")

    await storage.delete(artifact_id)

    assert await storage.get(artifact_id) is None


async def test_delete_absent_blob_is_noop(db_session: AsyncSession) -> None:
    storage = PgBlobStorage(db_session)

    # No row to delete -> no error (idempotent).
    await storage.delete(uuid.uuid4())
