"""Unit: ``TokenChunkMapper`` — one messages-channel chunk -> token-channel events.

Pure translation over raw ``AIMessageChunk``s, no collaborators: the mapper is
the only place that knows how a provider's token stream turns into the SSE
contract's ``reasoning_chunk`` / ``text_chunk`` / ``tool_call_started`` /
``tool_call_args`` (streaming.md § «Состав событий», § «Уточнения по отдельным
событиям»).

The contract these cases hold the mapper to: a tool call is announced on its
*first* fragment (name and id are known there, long before the arguments are
finished), the arguments are announced exactly once — at the moment the
accumulated string first parses as JSON, i.e. the call is fully generated but
not yet executed — and both are attributed to the right call when several calls
stream in parallel or a fragment carries only an ``index``. Oversized arguments
follow the single project-wide truncation limit.
"""

from __future__ import annotations

import json

import pytest
from app.agent.stream_events import TokenChunkMapper
from app.agent.text_limits import TRUNCATION_LIMIT
from app.services.agent_runner import StreamEvent
from langchain_core.messages import AIMessageChunk
from langchain_core.messages.tool import ToolCallChunk, tool_call_chunk

pytestmark = pytest.mark.unit


@pytest.fixture
def mapper() -> TokenChunkMapper:
    return TokenChunkMapper()


def _fragment(
    *,
    name: str | None = None,
    args: str | None = None,
    id: str | None = None,
    index: int | None = None,
) -> ToolCallChunk:
    """One ``tool_call_chunks`` entry as a provider streams it."""
    return tool_call_chunk(name=name, args=args, id=id, index=index)


def _chunk(
    *,
    content: str = "",
    reasoning: str | None = None,
    tool_calls: list[ToolCallChunk] | None = None,
) -> AIMessageChunk:
    """A raw provider chunk: text, a reasoning delta, tool-call fragments."""
    additional_kwargs: dict[str, object] = {}
    if reasoning is not None:
        additional_kwargs["reasoning"] = reasoning
    return AIMessageChunk(
        content=content,
        additional_kwargs=additional_kwargs,
        tool_call_chunks=tool_calls or [],
    )


def _typed(events: list[StreamEvent]) -> list[tuple[str, dict[str, object]]]:
    return [(e.type, e.data) for e in events]


# --- text and reasoning -----------------------------------------------------


def test_text_content_maps_to_text_chunk(mapper: TokenChunkMapper) -> None:
    events = mapper.map_chunk(_chunk(content="Hello"))

    assert _typed(events) == [("text_chunk", {"content": "Hello"})]


def test_reasoning_delta_maps_to_reasoning_chunk(mapper: TokenChunkMapper) -> None:
    events = mapper.map_chunk(_chunk(reasoning="I should check the docs"))

    assert _typed(events) == [
        ("reasoning_chunk", {"content": "I should check the docs"})
    ]


def test_chunk_with_both_reasoning_and_text_emits_both(
    mapper: TokenChunkMapper,
) -> None:
    events = mapper.map_chunk(_chunk(content="answer", reasoning="thought"))

    # Order between the two within one chunk is not part of the contract; both
    # must reach the wire with their own content.
    assert sorted(_typed(events)) == [
        ("reasoning_chunk", {"content": "thought"}),
        ("text_chunk", {"content": "answer"}),
    ]


def test_empty_chunk_emits_nothing(mapper: TokenChunkMapper) -> None:
    assert mapper.map_chunk(_chunk()) == []
    assert mapper.map_chunk(_chunk(content="", reasoning="")) == []


# --- tool call announcement / arguments -------------------------------------


def test_first_tool_call_fragment_announces_the_call_before_args_are_done(
    mapper: TokenChunkMapper,
) -> None:
    # The provider sends the name and id up front and dribbles the arguments
    # afterwards; the feed must show the action immediately, so only
    # ``tool_call_started`` fires while the JSON is still incomplete.
    events = mapper.map_chunk(
        _chunk(
            tool_calls=[
                _fragment(name="firecrawl_search", args='{"query": ', id="c1", index=0)
            ]
        )
    )

    assert _typed(events) == [
        ("tool_call_started", {"call_id": "c1", "tool": "firecrawl_search"})
    ]


