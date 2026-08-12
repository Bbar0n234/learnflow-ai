"""Sociable-unit tests for the auto-title half of ``ChatService.send_message``.

Two behaviours live here, both invisible from the outside except through the
event stream:

* **when generation is started** — only for a chat whose title is still the
  placeholder, only once per run, and only after the security guard has let the
  first agent event through (a run whose first event is ``security_block`` never
  sends the user's text to the title model);
* **when the finished title is delivered** — as a single non-terminal
  ``title_updated`` event slipped between two agent events, never replacing the
  terminal ``done`` / ``error`` / ``security_block``.

Collaborators are the scope's in-memory fakes; the title generator stand-in
returns a resolvable handle so "the title is ready at this exact point of the
stream" is deterministic (see ``FakeTitleGenerator`` in conftest).
"""

from __future__ import annotations

import uuid

import pytest
from app.models.thread_view import ThreadView
from app.services.agent_runner import StreamEvent
from app.services.chat import ChatService
from app.services.constants import DEFAULT_CHAT_TITLE

from tests.chat.conftest import (
    FakeAgentRunner,
    FakeThreadViewRepo,
    FakeTitleGenerator,
    cancelled_event,
    error_event,
    heartbeat_event,
    security_block_event,
    stream_started_event,
    text_chunk_event,
    tool_call_started_event,
    trace_id_event,
)

pytestmark = pytest.mark.unit

_USER_TEXT = "Объясни, что такое дискриминант"


def _thread(*, title: str = DEFAULT_CHAT_TITLE) -> ThreadView:
    return ThreadView(
        thread_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        title=title,
    )


def _build_service(
    *,
    thread_repo: FakeThreadViewRepo,
    runner: FakeAgentRunner,
    title_generator: FakeTitleGenerator | None,
) -> ChatService:
    return ChatService(
        thread_view_repo=thread_repo,  # type: ignore[arg-type]
        agent_runner=runner,  # AgentRunner is a Protocol — FakeAgentRunner fits
        trace_store=None,
        session=None,
        title_generator=title_generator,  # type: ignore[arg-type]
    )


async def _run(
    thread: ThreadView,
    events: list[StreamEvent],
    *,
    title_generator: FakeTitleGenerator | None,
    resolve_title_before_event: int | None = None,
    cancel_title_before_event: int | None = None,
) -> list[StreamEvent]:
    repo = FakeThreadViewRepo()
    repo.add(thread)
    runner = FakeAgentRunner()
    runner.events = events
    runner.last_ai_message_id = "m1"
    settle_before_event = (
        resolve_title_before_event
        if resolve_title_before_event is not None
        else cancel_title_before_event
    )
    if settle_before_event is not None:
        assert title_generator is not None
        settle = (
            title_generator.resolve
            if resolve_title_before_event is not None
            else title_generator.cancel
        )

        def _settle_generation(index: int) -> None:
            # The generation ends — with a title or with a cancellation — in the
            # gap between the poll that followed the previous event and the
            # delivery of event ``index``.
            if index == settle_before_event:
                settle()

        runner.on_event = _settle_generation
    service = _build_service(
        thread_repo=repo, runner=runner, title_generator=title_generator
    )
    return [
        event
        async for event in service.send_message(
            thread_id=thread.thread_id,
            project_id=thread.project_id,
            user_id=uuid.uuid4(),
            content=_USER_TEXT,
        )
    ]


# --- when generation is started -------------------------------------------


async def test_send_message_starts_generation_for_placeholder_title() -> None:
    thread = _thread()
    generator = FakeTitleGenerator()

    await _run(thread, [text_chunk_event("Привет")], title_generator=generator)

    # The generator is handed the chat and the text the title is derived from.
    assert generator.calls == [(thread.thread_id, _USER_TEXT)]


@pytest.mark.parametrize(
    ("first_event", "expected_types"),
    [
        (
            tool_call_started_event("c1", "search"),
            ["tool_call_started", "title_updated", "done"],
        ),
        (error_event("graph failed"), ["error"]),
    ],
    ids=["tool_first_run", "run_failed_immediately"],
)
async def test_send_message_starts_generation_on_any_non_block_first_event(
    first_event: StreamEvent, expected_types: list[str]
) -> None:
    generator = FakeTitleGenerator()

    events = await _run(_thread(), [first_event], title_generator=generator)

    # The gate is the security guard, not "the agent produced text": a tool-first
    # run (no text for minutes) and a run that fails right away both had their
    # input cleared by the guard already, so the title is still generated.
    assert len(generator.calls) == 1
    # The generation is started either way, but its *delivery* still obeys the
    # terminal contract: on the failing run the title is already available when
    # the error is yielded, and it must still not appear behind it.
    assert [e.type for e in events] == expected_types


