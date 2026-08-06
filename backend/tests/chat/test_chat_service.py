"""Sociable-unit tests for ``ChatService`` orchestration.

Collaborators are in-memory fakes (runner, repos, trace store); no DB, no
network. Focus is the service's own branching: trace-id filtering, artifact
linking, the error-vs-done terminal contract, and graceful degradation when the
trace store fails. These are the behaviours that can't be observed cleanly
through the HTTP layer.
"""

from __future__ import annotations

import ast
import uuid
from pathlib import Path

import pytest
from app.agent import heartbeat as heartbeat_module
from app.agent import runner as runner_module
from app.agent import stream_events as stream_events_module
from app.agent.subagents import runner as subagent_runner_module
from app.models.thread_view import ThreadView
from app.services import chat as chat_service_module
from app.services.agent_runner import Message, StreamEvent
from app.services.chat import ChatService
from app.services.constants import DEFAULT_CHAT_TITLE
from app.services.exceptions import EntityNotFoundError

from tests.chat.conftest import (
    RUNNER_FORWARDED_TYPES,
    SERVICE_SYNTHESISED_TYPES,
    FakeAgentRunner,
    FakeArtifactRepo,
    FakeThreadViewRepo,
    FakeTraceStore,
    agent_event_event,
    artifact_created_event,
    cancelled_event,
    error_event,
    heartbeat_event,
    reasoning_chunk_event,
    security_block_event,
    stream_started_event,
    text_chunk_event,
    tool_call_args_event,
    tool_call_cancelled_event,
    tool_call_started_event,
    tool_result_event,
    trace_id_event,
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


async def test_create_chat_returns_thread_view_with_placeholder_title() -> None:
    repo = FakeThreadViewRepo()
    service = _build_service(thread_repo=repo, runner=FakeAgentRunner())

    result = await service.create_chat(project_id=uuid.uuid4())

    assert result.title == DEFAULT_CHAT_TITLE
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
        trace_id_event("tr-9"),
        text_chunk_event("Hello"),
        text_chunk_event(" world"),
    ]
    service = _build_service(thread_repo=repo, runner=runner)

    events = await _drain(service, thread)

    # trace_id event is consumed internally, never forwarded.
    assert [e.type for e in events] == ["text_chunk", "text_chunk", "done"]
    assert [e.data["content"] for e in events[:2]] == ["Hello", " world"]
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
    runner.events = [artifact_created_event(artifact_id)]
    artifact_repo = FakeArtifactRepo()
    service = _build_service(
        thread_repo=repo, runner=runner, artifact_repo=artifact_repo
    )

    await _drain(service, thread)

    # Assert the resulting linkage state (the effect), not just that the spy
    # method fired: the streamed artifact is now bound to the resolved message.
    assert artifact_repo.linked == {artifact_id: "msg-1"}


@pytest.mark.parametrize(
    ("terminal_event", "terminal_type"),
    [
        (error_event("graph failed"), "error"),
        (security_block_event(), "security_block"),
        (cancelled_event(), "cancelled"),
    ],
)
async def test_send_message_terminal_event_skips_done(
    terminal_event: StreamEvent, terminal_type: str
) -> None:
    thread = _thread()
    repo = FakeThreadViewRepo()
    repo.add(thread)
    runner = FakeAgentRunner()
    runner.events = [text_chunk_event("partial"), terminal_event]
    service = _build_service(thread_repo=repo, runner=runner)

    events = await _drain(service, thread)

    # error/security_block/cancelled and done are mutually exclusive terminal
    # events. Partial text emitted before the terminal must survive unchanged,
    # and the terminal payload is forwarded verbatim (prod shape).
    assert [e.type for e in events] == ["text_chunk", terminal_type]
    assert events[0].data == {"content": "partial"}
    assert events[-1].data == terminal_event.data
    assert all(e.type != "done" for e in events)


async def test_send_message_saves_trace_id_to_store() -> None:
    thread = _thread()
    repo = FakeThreadViewRepo()
    repo.add(thread)
    runner = FakeAgentRunner()
    runner.last_ai_message_id = "m1"
    runner.events = [trace_id_event("tr-7")]
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
    runner.events = [text_chunk_event("ok")]
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


# --- event vocabulary contract --------------------------------------------
#
# The runner ↔ ChatService ↔ frontend triangle agrees on one closed set of wire
# event types. These tests pin that contract from both ends so a drift (runner
# starts emitting a type the service silently drops, or someone adds a wire type
# without teaching the frontend about it) fails loudly instead of green.


def _stream_event_type_literals(*modules: object) -> set[str]:
    """Collect every ``StreamEvent(type="literal", ...)`` string in the sources.

    AST-scans the given modules for ``StreamEvent(...)`` constructions and
    extracts the ``type`` argument when it is a string literal (positional or
    keyword). A new emission site with a fresh literal type widens this set and
    trips the contract tests below — forcing the vocabulary (and the frontend
    switch) to be updated deliberately. Both ends of the wire are scanned: the
    runner/mapper modules and ``ChatService`` itself, which synthesises event
    types of its own.
    """
    found: set[str] = set()
    for module in modules:
        source = Path(module.__file__).read_text(encoding="utf-8")  # type: ignore[attr-defined]
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "StreamEvent":
                continue
            type_arg: ast.expr | None = None
            for kw in node.keywords:
                if kw.arg == "type":
                    type_arg = kw.value
            if type_arg is None and node.args:
                type_arg = node.args[0]
            if isinstance(type_arg, ast.Constant) and isinstance(type_arg.value, str):
                found.add(type_arg.value)
    return found