def test_args_are_emitted_once_the_accumulated_json_is_complete(
    mapper: TokenChunkMapper,
) -> None:
    mapper.map_chunk(
        _chunk(tool_calls=[_fragment(name="search", args='{"q":', id="c1", index=0)])
    )

    events = mapper.map_chunk(_chunk(tool_calls=[_fragment(args='"cats"}', index=0)]))

    assert _typed(events) == [
        (
            "tool_call_args",
            {"call_id": "c1", "args": '{"q":"cats"}', "truncated": False},
        )
    ]


def test_further_fragments_after_completion_do_not_repeat_started_or_args(
    mapper: TokenChunkMapper,
) -> None:
    # Both events are once-per-call: a feed row must not be announced twice nor
    # have its "ВЫЗОВ" section rewritten by a late fragment.
    mapper.map_chunk(
        _chunk(tool_calls=[_fragment(name="search", args="{}", id="c1", index=0)])
    )

    events = mapper.map_chunk(_chunk(tool_calls=[_fragment(args="", index=0)]))

    assert events == []


def test_fragment_carrying_only_an_index_is_attributed_to_the_open_call(
    mapper: TokenChunkMapper,
) -> None:
    # Providers put the call id on the first fragment only; the rest correlate
    # by ``index``. Losing that correlation would strand the arguments.
    mapper.map_chunk(
        _chunk(tool_calls=[_fragment(name="search", args="", id="c1", index=0)])
    )

    events = mapper.map_chunk(
        _chunk(tool_calls=[_fragment(args='{"q": "v"}', index=0)])
    )

    assert _typed(events) == [
        ("tool_call_args", {"call_id": "c1", "args": '{"q": "v"}', "truncated": False})
    ]


def test_parallel_tool_calls_are_announced_and_filled_independently(
    mapper: TokenChunkMapper,
) -> None:
    # Two calls generated in one turn interleave by ``index``; each row in the
    # feed gets its own id, name and arguments.
    started = mapper.map_chunk(
        _chunk(
            tool_calls=[
                _fragment(name="search", args="", id="c1", index=0),
                _fragment(name="scrape", args="", id="c2", index=1),
            ]
        )
    )
    filled = mapper.map_chunk(
        _chunk(
            tool_calls=[
                _fragment(args='{"q": "a"}', index=0),
                _fragment(args='{"url": "b"}', index=1),
            ]
        )
    )

    assert _typed(started) == [
        ("tool_call_started", {"call_id": "c1", "tool": "search"}),
        ("tool_call_started", {"call_id": "c2", "tool": "scrape"}),
    ]
    assert _typed(filled) == [
        ("tool_call_args", {"call_id": "c1", "args": '{"q": "a"}', "truncated": False}),
        (
            "tool_call_args",
            {"call_id": "c2", "args": '{"url": "b"}', "truncated": False},
        ),
    ]


def test_oversized_args_are_truncated_and_flagged(mapper: TokenChunkMapper) -> None:
    args = json.dumps({"text": "x" * (TRUNCATION_LIMIT * 2)})

    events = mapper.map_chunk(
        _chunk(tool_calls=[_fragment(name="write", args=args, id="c1", index=0)])
    )

    args_event = next(e for e in events if e.type == "tool_call_args")
    assert args_event.data["truncated"] is True
    assert len(args_event.data["args"]) == TRUNCATION_LIMIT


def test_a_fresh_mapper_does_not_inherit_another_runs_calls() -> None:
    # Per-run instance: two concurrent user streams share nothing, so the same
    # provider-assigned id in a second run is announced again rather than being
    # swallowed as a duplicate.
    first = TokenChunkMapper()
    first.map_chunk(
        _chunk(tool_calls=[_fragment(name="search", args="{}", id="c1", index=0)])
    )

    second = TokenChunkMapper()
    events = second.map_chunk(
        _chunk(tool_calls=[_fragment(name="search", args="{}", id="c1", index=0)])
    )

    assert [e.type for e in events] == ["tool_call_started", "tool_call_args"]