async def test_send_message_skips_generation_when_user_already_named_the_chat() -> None:
    generator = FakeTitleGenerator()

    await _run(
        _thread(title="Подготовка к ЕГЭ"),
        [text_chunk_event("Привет")],
        title_generator=generator,
    )

    # Trigger is "title is still the placeholder" — a named chat is never
    # re-titled behind the user's back.
    assert generator.calls == []


@pytest.mark.parametrize(
    "events",
    [
        [security_block_event()],
        [trace_id_event("tr-1"), security_block_event()],
        [stream_started_event(), security_block_event()],
        [
            stream_started_event(),
            heartbeat_event(),
            heartbeat_event(),
            security_block_event(),
        ],
    ],
    ids=[
        "block_first",
        "block_after_consumed_trace_id",
        "block_after_stream_started",
        "block_after_stream_started_and_heartbeats",
    ],
)
async def test_send_message_skips_generation_when_guard_blocks_first_event(
    events: list[StreamEvent],
) -> None:
    generator = FakeTitleGenerator()

    await _run(_thread(), events, title_generator=generator)

    # Blocked input must not reach the title model (that call carries no guard
    # wrapper) and must not surface as a generated name in the sidebar. The
    # internally consumed trace_id event must not be mistaken for "the guard let
    # something through" — nor may the SSE v2 prologue (``stream_started`` is
    # unconditionally first, ``heartbeat`` fills the silence while the guard is
    # still running), which is why the trigger waits for an event in
    # ``_TITLE_GUARD_CLEARED_TYPES`` instead of reading the literal first event.
    assert generator.calls == []


@pytest.mark.parametrize(
    "events",
    [
        [cancelled_event()],
        [stream_started_event(), cancelled_event()],
        [stream_started_event(), heartbeat_event(), cancelled_event()],
    ],
    ids=["cancel_first", "cancel_after_stream_started", "cancel_after_heartbeat"],
)
async def test_send_message_skips_generation_when_cancelled_before_the_verdict(
    events: list[StreamEvent],
) -> None:
    # ``cancelled`` belongs to the prologue just as much as ``heartbeat`` does:
    # the pacer checks the cancel flag on its own timer and answers from any
    # point of the run (agent/heartbeat.py), while the USER_INPUT guard is only
    # reached after model resolution, tool resolution and graph assembly
    # (agent/runner.py) — i.e. never before the first tick. Hitting stop while
    # the classifier is still thinking must not send that unchecked text to the
    # title model.
    generator = FakeTitleGenerator()

    await _run(_thread(), events, title_generator=generator)

    assert generator.calls == []


async def test_send_message_keeps_generation_when_cancelled_after_the_verdict() -> None:
    # The mirror case, so the fix above cannot be satisfied by never generating
    # on a cancelled run: once an event proves the guard cleared the input, a
    # later cancellation does not retract the generation.
    generator = FakeTitleGenerator()

    await _run(
        _thread(),
        [stream_started_event(), text_chunk_event("Привет"), cancelled_event()],
        title_generator=generator,
    )

    assert len(generator.calls) == 1


async def test_send_message_keeps_generation_when_block_arrives_later() -> None:
    generator = FakeTitleGenerator()

    events = await _run(
        _thread(),
        [text_chunk_event("Привет"), security_block_event()],
        title_generator=generator,
    )

    # A block *after* the guard already passed the input does not retract the
    # generation: the title comes from text the guard cleared.
    assert len(generator.calls) == 1
    assert events[-1].type == "security_block"


async def test_send_message_starts_generation_at_most_once_per_run() -> None:
    generator = FakeTitleGenerator(mode="pending")

    await _run(
        _thread(),
        [text_chunk_event("а"), text_chunk_event("б"), text_chunk_event("в")],
        title_generator=generator,
    )

    assert len(generator.calls) == 1


# --- when the finished title is delivered ---------------------------------


