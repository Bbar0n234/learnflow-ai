"""Unit: ``HeartbeatPacer`` — silence heartbeats + responsive cancellation.

The pacer wraps an arbitrary ``StreamEvent`` source and owns two guarantees of
the SSE contract (streaming.md § «Лимиты», § «Cancellation»): the client never
sits in unexplained silence, because a ``heartbeat`` goes out on every interval
the source produced nothing; and a cancellation is noticed on that same timer,
so a run blocked deep inside a tool call still terminates with ``cancelled``
instead of hanging until the tool returns.

Determinism without sleeping on wall-clock: the source blocks on an
``asyncio.Event`` the test controls, so "the source produced nothing this
interval" is a fact of the test, not a race. The interval is set to a few
milliseconds — the timer has to expire, but nothing depends on *how many*
times it does before the test releases the source.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator

import pytest
from app.agent.heartbeat import HEARTBEAT_INTERVAL_SECONDS, HeartbeatPacer
from app.services.agent_runner import StreamEvent

pytestmark = pytest.mark.unit

INTERVAL = 0.01


def _text(content: str) -> StreamEvent:
    return StreamEvent(type="text_chunk", data={"content": content})


class _SourceState:
    """Observable lifecycle of the wrapped source: closed / fully drained."""

    def __init__(self) -> None:
        self.closed = False
        self.drained = False


def _blocking_source(
    release: asyncio.Event, state: _SourceState
) -> AsyncGenerator[StreamEvent, None]:
    """Yields one event, but only once the test releases it."""

    async def _gen() -> AsyncGenerator[StreamEvent, None]:
        try:
            await release.wait()
            yield _text("late")
            state.drained = True
        finally:
            state.closed = True

    return _gen()


def _prompt_source(count: int) -> AsyncGenerator[StreamEvent, None]:
    async def _gen() -> AsyncGenerator[StreamEvent, None]:
        for i in range(count):
            yield _text(str(i))

    return _gen()


def test_default_interval_is_the_documented_five_seconds() -> None:
    # streaming.md § «Лимиты»: 5 s of silence, and the client's own timeout is
    # derived from it (3 missed heartbeats) — a business invariant, not env.
    assert HEARTBEAT_INTERVAL_SECONDS == 5.0


async def test_silence_emits_heartbeats_until_the_source_produces() -> None:
    release = asyncio.Event()
    state = _SourceState()
    paced = HeartbeatPacer(interval=INTERVAL).pace(
        _blocking_source(release, state), asyncio.Event()
    )

    first = await anext(paced)
    assert first == StreamEvent(type="heartbeat", data={})

    release.set()
    following = [event async for event in paced]

    assert _text("late") in following
    assert all(e.type in {"heartbeat", "text_chunk"} for e in following)
    assert state.drained is True


async def test_a_source_that_keeps_producing_never_yields_a_heartbeat() -> None:
    # A full-speed stream must stay clean: heartbeats are a silence filler, not
    # a periodic keep-alive interleaved into real events.
    paced = HeartbeatPacer(interval=HEARTBEAT_INTERVAL_SECONDS).pace(
        _prompt_source(3), asyncio.Event()
    )

    events = [event async for event in paced]

    assert [e.data["content"] for e in events] == ["0", "1", "2"]


async def test_cancel_during_a_blocked_source_terminates_the_stream() -> None:
    # The blocked source stands in for a long tool call: the pacer must notice
    # the cancellation on its own timer, emit the terminal ``cancelled`` and
    # stop pulling — never wait for the tool to finish.
    release = asyncio.Event()
    state = _SourceState()
    cancel_event = asyncio.Event()
    paced = HeartbeatPacer(interval=INTERVAL).pace(
        _blocking_source(release, state), cancel_event
    )

    assert (await anext(paced)).type == "heartbeat"
    cancel_event.set()
    events = [event async for event in paced]

    assert events[-1] == StreamEvent(type="cancelled", data={})
    assert all(e.type in {"heartbeat", "cancelled"} for e in events)
    assert state.drained is False
    assert state.closed is True


async def test_source_exhaustion_ends_the_paced_stream() -> None:
    paced = HeartbeatPacer(interval=INTERVAL).pace(_prompt_source(1), asyncio.Event())

    events = [event async for event in paced]

    assert [e.type for e in events] == ["text_chunk"]


async def test_source_failure_is_not_swallowed() -> None:
    # The runner's own error handling (mapping an exception to a terminal
    # ``error`` event) sits *inside* the source; anything escaping it must keep
    # escaping, not be muted into a silent end-of-stream.
    async def _failing() -> AsyncGenerator[StreamEvent, None]:
        yield _text("partial")
        raise RuntimeError("graph exploded")

    paced = HeartbeatPacer(interval=INTERVAL).pace(_failing(), asyncio.Event())

    assert (await anext(paced)).type == "text_chunk"
    with pytest.raises(RuntimeError, match="graph exploded"):
        await anext(paced)


async def test_consumer_closing_early_closes_the_source() -> None:
    # A client disconnect closes the paced generator; the wrapped run must be
    # torn down with it rather than left pulling in the background.
    release = asyncio.Event()
    state = _SourceState()
    paced = HeartbeatPacer(interval=INTERVAL).pace(
        _blocking_source(release, state), asyncio.Event()
    )

    assert (await anext(paced)).type == "heartbeat"
    await paced.aclose()

    assert state.closed is True
