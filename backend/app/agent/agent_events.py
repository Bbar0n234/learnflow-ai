"""Safe custom-channel emission for domain ``agent_event``s.

Tools call :func:`emit_agent_event` to report a domain-level write (KS
section, user memory, skill context); ``graph.py``'s compaction step reports
through it too. The runner's ``stream_mode="custom"`` handling
(``app.agent.runner``) recognizes :data:`DOMAIN_AGENT_EVENT_KINDS` and wraps
them into the wire's ``agent_event {kind, payload, parent_call_id?}``
(design-brief § "Контракт SSE v2").

Resolving *which* stream writer to use is the whole point of this module —
three sources, tried in this priority order:

1. An explicitly captured writer, stashed in :data:`SUBAGENT_STREAM_WRITER`
   by the subagent tool-execution wrapper for the duration of one subagent
   tool call. Required because a subagent runs a nested, separately compiled
   Pregel graph via ``ainvoke`` — inside it, ``get_stream_writer()``
   *succeeds* (it returns that nested run's own writer), but nothing ever
   consumes that run's custom stream (the outer call is ``ainvoke``, not
   ``astream``), so anything written there goes nowhere. Checking this
   contextvar first is what lets the same KS/memory/skill-context tools,
   called from inside a subagent, still surface on the *main* stream instead
   of silently vanishing — this priority order is a requirement, not a
   preference, and is why source (2) below must never be tried first.
2. ``get_stream_writer()`` — the tool is running inside the main graph's own
   Pregel run, where this always resolves correctly.
3. A no-op — the tool is running outside any graph runtime at all. Every
   existing tool test calls ``tool.ainvoke(...)`` directly, which makes
   ``get_stream_writer()`` raise ``KeyError('__pregel_runtime')``; a bare
   function call outside any runnable context (e.g. ``_reduce_context``
   invoked directly in a unit test) raises ``RuntimeError`` instead — both
   are caught so this helper never breaks a test that doesn't care about
   streaming.

The same subagent tool-execution wrapper also stashes the wrapping
``run_subagent`` call's own ``call_id`` in :data:`SUBAGENT_PARENT_CALL_ID`,
for the same duration. A domain tool body (``sphere_write``, ``memory_write``,
...) has no idea whether it is running inside a subagent — it just calls
:func:`emit_agent_event` the same way either way — so attaching
``parent_call_id`` to the wire event has to happen here, by reading this
contextvar, rather than by threading a parameter through every tool
(design-brief § "Вложенность субагента").
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Final

from langgraph.config import get_stream_writer
from langgraph.types import StreamWriter

from app.agent.text_limits import truncate

# The only kinds the runner recognizes and wraps into `agent_event`
# (design-brief § "Контракт SSE v2"). Shared with `app.agent.runner` so the
# two sides of the custom channel (emitters here, dispatch there) can't drift
# apart into recognizing different sets.
DOMAIN_AGENT_EVENT_KINDS: Final = frozenset(
    {"sphere_write", "memory_write", "skill_context_write", "compaction"}
)

# Set by the subagent tool-execution wrapper for the duration of one subagent
# tool call (`.set()` / `.reset(token)` around the call, in `finally`); `None`
# everywhere else (main graph, outside any graph).
SUBAGENT_STREAM_WRITER: ContextVar[StreamWriter | None] = ContextVar(
    "subagent_stream_writer", default=None
)

# Set alongside `SUBAGENT_STREAM_WRITER`, same lifetime — the `call_id` of the
# `run_subagent` tool call whose subagent is currently executing a tool.
# `None` everywhere else.
SUBAGENT_PARENT_CALL_ID: ContextVar[str | None] = ContextVar(
    "subagent_parent_call_id", default=None
)


def _noop_writer(_: Any) -> None:
    return None


def _resolve_writer() -> StreamWriter:
    explicit = SUBAGENT_STREAM_WRITER.get()
    if explicit is not None:
        return explicit
    try:
        return get_stream_writer()
    except (KeyError, RuntimeError):
        return _noop_writer


def emit_agent_event(kind: str, payload: dict[str, Any]) -> None:
    """Emit a domain ``agent_event`` on the custom stream channel.

    Safe to call unconditionally — see module docstring for the three writer
    sources tried, in order; outside any graph runtime this is a no-op.
    String payload values are truncated by the same policy as the rest of the
    SSE/API surface (``text_limits.truncate``) before reaching the wire.
    When called while a subagent tool is executing, the emitted event also
    carries ``parent_call_id`` (read from :data:`SUBAGENT_PARENT_CALL_ID`) so
    the runner can attribute it to the right nested-line in the activity feed.
    """
    if kind not in DOMAIN_AGENT_EVENT_KINDS:
        raise ValueError(f"unknown agent_event kind: {kind!r}")

    truncated_payload: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            value, _truncated = truncate(value)
        truncated_payload[key] = value

    event: dict[str, Any] = {"type": kind, "payload": truncated_payload}
    parent_call_id = SUBAGENT_PARENT_CALL_ID.get()
    if parent_call_id is not None:
        event["parent_call_id"] = parent_call_id

    writer = _resolve_writer()
    writer(event)
