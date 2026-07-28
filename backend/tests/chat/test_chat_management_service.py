"""Sociable-unit tests for the rename/delete branches of ``ChatService``.

Only what the HTTP layer can't show cleanly lives here: the not-found contract
the routes translate into 404 / idempotent 204 — and specifically that it is
resolved *before* anything else the method needs, so a chat that isn't there is
reported as missing rather than as some downstream failure. Everything the
delete actually does (the disables cleanup, the row cascade, the degradation
when checkpoint cleanup fails) is SQL over a real session and lives in
``test_chat_management_routes.py``.
"""

from __future__ import annotations

import uuid

import pytest
from app.services.chat import ChatService
from app.services.exceptions import EntityNotFoundError

from tests.chat.conftest import FakeAgentRunner, FakeArtifactRepo, FakeThreadViewRepo

pytestmark = pytest.mark.unit


def _build_service(
    *, thread_repo: FakeThreadViewRepo, runner: FakeAgentRunner
) -> ChatService:
    return ChatService(
        thread_view_repo=thread_repo,  # type: ignore[arg-type]
        agent_runner=runner,  # AgentRunner is a Protocol — FakeAgentRunner fits
        artifact_repo=FakeArtifactRepo(),  # type: ignore[arg-type]
        trace_store=None,
        session=None,
    )


async def test_rename_chat_missing_thread_raises_not_found() -> None:
    service = _build_service(thread_repo=FakeThreadViewRepo(), runner=FakeAgentRunner())

    with pytest.raises(EntityNotFoundError):
        await service.rename_chat(uuid.uuid4(), title="Новое имя")


async def test_delete_chat_missing_thread_raises_not_found() -> None:
    service = _build_service(thread_repo=FakeThreadViewRepo(), runner=FakeAgentRunner())

    # A chat that isn't there is "not found" — and stays so even though this
    # service was built without a session, i.e. the existence check wins over
    # everything the deletion would otherwise need. That ordering is what lets
    # the route answer an idempotent 204 for an already-deleted chat.
    with pytest.raises(EntityNotFoundError):
        await service.delete_chat(uuid.uuid4())
