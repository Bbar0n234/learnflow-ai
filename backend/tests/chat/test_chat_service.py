"""Sociable-unit tests for ``ChatService`` orchestration.

Collaborators are in-memory fakes (runner, repos, trace store); no DB, no
network. Focus is the service's own branching: trace-id filtering, artifact
linking, the error-vs-done terminal contract, and graceful degradation when the
trace store fails. These are the behaviours that can't be observed cleanly
through the HTTP layer.
"""

from __future__ import annotations

import uuid

import pytest
from app.models.thread_view import ThreadView
from app.services.agent_runner import Message, StreamEvent
from app.services.chat import ChatService
from app.services.exceptions import EntityNotFoundError

from tests.chat.conftest import (
    FakeAgentRunner,
    FakeArtifactRepo,
    FakeThreadViewRepo,
    FakeTraceStore,
)

pytestmark = pytest.mark.unit


def _thread(project_id: uuid.UUID | None = None) -> ThreadView:
    return ThreadView(
        thread_id=uuid.uuid4(),
        project_id=project_id or uuid.uuid4(),
        title="Chat",
    )


def _build_service(
    *,
    thread_repo: FakeThreadViewRepo,
    runner: FakeAgentRunner,
    artifact_repo: FakeArtifactRepo | None = None,
    trace_store: FakeTraceStore | None = None,
) -> ChatService:
    return ChatService(
        thread_view_repo=thread_repo,  # type: ignore[arg-type]
        agent_runner=runner,  # AgentRunner is a Protocol — FakeAgentRunner fits
        artifact_repo=artifact_repo or FakeArtifactRepo(),  # type: ignore[arg-type]
        trace_store=trace_store,  # type: ignore[arg-type]
        session=None,
    )


async def _drain(service: ChatService, thread: ThreadView) -> list[StreamEvent]:
    return [
        event
        async for event in service.send_message(
            thread_id=thread.thread_id,
            project_id=thread.project_id,
            user_id=uuid.uuid4(),
            content="hi",
        )
    ]


# --- create / list ---------------------------------------------------------


async def test_create_chat_returns_thread_view_with_given_title() -> None:
    repo = FakeThreadViewRepo()
    service = _build_service(thread_repo=repo, runner=FakeAgentRunner())

    result = await service.create_chat(project_id=uuid.uuid4(), title="My chat")

    assert result.title == "My chat"
    assert result.thread_id in repo.threads


async def test_list_chats_returns_items_and_total() -> None:
    project_id = uuid.uuid4()
    repo = FakeThreadViewRepo()
    repo.add(_thread(project_id))
    repo.add(_thread(project_id))
    service = _build_service(thread_repo=repo, runner=FakeAgentRunner())

    items, total = await service.list_chats(project_id)

    assert total == 2
    assert len(items) == 2


# --- get_chat --------------------------------------------------------------


async def test_get_chat_missing_thread_raises_not_found() -> None:
    service = _build_service(thread_repo=FakeThreadViewRepo(), runner=FakeAgentRunner())

    with pytest.raises(EntityNotFoundError):
        await service.get_chat(uuid.uuid4())


async def test_get_chat_returns_history_with_trace_ids_and_feedback() -> None:
    thread = _thread()
    repo = FakeThreadViewRepo()
    repo.add(thread)
    runner = FakeAgentRunner()
    runner.history = [Message(id="m1", role="assistant", content="hello")]
    trace_store = FakeTraceStore(
        by_thread={thread.thread_id: {"m1": "tr-1"}},
        feedback={"tr-1": True},
    )
    service = _build_service(thread_repo=repo, runner=runner, trace_store=trace_store)

    detail = await service.get_chat(thread.thread_id)

    assert [m.content for m in detail.messages] == ["hello"]
    assert detail.trace_ids == {"m1": "tr-1"}
    assert detail.feedback_scores == {"tr-1": True}


async def test_get_chat_degrades_when_trace_lookup_fails() -> None:
    thread = _thread()
    repo = FakeThreadViewRepo()
    repo.add(thread)
    runner = FakeAgentRunner()
    runner.history = [Message(id="m1", role="assistant", content="hi")]
    trace_store = FakeTraceStore(raise_on_get_by_thread=True)
    service = _build_service(thread_repo=repo, runner=runner, trace_store=trace_store)

    detail = await service.get_chat(thread.thread_id)

    # History still served; trace data silently empty (Redis is non-critical).
    assert [m.content for m in detail.messages] == ["hi"]
    assert detail.trace_ids == {}
    assert detail.feedback_scores == {}