def _custom_channel_type_literals(*modules: object) -> set[str]:
    """Collect every ``{"type": "literal", ...}`` envelope in the sources.

    The subagent's tool wrapper does not build ``StreamEvent``s — it writes wire
    envelopes straight into the stream writer, and the runner passes them
    through under whatever ``type`` they carry. That puts those literals on the
    wire just as directly as the runner's own, so they need the same guard:
    without it, a typo there produces a wire event no consumer knows, and
    nothing anywhere turns red.
    """
    found: set[str] = set()
    for module in modules:
        source = Path(module.__file__).read_text(encoding="utf-8")  # type: ignore[attr-defined]
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values, strict=True):
                if not (isinstance(key, ast.Constant) and key.value == "type"):
                    continue
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    found.add(value.value)
    return found


def test_subagent_wrapper_emits_only_the_agreed_wire_vocabulary() -> None:
    emitted = _custom_channel_type_literals(subagent_runner_module)

    # Non-empty: an empty result would mean the scan stopped seeing the
    # emission site and the guard silently guards nothing.
    assert emitted
    assert emitted <= RUNNER_FORWARDED_TYPES


def test_runner_emits_only_the_agreed_wire_vocabulary() -> None:
    # Both roads to the wire are scanned as one set. ``tool_result`` and
    # ``artifact_created`` are no longer built as ``StreamEvent``s at all: the
    # tools node writes them itself, per finished call, as custom-channel
    # envelopes in ``stream_events``. Scanning only the ``StreamEvent`` sites
    # would leave that half of the vocabulary unguarded while the assertion
    # below still looked exhaustive.
    emitted = _stream_event_type_literals(
        runner_module, stream_events_module, heartbeat_module
    ) | _custom_channel_type_literals(stream_events_module)

    # trace_id is emitted by the runner but consumed inside ChatService; every
    # other emitted type is forwarded to the wire. Nothing the runner emits may
    # fall outside the union the frontend (and ChatService) know how to handle.
    assert emitted == RUNNER_FORWARDED_TYPES | {"trace_id"}


def test_chat_service_emits_only_the_agreed_synthesised_wire_types() -> None:
    emitted = _stream_event_type_literals(chat_service_module)

    # ChatService is the second emitter on this wire: besides forwarding runner
    # events it puts the terminal ``done`` and the auto-title ``title_updated``
    # on the stream itself. Those never pass through the runner, so the guard
    # above cannot see them — without this one a new service-side event type
    # would reach the frontend union unannounced.
    assert emitted == SERVICE_SYNTHESISED_TYPES


def test_title_trigger_classifies_every_runner_event_type() -> None:
    # The auto-title trigger splits the runner's vocabulary in two: events that
    # prove the USER_INPUT guard cleared the input, and the rest — the prologue
    # (``stream_started``, ``heartbeat``, and ``cancelled``, which the pacer can
    # answer with from any point of the run, including before a verdict exists)
    # plus ``security_block``, the negative verdict itself. A type that belongs
    # to neither half is a type nobody classified: adding one to the wire and
    # forgetting this decision costs either a chat its generated name or, on the
    # side that matters, sends unchecked input to the title model. Only the
    # union is pinned, so the drift surfaces here rather than in production.
    cleared = chat_service_module._TITLE_GUARD_CLEARED_TYPES
    prologue_and_verdict = {
        "stream_started",
        "heartbeat",
        "cancelled",
        "security_block",
    }

    assert not cleared & prologue_and_verdict
    assert cleared | prologue_and_verdict == RUNNER_FORWARDED_TYPES


async def test_chat_service_forwards_each_runner_type_and_consumes_trace_id() -> None:
    thread = _thread()
    repo = FakeThreadViewRepo()
    repo.add(thread)
    runner = FakeAgentRunner()
    runner.last_ai_message_id = "m1"
    # One non-terminal event of every forwarded type, plus trace_id which must be
    # swallowed. Terminals (error/security_block/cancelled) are exercised
    # separately so we can reach the synthesised ``done`` here.
    runner.events = [
        trace_id_event("tr-1"),
        stream_started_event(),
        heartbeat_event(),
        reasoning_chunk_event("thinking..."),
        text_chunk_event("hi"),
        tool_call_started_event("c1", "search"),
        tool_call_args_event("c1", '{"query": "hi"}'),
        tool_call_cancelled_event("c2"),
        tool_result_event("c1", "search", content="ok"),
        agent_event_event("sphere_write", {"section_id": "s1"}),
        artifact_created_event(uuid.uuid4()),
        StreamEvent(type="final_output_review_started", data={}),
        StreamEvent(type="final_output_review_complete", data={}),
    ]
    service = _build_service(thread_repo=repo, runner=runner)

    events = await _drain(service, thread)
    forwarded = [e.type for e in events]

    # trace_id consumed; all other types forwarded in order; done synthesised.
    assert "trace_id" not in forwarded
    assert forwarded == [
        "stream_started",
        "heartbeat",
        "reasoning_chunk",
        "text_chunk",
        "tool_call_started",
        "tool_call_args",
        "tool_call_cancelled",
        "tool_result",
        "agent_event",
        "artifact_created",
        "final_output_review_started",
        "final_output_review_complete",
        "done",
    ]
    assert set(forwarded) - {"done"} == RUNNER_FORWARDED_TYPES - {
        "error",
        "security_block",
        "cancelled",
    }
