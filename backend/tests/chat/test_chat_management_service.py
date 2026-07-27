"""Sociable-unit tests for the rename/delete branches of ``ChatService``.

Only what the HTTP layer can't show cleanly lives here: the not-found contract
the routes translate into 404 / idempotent 204, and the shape of the degradation
when checkpoint cleanup fails (the warning, not just the surviving request).
The cascade itself is SQL and is covered by ``test_chat_management_routes.py``.
"""

from __future__ import annotations

import uuid

import pytest
from app.models.thread_view import ThreadView
from app.services.chat import ChatService
from app.services.constants import DEFAULT_CHAT_TITLE
from app.services.exceptions import EntityNotFoundError
from structlog.testing import capture_logs

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


def _thread() -> ThreadView:
    return ThreadView(
        thread_id=uuid.uuid4(), project_id=uuid.uuid4(), title=DEFAULT_CHAT_TITLE
    )


async def test_rename_chat_missing_thread_raises_not_found() -> None:
    service = _build_service(thread_repo=FakeThreadViewRepo(), runner=FakeAgentRunner())

    with pytest.raises(EntityNotFoundError):
        await service.rename_chat(uuid.uuid4(), title="Новое имя")


async def test_delete_chat_missing_thread_raises_not_found() -> None:
    service = _build_service(thread_repo=FakeThreadViewRepo(), runner=FakeAgentRunner())

    with pytest.raises(EntityNotFoundError):
        await service.delete_chat(uuid.uuid4())


async def test_delete_chat_warns_but_completes_when_checkpoint_cleanup_fails() -> None:
    thread = _thread()
    repo = FakeThreadViewRepo()
    repo.add(thread)
    runner = FakeAgentRunner()
    runner.raise_on_delete_thread = True
    service = _build_service(thread_repo=repo, runner=runner)

    with capture_logs() as logs:
        await service.delete_chat(thread.thread_id)

    # The chat is gone regardless of the checkpointer; the orphaned checkpoints
    # are recorded as a warning, not raised at the caller.
    assert thread.thread_id not in repo.threads
    warnings = [
        entry
        for entry in logs
        if entry["log_level"] == "warning"
        and entry["event"] == "checkpoint thread deletion failed"
    ]
    assert len(warnings) == 1