async def test_get_chat_degrades_when_feedback_batch_fails() -> None:
    thread = _thread()
    repo = FakeThreadViewRepo()
    repo.add(thread)
    runner = FakeAgentRunner()
    trace_store = FakeTraceStore(
        by_thread={thread.thread_id: {"m1": "tr-1"}},
        raise_on_feedback_batch=True,
    )
    service = _build_service(thread_repo=repo, runner=runner, trace_store=trace_store)

    detail = await service.get_chat(thread.thread_id)

    assert detail.trace_ids == {"m1": "tr-1"}
    assert detail.feedback_scores == {}


# --- send_message orchestration -------------------------------------------


async def test_send_message_missing_thread_raises_not_found() -> None:
    service = _build_service(thread_repo=FakeThreadViewRepo(), runner=FakeAgentRunner())

    with pytest.raises(EntityNotFoundError):
        await _drain(service, _thread())


async def test_send_message_filters_trace_id_and_appends_done() -> None:
    thread = _thread()
    repo = FakeThreadViewRepo()
    repo.add(thread)
    runner = FakeAgentRunner()
    runner.last_ai_message_id = "m1"
    runner.events = [
        StreamEvent(type="trace_id", data={"trace_id": "tr-9"}),
        StreamEvent(type="token", data={"content": "Hello"}),
        StreamEvent(type="token", data={"content": " world"}),
    ]
    service = _build_service(thread_repo=repo, runner=runner)

    events = await _drain(service, thread)

    # trace_id event is consumed internally, never forwarded.
    assert [e.type for e in events] == ["token", "token", "done"]
    done = events[-1]
    assert done.data == {"message_id": "m1", "trace_id": "tr-9"}
    assert thread.thread_id in repo.touched


async def test_send_message_links_created_artifacts_to_message() -> None:
    thread = _thread()
    repo = FakeThreadViewRepo()
    repo.add(thread)
    artifact_id = uuid.uuid4()
    runner = FakeAgentRunner()
    runner.last_ai_message_id = "msg-1"
    runner.events = [
        StreamEvent(type="artifact_created", data={"id": str(artifact_id)}),
    ]
    artifact_repo = FakeArtifactRepo()
    service = _build_service(
        thread_repo=repo, runner=runner, artifact_repo=artifact_repo
    )

    await _drain(service, thread)

    assert artifact_repo.set_message_id_calls == [([artifact_id], "msg-1")]


@pytest.mark.parametrize("terminal_type", ["error", "security_block"])
async def test_send_message_terminal_failure_skips_done(terminal_type: str) -> None:
    thread = _thread()
    repo = FakeThreadViewRepo()
    repo.add(thread)
    runner = FakeAgentRunner()
    runner.events = [
        StreamEvent(type="token", data={"content": "partial"}),
        StreamEvent(type=terminal_type, data={"message": "stopped"}),
    ]
    service = _build_service(thread_repo=repo, runner=runner)

    events = await _drain(service, thread)

    # error and done are mutually exclusive terminal events (SSE contract).
    assert [e.type for e in events] == ["token", terminal_type]
    assert all(e.type != "done" for e in events)


async def test_send_message_saves_trace_id_to_store() -> None:
    thread = _thread()
    repo = FakeThreadViewRepo()
    repo.add(thread)
    runner = FakeAgentRunner()
    runner.last_ai_message_id = "m1"
    runner.events = [StreamEvent(type="trace_id", data={"trace_id": "tr-7"})]
    trace_store = FakeTraceStore()
    service = _build_service(thread_repo=repo, runner=runner, trace_store=trace_store)

    await _drain(service, thread)

    assert trace_store.saved == [(thread.thread_id, "m1", "tr-7")]


async def test_send_message_emits_done_when_post_hoc_resolution_fails() -> None:
    thread = _thread()
    repo = FakeThreadViewRepo()
    repo.add(thread)
    runner = FakeAgentRunner()
    runner.raise_on_last_id = True
    runner.events = [StreamEvent(type="token", data={"content": "ok"})]
    service = _build_service(thread_repo=repo, runner=runner)

    events = await _drain(service, thread)

    # Post-hoc message resolution failure is swallowed; stream still terminates
    # cleanly with a done carrying an empty message_id.
    assert events[-1].type == "done"
    assert events[-1].data["message_id"] == ""


# --- cancel ----------------------------------------------------------------


@pytest.mark.parametrize("expected", [True, False])
async def test_cancel_returns_runner_result(expected: bool) -> None:
    runner = FakeAgentRunner()
    runner.cancel_result = expected
    service = _build_service(thread_repo=FakeThreadViewRepo(), runner=runner)

    assert await service.cancel(thread_id=uuid.uuid4()) is expected
