"""Maps LangGraph stream payloads to domain ``StreamEvent``s.

``StreamEventMapper`` translates ``stream_mode="updates"`` node outputs (a
guard cut of the turn's tool calls) into the SSE-facing event vocabulary;
``TokenChunkMapper`` does the same for ``stream_mode="messages"`` chunks (text,
reasoning, tool-call assembly). Either way the runner stays free of graph
payload shape knowledge.

The third road to the wire does not pass through the runner's mappers at all:
:func:`tool_result_envelope`/:func:`artifact_envelopes` build the
``custom``-channel envelopes the tools node writes itself, one per finished
tool call (``tool_guards.execute_tools_guarded``). They live here, next to the
mappers, because this module is the one place that knows what a wire event
looks like — the node picks the moment, this module picks the shape.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langchain_core.messages.tool import ToolCallChunk
from langgraph.types import StreamWriter

from app.agent.text_limits import truncate
from app.services.agent_runner import StreamEvent


def tool_result_envelope(
    message: ToolMessage, *, parent_call_id: str | None = None
) -> dict[str, Any]:
    """Build the ``custom``-channel envelope for one finished tool call.

    Shaped exactly as the runner's custom-channel passthrough expects
    (``app.agent.runner``: a known ``type`` plus its wire ``data``), so what
    reaches the client is indistinguishable from an event the mappers built.
    ``parent_call_id`` is set only for a subagent's nested call.
    """
    content = (
        message.content if isinstance(message.content, str) else str(message.content)
    )
    content_text, content_truncated = truncate(content)
    data: dict[str, Any] = {
        "call_id": message.tool_call_id,
        "tool": message.name or "",
        "status": message.status,
        "content": content_text,
        "truncated": content_truncated,
    }
    if parent_call_id is not None:
        data["parent_call_id"] = parent_call_id
    return {"type": "tool_result", "data": data}


def artifact_envelopes(message: ToolMessage) -> list[dict[str, Any]]:
    """Build the ``artifact_created``/``artifact_updated`` envelopes, or ``[]``.

    Emitted by attribute (``response_format="content_and_artifact"``), never by
    tool name, and always right after the ``tool_result`` of the same call —
    which is why they are written by the same reporter rather than by a channel
    of their own (streaming.md § «tool_result / artifact_created»).

    ``message.artifact`` is a list, one element per file the call touched (a
    job can write several) — each element's ``kind`` (``"created"`` /
    ``"updated"``, default ``"created"``) picks the event type and is then
    dropped from the payload, since the event ``type`` already carries that
    distinction; ``diff`` (present only on an update) rides through unchanged.
    Wire-name for the file's own type is ``artifact_type`` — the flat envelope
    ``messages.py`` builds (``{"type": event.type, **event.data}``) would let a
    payload key literally named ``type`` clobber the event's own.

    A non-list ``artifact`` (older checkpoint form — see ``checkpoint_history.
    _artifact_parts``) never reaches this path on a live run — this module only
    ever sees messages the tools node just produced — but the guard is kept in
    sync with the read side rather than trusted implicitly.
    """
    if not message.artifact or not isinstance(message.artifact, list):
        return []
    envelopes: list[dict[str, Any]] = []
    for item in message.artifact:
        data = dict(item)
        data["artifact_type"] = data.pop("type", "")
        kind = data.pop("kind", "created")
        if kind == "updated":
            data.setdefault("diff", None)
            envelopes.append({"type": "artifact_updated", "data": data})
        else:
            data.pop("diff", None)
            envelopes.append({"type": "artifact_created", "data": data})
    return envelopes


def make_tool_result_reporter(
    writer: StreamWriter, *, parent_call_id: str | None = None
) -> Callable[[ToolMessage], None]:
    """Reporter for ``execute_tools_guarded``: one checked result -> the wire.

    Called the moment a single tool call's result clears the TOOL_RESULT
    guard — not when the batch does — so a fast call never inherits a slow
    neighbour's duration in the activity feed. Any artifact envelopes the call
    produced follow right after, in order — a job touching N files reports N
    of them.
    """

    def report(message: ToolMessage) -> None:
        writer(tool_result_envelope(message, parent_call_id=parent_call_id))
        for artifact in artifact_envelopes(message):
            writer(artifact)

    return report


class StreamEventMapper:
    """Per-run ``stream_mode="updates"`` node payload -> updates-channel ``StreamEvent``s.

    The one event born here is ``tool_call_cancelled``. ``tool_result`` and
    ``artifact_created``/``artifact_updated`` are not: they are written by the
    tools node itself, per finished call, because a node update only ever
    arrives once the *whole* batch is done — which is precisely the wait that
    made a fast call inherit a slow neighbour's duration in the feed.

    **Must be instantiated fresh per run**, same reasoning as ``TokenChunkMapper``
    (see below): it tracks which tool-call ``call_id``s the token channel has
    already announced (``tool_call_started``) but that haven't resolved yet,
    via ``note_call_announced`` — the runner calls it whenever the token
    channel emits ``tool_call_started``. That bookkeeping is what lets
    ``updates()`` emit ``tool_call_cancelled`` when a guard cuts a turn's tool
    calls: by the time the redacted ``AIMessage`` reaches this node's payload,
    ``tool_guards.guard_tool_call_args`` has already stripped ``tool_calls`` to
    an empty list, so the payload itself no longer carries the cut ids — only
    this per-run "announced, not yet resolved" set does.
    """

    def __init__(self) -> None:
        self._pending_call_ids: list[str] = []

    def note_call_announced(self, call_id: str) -> None:
        """Record a ``call_id`` the token channel announced via ``tool_call_started``.

        Resolved later either by a matching ``ToolMessage`` (``tool_result``) or
        by a guard cutting the turn's tool calls (``tool_call_cancelled``).
        """
        if call_id not in self._pending_call_ids:
            self._pending_call_ids.append(call_id)

    def updates(self, data: dict[str, Any]) -> list[StreamEvent]:
        events: list[StreamEvent] = []

        if "agent" in data:
            for msg in data["agent"].get("messages", []):
                # Recognizing a guard cut: an ``AIMessage`` (never a
                # ``ToolMessage`` — ``guard_tool_result`` stamps the same
                # ``security_redacted`` flag on those, for an unrelated
                # TOOL_RESULT redaction) with tool_calls stripped to empty by
                # ``guard_tool_call_args`` (``tool_guards.py``). Comparing
                # ``original_detection_layer`` to a checkpoint string is not
                # this signal — that field holds a ``DetectionLayer`` value.
                if (
                    isinstance(msg, AIMessage)
                    and not msg.tool_calls
                    and msg.additional_kwargs.get("security_redacted")
                ):
                    for call_id in self._pending_call_ids:
                        events.append(
                            StreamEvent(
                                type="tool_call_cancelled",
                                data={"call_id": call_id},
                            )
                        )
                    self._pending_call_ids = []

        if "tools" in data:
            # Bookkeeping only, no emission: the node has already reported each
            # of these results on the custom channel, one by one, as it checked
            # them (``make_tool_result_reporter``). What the node payload is
            # still needed for is the other half of the same ledger — a call
            # that produced a result is resolved and must never be reported as
            # cancelled afterwards.
            for msg in data["tools"].get("messages", []):
                if isinstance(msg, ToolMessage):
                    call_id = msg.tool_call_id
                    if call_id in self._pending_call_ids:
                        self._pending_call_ids.remove(call_id)

        return events


class TokenChunkMapper:
    """Per-run ``stream_mode="messages"`` chunk -> token-channel ``StreamEvent``s.

    Splits one raw ``AIMessageChunk`` into its constituent wire events —
    ``reasoning_chunk`` (``additional_kwargs["reasoning"]``), ``text_chunk``
    (``content``), and the ``tool_call_started``/``tool_call_args`` pair
    assembled from ``tool_call_chunks`` (name+id known on the first fragment
    of a call, args accumulated incrementally as a JSON string).

    **Must be instantiated fresh per run**, never shared on the runner's
    ``__init__``: it accumulates tool-call assembly state (which ``call_id``s
    were already announced, the args JSON accumulated so far) keyed by the
    provider-assigned ``call_id``/``index``. A shared instance would let two
    concurrent users' streams collide on the same ids — conventions.md's
    "никакого module-level/shared состояния" applies equally to a
    long-lived collaborator instance holding per-request state.
    """

    def __init__(self) -> None:
        self._call_id_by_index: dict[int, str] = {}
        self._tool_by_call_id: dict[str, str] = {}
        self._args_by_call_id: dict[str, str] = {}
        self._announced_call_ids: set[str] = set()
        self._args_emitted_call_ids: set[str] = set()

    def map_chunk(self, chunk: AIMessageChunk) -> list[StreamEvent]:
        events: list[StreamEvent] = []

        reasoning: Any = None
        if isinstance(chunk.additional_kwargs, dict):
            reasoning = chunk.additional_kwargs.get("reasoning")
        if isinstance(reasoning, str) and reasoning:
            events.append(
                StreamEvent(type="reasoning_chunk", data={"content": reasoning})
            )

        if isinstance(chunk.content, str) and chunk.content:
            events.append(
                StreamEvent(type="text_chunk", data={"content": chunk.content})
            )

        for tool_call_chunk in chunk.tool_call_chunks:
            events.extend(self._map_tool_call_chunk(tool_call_chunk))

        return events

    def _map_tool_call_chunk(self, chunk: ToolCallChunk) -> list[StreamEvent]:
        index = chunk.get("index")
        call_id = chunk.get("id")
        if call_id and index is not None:
            self._call_id_by_index[index] = call_id
        resolved_call_id = call_id or (
            self._call_id_by_index.get(index) if index is not None else None
        )
        if resolved_call_id is None:
            # Fragment carries no id anywhere to correlate it to a call
            # (shouldn't happen per provider contract — id arrives on the
            # first fragment of every call) — nothing to attribute it to.
            return []

        name = chunk.get("name")
        if name:
            self._tool_by_call_id[resolved_call_id] = name

        events: list[StreamEvent] = []
        if resolved_call_id not in self._announced_call_ids:
            self._announced_call_ids.add(resolved_call_id)
            events.append(
                StreamEvent(
                    type="tool_call_started",
                    data={
                        "call_id": resolved_call_id,
                        "tool": self._tool_by_call_id.get(resolved_call_id, ""),
                    },
                )
            )

        args_fragment = chunk.get("args") or ""
        if args_fragment:
            self._args_by_call_id[resolved_call_id] = (
                self._args_by_call_id.get(resolved_call_id, "") + args_fragment
            )

        accumulated = self._args_by_call_id.get(resolved_call_id, "")
        if (
            resolved_call_id not in self._args_emitted_call_ids
            and self._is_complete_json(accumulated)
        ):
            self._args_emitted_call_ids.add(resolved_call_id)
            args_text, truncated = truncate(accumulated)
            events.append(
                StreamEvent(
                    type="tool_call_args",
                    data={
                        "call_id": resolved_call_id,
                        "args": args_text,
                        "truncated": truncated,
                    },
                )
            )
        return events

    @staticmethod
    def _is_complete_json(text: str) -> bool:
        if not text:
            return False
        try:
            json.loads(text)
        except ValueError:
            return False
        return True