async def test_send_message_emits_title_updated_between_agent_events() -> None:
    generator = FakeTitleGenerator(title="Квадратные уравнения")

    events = await _run(
        _thread(),
        [text_chunk_event("Привет"), text_chunk_event(", мир")],
        title_generator=generator,
    )

    # Non-terminal: the ready title is slipped in after the event that triggered
    # generation, the agent's own events keep flowing, and the run still ends
    # with the synthesised done.
    assert [e.type for e in events] == [
        "text_chunk",
        "title_updated",
        "text_chunk",
        "done",
    ]
    assert events[1].data == {"title": "Квадратные уравнения"}


async def test_send_message_emits_title_updated_only_once_per_run() -> None:
    generator = FakeTitleGenerator(title="Квадратные уравнения")

    events = await _run(
        _thread(),
        [text_chunk_event("а"), text_chunk_event("б"), text_chunk_event("в")],
        title_generator=generator,
    )

    assert [e.type for e in events].count("title_updated") == 1


async def test_send_message_delivers_title_before_terminal_block() -> None:
    generator = FakeTitleGenerator(title="Квадратные уравнения")

    events = await _run(
        _thread(),
        [text_chunk_event("Привет"), security_block_event()],
        title_generator=generator,
    )

    # A terminal event still terminates: title_updated may precede it, but no
    # done is synthesised after a block.
    assert [e.type for e in events] == ["text_chunk", "title_updated", "security_block"]


@pytest.mark.parametrize(
    ("second_event", "expected_types"),
    [
        (
            text_chunk_event(", мир"),
            ["text_chunk", "text_chunk", "title_updated", "done"],
        ),
        (error_event("graph failed"), ["text_chunk", "error"]),
        (security_block_event(), ["text_chunk", "security_block"]),
    ],
    ids=["next_event_is_not_terminal", "next_event_is_error", "next_event_is_block"],
)
async def test_send_message_delivers_a_last_moment_title_only_before_a_non_terminal(
    second_event: StreamEvent, expected_types: list[str]
) -> None:
    generator = FakeTitleGenerator(mode="deferred")

    events = await _run(
        _thread(),
        [text_chunk_event("Привет"), second_event],
        title_generator=generator,
        resolve_title_before_event=1,
    )

    # The generation finishes in the narrowest window there is: after the first
    # event was already polled, before the second one is delivered. If the
    # second event is ordinary the title rides right behind it; if it is
    # terminal the stream is closed and nothing may follow it (streaming.md
    # § Protocol Overview) — the title is dropped from the wire and reaches the
    # client through the refetch fallback instead (design-brief § Доставка
    # title). Same fake, same timing: the only difference is the event type.
    assert [e.type for e in events] == expected_types


@pytest.mark.parametrize(
    ("mode", "title"),
    [
        ("pending", "Квадратные уравнения"),
        ("ready", None),
        ("in_flight", "Квадратные уравнения"),
    ],
    ids=["still_running", "generation_gave_up", "already_in_flight"],
)
async def test_send_message_emits_no_title_updated_without_a_ready_title(
    mode: str, title: str | None
) -> None:
    events = await _run(
        _thread(),
        [text_chunk_event("Привет")],
        title_generator=FakeTitleGenerator(mode=mode, title=title),
    )

    # No title yet (slow run), a generation that degraded to None, or a
    # generation already in flight from an earlier message — in all three the
    # stream is exactly what it would be without the auto-title feature.
    assert [e.type for e in events] == ["text_chunk", "done"]


async def test_send_message_survives_a_generation_cancelled_mid_stream() -> None:
    generator = FakeTitleGenerator(mode="deferred")

    events = await _run(
        _thread(),
        [text_chunk_event("Привет"), text_chunk_event(", мир")],
        title_generator=generator,
        cancel_title_before_event=1,
    )

    # Application shutdown cancels every in-flight generation, and a stream that
    # is still open finds its handle finished — carrying a CancelledError, not a
    # title. That is the same outcome as "the generation did not make it": the
    # answer keeps streaming to the user and ends normally, instead of the
    # cancellation tearing the SSE response apart.
    assert [e.type for e in events] == ["text_chunk", "text_chunk", "done"]


async def test_send_message_emits_no_title_updated_without_a_generator() -> None:
    events = await _run(_thread(), [text_chunk_event("Привет")], title_generator=None)

    # ASGI tests and any deployment without the lifespan-built generator fall
    # back to the pre-auto-title behaviour instead of crashing.
    assert [e.type for e in events] == ["text_chunk", "done"]
