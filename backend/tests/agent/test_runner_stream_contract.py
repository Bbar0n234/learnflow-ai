"""Sociable unit: ``LangGraphAgentRunner.stream`` — the SSE v2 wire contract.

Here the runner is driven by a *scripted* graph: a fake whose ``astream``
replays a chosen ``(mode, data)`` sequence over the three channels the contract
is built on — ``messages``, ``updates``, ``custom``. Everything else around the
runner is real (``RuntimeSecurityEnforcer`` with the guard off, a real
``CheckpointHistory`` over ``InMemorySaver``, a disabled tracer), so what these
cases assert is the runner's own translation and lifecycle work, without an LLM
in the loop deciding what the channels contain.

That is the seam where the contract's trickier promises live: a domain
``agent_event`` is wrapped while a subagent's lifecycle event is passed through
untouched, a tool call announced by the token channel and then cut by the guard
is reported as cancelled, reasoning never feeds the output guard, and a
cancellation is answered with the terminal ``cancelled`` even while the graph
sits inside one long iteration. Runs through the *real* graph (a real tool
emitting a real ``agent_event``) live in ``test_runner.py``.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
from app.agent.checkpoint_history import CheckpointHistory
from app.agent.config import ResolvedModelConfig, load_error_messages
from app.agent.heartbeat import HeartbeatPacer
from app.agent.runner import LangGraphAgentRunner
from app.agent.runtime_security import RuntimeSecurityEnforcer, SecurityOutcome
from app.agent.security.types import (
    Checkpoint,
    DetectionLayer,
    Direction,
    GuardResult,
    SecurityMessages,
    Verdict,
)
from app.agent.tracing import AgentRunTracer
from app.services.agent_runner import StreamEvent
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.messages.tool import tool_call_chunk
from langgraph.checkpoint.memory import InMemorySaver

pytestmark = pytest.mark.unit

PACER_INTERVAL = 0.01


class _ScriptedGraph:
    """Replays a chosen ``(mode, data)`` sequence, optionally then blocking.

    ``block`` models a graph stuck inside a single iteration — a long tool call
    or a subagent run — which is exactly the situation the heartbeat timer, not
    the astream loop, is responsible for. ``then`` gives the *second* run of the
    same runner its own script, so two consecutive turns can be told apart.
    """

    def __init__(
        self,
        events: list[tuple[str, Any]],
        *,
        block: asyncio.Event | None = None,
        then: list[tuple[str, Any]] | None = None,
    ) -> None:
        self._scripts = [events] if then is None else [events, then]
        self._runs = 0
        self._block = block

    async def astream(
        self,
        _input: Any,
        _config: Any = None,
        *,
        stream_mode: Any = None,
        context: Any = None,
    ) -> AsyncGenerator[tuple[str, Any], None]:
        script = self._scripts[min(self._runs, len(self._scripts) - 1)]
        self._runs += 1
        for event in script:
            yield event
        if self._block is not None:
            await self._block.wait()


class _FakeFactory:
    """Graph factory returning the scripted graph; counts setup invocations."""

    def __init__(self, graph: _ScriptedGraph) -> None:
        self._graph = graph
        self.build_calls = 0

    def build(self, _model_config: Any, *, extra_tools: Any = None) -> _ScriptedGraph:
        self.build_calls += 1
        return self._graph


class _DummyResolver:
    """Unused: ``model_config`` is passed to ``stream``, so ``resolve`` is skipped."""


class _StagedEnforcer:
    """Stub enforcer flagging INJECTION at a chosen runtime checkpoint.

    ``user_input_blocks`` counts down, so a runner can be made to block the
    first run and pass the next one — the two-run setup the cleanup cases need.
    """

    def __init__(self, *, user_input_blocks: int = 0, mid: bool = False) -> None:
        self._user_input_blocks = user_input_blocks
        self._mid = mid

    async def check_user_input(self, **_kwargs: Any) -> GuardResult | None:
        if self._user_input_blocks <= 0:
            return None
        self._user_input_blocks -= 1
        return GuardResult(
            verdict=Verdict.INJECTION,
            checkpoint=Checkpoint.USER_INPUT,
            direction=Direction.INBOUND,
            detection_layer=None,
        )

    async def check_mid_stream(self, **_kwargs: Any) -> SecurityOutcome | None:
        if not self._mid:
            return None
        return SecurityOutcome(
            reason="unicode",
            result=GuardResult(
                verdict=Verdict.INJECTION,
                checkpoint=Checkpoint.FINAL_OUTPUT,
                direction=Direction.OUTBOUND,
                detection_layer=DetectionLayer.UNICODE,
            ),
        )

    async def check_final_output(self, **_kwargs: Any) -> SecurityOutcome | None:
        return None

    async def inspect_in_graph(self, **_kwargs: Any) -> SecurityOutcome | None:
        return None


def _make_runner(
    factory: _FakeFactory,
    *,
    enforcer: Any | None = None,
) -> LangGraphAgentRunner:
    security_messages = SecurityMessages()
    history = CheckpointHistory(InMemorySaver(), security_messages)
    return LangGraphAgentRunner(
        factory,  # type: ignore[arg-type]
        _DummyResolver(),  # type: ignore[arg-type]
        AgentRunTracer(enabled=False, security_messages=security_messages),
        enforcer
        or RuntimeSecurityEnforcer(
            guard=None, security_messages=security_messages, history=history
        ),
        history,
        load_error_messages(),
        heartbeat_pacer=HeartbeatPacer(interval=PACER_INTERVAL),
    )


def _runner_for(
    events: list[tuple[str, Any]],
    *,
    enforcer: Any | None = None,
) -> LangGraphAgentRunner:
    return _make_runner(_FakeFactory(_ScriptedGraph(events)), enforcer=enforcer)


def _stream(
    runner: LangGraphAgentRunner, thread_id: uuid.UUID | None = None
) -> AsyncGenerator[StreamEvent, None]:
    return cast(
        AsyncGenerator[StreamEvent, None],
        runner.stream(
            thread_id=thread_id or uuid.uuid4(),
            content="hi",
            project_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            model_config=ResolvedModelConfig(
                model="fake", extra_body=None, source="config"
            ),
        ),
    )


async def _collect(
    runner: LangGraphAgentRunner, thread_id: uuid.UUID | None = None
) -> list[StreamEvent]:
    return [event async for event in _stream(runner, thread_id)]


def _text_chunk(content: str) -> tuple[str, Any]:
    return ("messages", (AIMessageChunk(content=content, id="m1"), {}))


def _reasoning_chunk(content: str) -> tuple[str, Any]:
    return (
        "messages",
        (
            AIMessageChunk(
                content="", id="m1", additional_kwargs={"reasoning": content}
            ),
            {},
        ),
    )


def _tool_call_chunk(call_id: str, tool: str, args: str) -> tuple[str, Any]:
    return (
        "messages",
        (
            AIMessageChunk(
                content="",
                id="m1",
                tool_call_chunks=[
                    tool_call_chunk(name=tool, args=args, id=call_id, index=0)
                ],
            ),
            {},
        ),
    )


# --- stream lifecycle --------------------------------------------------------


async def test_stream_started_is_the_first_event_and_precedes_setup() -> None:
    # "Молчаливого UX не существует": the first thing on the wire is the stream
    # opening, and it goes out before the model/MCP/graph setup that can take
    # seconds — so it cannot be a by-product of that setup finishing.
    factory = _FakeFactory(_ScriptedGraph([_text_chunk("hi")]))
    stream = _stream(_make_runner(factory))

    first = await anext(stream)

    assert first == StreamEvent(type="stream_started", data={})
    assert factory.build_calls == 0
    await stream.aclose()


# --- custom channel ----------------------------------------------------------


async def test_domain_write_becomes_an_agent_event() -> None:
    runner = _runner_for(
        [("custom", {"type": "sphere_write", "payload": {"section_id": "s1"}})]
    )

    events = await _collect(runner)

    agent_events = [e for e in events if e.type == "agent_event"]
    assert [e.data for e in agent_events] == [
        {"kind": "sphere_write", "payload": {"section_id": "s1"}}
    ]


async def test_domain_write_from_a_subagent_keeps_its_parent_call_id() -> None:
    runner = _runner_for(
        [
            (
                "custom",
                {
                    "type": "memory_write",
                    "payload": {"key": "k"},
                    "parent_call_id": "outer-1",
                },
            )
        ]
    )

    events = await _collect(runner)

    agent_event = next(e for e in events if e.type == "agent_event")
    assert agent_event.data == {
        "kind": "memory_write",
        "payload": {"key": "k"},
        "parent_call_id": "outer-1",
    }


async def test_subagent_lifecycle_events_pass_through_as_their_own_types() -> None:
    # On the wire a subagent's step is indistinguishable from the main agent's
    # own, except for ``parent_call_id`` — so these must never be wrapped into
    # ``agent_event`` (streaming.md § «Вложенность субагента»).
    payload = {
        "call_id": "inner-1",
        "tool": "firecrawl_search",
        "parent_call_id": "outer-1",
    }
    runner = _runner_for([("custom", {"type": "tool_call_started", "data": payload})])

    events = await _collect(runner)

    started = [e for e in events if e.type == "tool_call_started"]
    assert [e.data for e in started] == [payload]


async def test_a_custom_payload_without_a_type_is_ignored() -> None:
    runner = _runner_for([("custom", {"payload": {"noise": 1}}), _text_chunk("ok")])

    events = await _collect(runner)

    types = [e.type for e in events]
    assert "agent_event" not in types
    assert "text_chunk" in types


# --- token channel meets updates channel -------------------------------------


async def test_a_call_cut_by_the_guard_is_reported_as_cancelled() -> None:
    # The announcement lives in the token channel and the cut surfaces in the
    # updates channel: only the runner sees both, so this is where the two are
    # wired together. Without it the feed keeps a row spinning forever.
    runner = _runner_for(
        [
            _tool_call_chunk("c1", "firecrawl_search", '{"query": "x"}'),
            (
                "updates",
                {
                    "agent": {
                        "messages": [
                            AIMessage(
                                content="",
                                additional_kwargs={"security_redacted": True},
                            )
                        ]
                    }
                },
            ),
        ]
    )

    events = await _collect(runner)

    types = [e.type for e in events]
    assert "tool_call_started" in types
    assert "tool_call_args" in types
    cancelled = [e for e in events if e.type == "tool_call_cancelled"]
    assert [e.data for e in cancelled] == [{"call_id": "c1"}]
    assert types.index("tool_call_started") < types.index("tool_call_cancelled")


# --- one run's tool-call bookkeeping never reaches the next ------------------


async def test_a_later_run_announces_a_repeated_call_id_again() -> None:
    # Tool-call assembly state belongs to one run. A shared mapper would treat
    # the second turn's ``c1`` as already announced and swallow the row — and
    # since provider ids repeat across concurrent users' streams, that is one
    # user's action silently missing from another user's feed.
    runner = _make_runner(
        _FakeFactory(_ScriptedGraph([_tool_call_chunk("c1", "echo", "{}")]))
    )

    first = await _collect(runner)
    second = await _collect(runner)

    assert [e.type for e in first if e.type.startswith("tool_call")] == [
        "tool_call_started",
        "tool_call_args",
    ]
    assert [e.type for e in second if e.type.startswith("tool_call")] == [
        "tool_call_started",
        "tool_call_args",
    ]


async def test_a_guard_cut_does_not_cancel_a_previous_runs_call() -> None:
    # The mirror image on the updates side: a call left unresolved by an earlier
    # turn must not be reported as cancelled when a *later* turn gets cut. With
    # shared bookkeeping the second stream would carry a phantom row id its
    # client never saw announced.
    runner = _make_runner(
        _FakeFactory(
            _ScriptedGraph(
                [_tool_call_chunk("c1", "echo", "{}")],
                then=[
                    (
                        "updates",
                        {
                            "agent": {
                                "messages": [
                                    AIMessage(
                                        content="",
                                        additional_kwargs={"security_redacted": True},
                                    )
                                ]
                            }
                        },
                    )
                ],
            )
        )
    )

    await _collect(runner)
    second = await _collect(runner)

    assert [e.type for e in second if e.type == "tool_call_cancelled"] == []


# --- reasoning is streamed, never guarded ------------------------------------


async def test_reasoning_only_turn_streams_reasoning_and_skips_the_review() -> None:
    # The end-of-stream review runs on the *answer*; a turn that produced only
    # reasoning has no answer to review (streaming.md § «final_output_review_*»).
    runner = _runner_for([_reasoning_chunk("weighing the options")])

    events = await _collect(runner)

    reasoning = [e for e in events if e.type == "reasoning_chunk"]
    assert [e.data["content"] for e in reasoning] == ["weighing the options"]
    assert "final_output_review_started" not in [e.type for e in events]


async def test_reasoning_does_not_reach_the_output_guard() -> None:
    # Conscious boundary of the design brief: reasoning streams live without
    # guard involvement, so an enforcer that blocks everything it is shown must
    # never be shown a reasoning chunk.
    runner = _runner_for(
        [_reasoning_chunk("some thought")], enforcer=_StagedEnforcer(mid=True)
    )

    events = await _collect(runner)

    types = [e.type for e in events]
    assert "reasoning_chunk" in types
    assert "security_block" not in types


async def test_text_still_reaches_the_output_guard() -> None:
    # The counterpart of the case above — the guard must stay wired to text,
    # otherwise the previous case would pass for the wrong reason.
    runner = _runner_for(
        [_text_chunk("leaked secret")], enforcer=_StagedEnforcer(mid=True)
    )

    events = await _collect(runner)

    types = [e.type for e in events]
    assert "security_block" in types
    assert "text_chunk" not in types


# --- cancellation ------------------------------------------------------------


async def test_cancel_while_the_graph_is_blocked_ends_the_stream() -> None:
    # The graph is stuck inside one iteration (long tool call / subagent run):
    # the astream loop cannot notice anything, so the heartbeat timer has to —
    # otherwise cancelling during a slow tool would do nothing until it returns.
    blocked = asyncio.Event()
    thread_id = uuid.uuid4()
    runner = _make_runner(
        _FakeFactory(_ScriptedGraph([_text_chunk("working")], block=blocked))
    )
    stream = _stream(runner, thread_id)
    try:
        assert (await anext(stream)).type == "stream_started"
        assert (await anext(stream)).type == "text_chunk"

        await runner.cancel(thread_id=thread_id)
        tail = [event async for event in stream]
    finally:
        blocked.set()

    assert tail[-1] == StreamEvent(type="cancelled", data={})
    assert "error" not in [e.type for e in tail]


async def test_cancel_between_graph_iterations_ends_the_stream() -> None:
    thread_id = uuid.uuid4()
    runner = _runner_for([_text_chunk("one"), _text_chunk("two")])
    stream = _stream(runner, thread_id)

    assert (await anext(stream)).type == "stream_started"
    assert (await anext(stream)).data["content"] == "one"
    await runner.cancel(thread_id=thread_id)
    tail = [event async for event in stream]

    assert [e.type for e in tail] == ["cancelled"]


async def test_a_completed_run_leaves_no_cancellation_state_behind() -> None:
    # Cancellation state is per-run: after a run ends, cancelling that thread
    # again must arm the *next* run. A leaked event from the finished run would
    # swallow the cancel and let the second run stream on unstoppable.
    thread_id = uuid.uuid4()
    runner = _runner_for([_text_chunk("first")])
    await _collect(runner, thread_id)

    await runner.cancel(thread_id=thread_id)
    second = await _collect(runner, thread_id)

    assert "cancelled" in [e.type for e in second]


async def test_a_run_blocked_before_the_graph_leaves_no_state_behind() -> None:
    # Same guarantee on the early-return path: the pre-graph USER_INPUT block
    # returns out of the middle of the run, and the cleanup must still happen.
    thread_id = uuid.uuid4()
    runner = _runner_for(
        [_text_chunk("second run")], enforcer=_StagedEnforcer(user_input_blocks=1)
    )
    blocked_run = await _collect(runner, thread_id)
    assert "security_block" in [e.type for e in blocked_run]

    await runner.cancel(thread_id=thread_id)
    second = await _collect(runner, thread_id)

    assert "cancelled" in [e.type for e in second]
