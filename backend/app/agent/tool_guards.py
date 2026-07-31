"""Shared ToolNode/guard building blocks for the main graph and subagent graphs.

Extracted out of ``app.agent.graph`` (T1.5, feat-011) so that
``app.agent.subagents.graph`` can reuse them without a circular import:
``app.agent.graph`` itself imports ``app.agent.tools.ks_helpers``, and
``app.agent.tools.__init__`` eagerly imports ``app.agent.tools.subagents``,
which imports ``app.agent.subagents`` (package) -> ``subagents.runner`` ->
``subagents.graph`` — so a subagent-graph module reaching back into
``app.agent.graph`` at import time deadlocks on a partially-initialized
module. This module has no dependency on ``app.agent.tools``/
``app.agent.subagents``, so both graph builders can import it safely.

Same checkpoints, same log events/severity, same fail-safe redact semantics
(design-brief § "Безопасность": tool-result injection -> content swapped for
a stub, cycle continues; tool-call-arg injection -> ``tool_calls`` stripped,
cycle ends). Both graphs reuse the same building blocks: the TOOL_CALL_ARG
check runs in the model node (``app.agent.graph.agent_node`` / the subagent's
``llm`` node) on the response it just produced, the TOOL_RESULT check runs in
the tools node via :func:`execute_tools_guarded`, once per tool call — see its
docstring for why that node and not the next one, and why per call and not per
batch.

Layering: this is an *enforcement adapter* over the security engine
(``app.agent.security`` — detectors, classifier, ``SecurityGuard``), not part
of the engine itself. Living at the ``app/agent/`` level next to the graphs
it protects is deliberate — same placement as ``runtime_security.py``
(stream-checkpoint enforcement); see conventions/agent.md § Agent Runtime.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Sequence
from functools import partial
from typing import Any

import structlog
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import Runnable
from langgraph.config import get_config
from siem_contracts import AGENT_GUARD_DEGRADED

from app.agent.security.guard import SecurityGuard
from app.agent.security.types import Checkpoint, DetectionLayer, Verdict

logger = structlog.get_logger()

_TOOL_ERROR_MESSAGE = (
    "Tool execution failed; the requested operation could not be completed. "
    "Please try a different approach or rephrasing the request."
)


def handle_tool_error(exc: Exception) -> str:
    """Callable handler for ToolNode(handle_tool_errors=...).

    Logs the exception with exc_info so operators have full context, then
    returns a safe, non-leaking message that goes into ToolMessage(status="error").
    The message is seen only by the agent (LLM), not by the end user.
    """
    logger.error(
        "tool execution failed",
        error_type=type(exc).__name__,
        exc_info=exc,
    )
    return _TOOL_ERROR_MESSAGE


def _log_guard_degraded(event: str, *, reason: str, **details: Any) -> None:
    """Report a TOOL_RESULT check that ran without its full input, or not at all.

    The guard is fail-safe (fail-open) by design — a checkpoint that cannot
    do its job lets the cycle continue instead of blocking the thread — but
    every road of that degradation is observable, and by the same shape the
    engine itself uses (``security/guard.py``): ``security_event=True`` +
    the canonical ``agent.guard.degraded`` + ``severity`` + metadata. Silent
    degradation is what turns a latent branch into an incident nobody can
    trace back (conventions.md § «Восстановление», § Logging).
    """
    logger.error(
        event,
        security_event=True,
        event_type=AGENT_GUARD_DEGRADED,
        severity="critical",
        metadata={
            "checkpoint": Checkpoint.TOOL_RESULT.value,
            "detection_layer": DetectionLayer.GRACEFUL_DEGRADATION.value,
            "verdict": "clean",
            "reason": reason,
            **details,
        },
    )


def _state_messages(state: Any) -> list[Any] | None:
    """Read the conversation out of a graph state; ``None`` when it has none.

    Both graphs run on ``MessagesState`` (a dict), but a state schema may
    also be a Pydantic model or a dataclass — hence the attribute fallback.
    ``None`` means "this shape has no readable ``messages``" and is a signal
    for the caller to degrade observably, not a licence to skip the check.
    """
    messages = (
        state.get("messages")
        if isinstance(state, dict)
        else getattr(state, "messages", None)
    )
    if isinstance(messages, Sequence) and not isinstance(messages, str | bytes):
        return list(messages)
    return None


async def guard_tool_result(
    message: ToolMessage,
    guard: SecurityGuard,
    canary_token: str,
    tool_result_stub: str,
    history: list[Any],
) -> ToolMessage:
    """Check one tool result; return it, or its redacted replacement.

    One result, one classifier call — the unit of the check is a single tool
    call, so a result can neither be skipped (there is no batch to fall out of)
    nor judged twice (nothing re-enters this function once it carries
    ``security_redacted``). ``history`` is the conversation as the calling node
    received it, offered to the classifier as context; an empty one is a
    degraded check, never a skipped one.
    """
    if message.additional_kwargs.get("security_redacted"):
        return message

    content = (
        message.content if isinstance(message.content, str) else str(message.content)
    )
    result = await guard.check(
        content,
        Checkpoint.TOOL_RESULT,
        history=history,
        canary_token=canary_token,
    )
    if result.verdict != Verdict.INJECTION:
        return message

    logger.warning(
        "tool_result injection blocked",
        security_event=True,
        checkpoint=Checkpoint.TOOL_RESULT.value,
        verdict=Verdict.INJECTION.value,
        metadata={
            "detection_layer": (
                result.detection_layer.value if result.detection_layer else None
            ),
            "tool": message.name,
        },
    )
    # The redacted message *replaces* the raw one rather than being appended
    # next to it — the poisoned text never enters the state at all. ``id`` is
    # carried over as-is: the message has not passed through ``add_messages``
    # yet, so it may still be unset, and the replacement must not invent one.
    return ToolMessage(
        id=message.id,
        tool_call_id=message.tool_call_id,
        name=message.name,
        content=tool_result_stub,
        additional_kwargs={
            **message.additional_kwargs,
            "security_redacted": True,
            "original_detection_layer": (
                result.detection_layer.value
                if result.detection_layer
                else Checkpoint.TOOL_RESULT.value
            ),
        },
    )


def _split_per_call(state: Any, history: list[Any]) -> list[Any] | None:
    """Split a multi-call batch into one node input per tool call.

    Mirrors ``ToolNode._parse_input``: the calls it would execute are those of
    the *last* ``AIMessage``, so that is the message replaced — by a copy
    carrying a single call — in an otherwise untouched state, keeping whatever
    a tool reads off it (``ToolRuntime.state``) the same as in a batch run.

    ``None`` means "not splittable, run the node once": a state that is not a
    mapping (nothing to rebuild), a conversation that cannot be read, or a
    batch of one — where a split would be a copy of the original.
    """
    if not isinstance(state, dict) or not history:
        return None
    anchor_index = -1
    for i, message in enumerate(history):
        if isinstance(message, AIMessage):
            anchor_index = i
    if anchor_index == -1:
        return None
    anchor = history[anchor_index]
    calls = list(getattr(anchor, "tool_calls", None) or [])
    if len(calls) < 2:
        return None
    return [
        {
            **state,
            "messages": [
                *history[:anchor_index],
                anchor.model_copy(update={"tool_calls": [call]}),
                *history[anchor_index + 1 :],
            ],
        }
        for call in calls
    ]


def _merge_outputs(outputs: list[Any]) -> Any:
    """Recombine per-call node outputs into one node return value.

    Ordinary case — every call answered with a messages dict: one dict, the
    results in the order the model asked for them (not the order they
    finished), so the conversation written to the checkpoint reads the same as
    it did when the whole batch ran at once. The other case exists only
    because ``ToolNode`` answers with a list once a tool returns a ``Command``:
    those outputs are passed through side by side, the shape LangGraph already
    accepts from a node.
    """
    if all(isinstance(output, dict) for output in outputs):
        merged: dict[str, Any] = {}
        for output in outputs:
            merged.update({k: v for k, v in output.items() if k != "messages"})
        merged["messages"] = [
            m for output in outputs for m in output.get("messages", [])
        ]
        return merged
    flattened: list[Any] = []
    for output in outputs:
        if isinstance(output, list):
            flattened.extend(output)
        else:
            flattened.append(output)
    return flattened


async def _run_and_check(
    tool_node: Runnable[Any, Any],
    node_input: Any,
    config: Any,
    *,
    guard: SecurityGuard | None,
    history: list[Any],
    canary_token: str,
    tool_result_stub: str,
    on_result: Callable[[ToolMessage], None] | None,
) -> Any:
    """Run the tools node over one input and check+report each result it yields."""
    result = await tool_node.ainvoke(node_input, config)

    messages = result.get("messages") if isinstance(result, dict) else None
    if not isinstance(messages, list):
        # Unrecognised node output: ``ToolNode`` answers with a *list*
        # (``Command``s, plus one dict per plain result) as soon as a single
        # tool returns a ``Command``, and there is no ``ToolMessage`` batch in
        # that shape to hand the guard. No tool in this codebase returns a
        # ``Command`` today, so the branch is latent — but it is precisely the
        # branch on which results would reach the wire and the checkpoint
        # unchecked, so it degrades *loudly* instead of opening in silence
        # (conventions.md § «Восстановление: fail-safe vs fail-secure» —
        # деградация guard всегда наблюдаема).
        if guard is not None:
            _log_guard_degraded(
                "tool_result guard skipped: unrecognised tools output",
                reason="unsupported_tools_output",
                output_type=type(result).__name__,
            )
        return result

    checked: list[Any] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            checked.append(message)
            continue
        if guard is not None:
            message = await guard_tool_result(
                message, guard, canary_token, tool_result_stub, history
            )
        checked.append(message)
        if on_result is not None:
            # Reported only here, after the check and before this coroutine
            # returns: what goes on the wire is what the guard cleared, and it
            # goes there the moment *this* call is done, not when its
            # neighbours are.
            on_result(message)

    return {**result, "messages": checked}


async def execute_tools_guarded(
    tool_node: Runnable[Any, Any],
    state: Any,
    *,
    guard: SecurityGuard | None,
    canary_token: str,
    tool_result_stub: str,
    on_result: Callable[[ToolMessage], None] | None = None,
) -> Any:
    """Run the tools node per tool call, checking and reporting each result on its own.

    Two properties, and the second is why this function exists at all:

    *The TOOL_RESULT check lives inside the tools node*, not on re-entry into
    the calling node, because the node's own output is what reaches the wire
    and the checkpoint. A check that ran one super-step later would always run
    *after* the poisoned text had been shown to the user — the redaction would
    only ever reach the model.

    *Each call is its own unit of work.* ``ToolNode`` executes a batch and
    answers when the slowest member of it finishes, so a batch-shaped node
    reports a search that took ten seconds as still running until a subagent
    sharing its turn finishes three minutes later — the feed shows finished
    work as unfinished and hangs someone else's duration on it. So a
    multi-call batch is split into one node input per call
    (``_split_per_call``), the calls run concurrently as before, and each
    result is checked and handed to ``on_result`` the moment its own call is
    done. The price is deliberate and was weighed: one classifier call per
    result instead of one per batch — more tokens and more money on parallel
    turns, in exchange for a feed that tells the truth about what has and has
    not finished. Do not "optimise" it back into a batch.

    ``on_result`` receives one final, checked ``ToolMessage`` at a time — the
    hook both graphs report their ``tool_result`` through, which is why the
    reporting cannot live in the subagent's tool proxy (``subagents/runner.py``):
    there, the text has been through neither the guard nor ``ToolNode``'s error
    sanitizer.

    Neither way this function can end up not checking a result — a node output
    that carries no ``ToolMessage`` batch, a state whose conversation cannot be
    read — passes in silence: both report through ``_log_guard_degraded``
    before the cycle continues.
    """
    config = get_config()
    history = _state_messages(state)
    if history is None:
        # A state the conversation cannot be read out of (a Pydantic or
        # dataclass state schema without ``messages``). Every result is still
        # checked — one by one, as always — but the classifier works without
        # context, which is a degradation and is reported as one.
        if guard is not None:
            _log_guard_degraded(
                "tool_result guard degraded: state history unreadable",
                reason="state_history_unreadable",
                state_type=type(state).__name__,
            )
        history = []

    run = partial(
        _run_and_check,
        tool_node,
        config=config,
        guard=guard,
        history=history,
        canary_token=canary_token,
        tool_result_stub=tool_result_stub,
        on_result=on_result,
    )

    per_call_inputs = _split_per_call(state, history)
    if per_call_inputs is None:
        return await run(state)

    outputs = await asyncio.gather(
        *(run(node_input) for node_input in per_call_inputs),
        return_exceptions=True,
    )
    # Gathered with ``return_exceptions`` so a failing call cannot leave its
    # siblings running unawaited past this node; the first failure is then
    # re-raised, exactly as it would have propagated out of a single
    # ``ToolNode`` invocation.
    for output in outputs:
        if isinstance(output, BaseException):
            raise output
    return _merge_outputs(list(outputs))


async def guard_tool_call_args(
    response: AIMessage,
    guard: SecurityGuard,
    canary_token: str,
    history: list[Any],
) -> AIMessage:
    """Check a model response's tool_calls args for injection; fail-safe redact.

    No-op (returns ``response`` unchanged) when there are no tool_calls to
    check or the guard clears the payload. On ``Verdict.INJECTION`` the
    tool_calls are stripped — a redacted ``AIMessage`` with no tool_calls is
    returned (routes to END via ``tools_condition`` instead of the tools
    node) rather than blocking the thread, mirroring ``guard_tool_result``'s
    fail-safe-not-fail-closed semantics.
    """
    if not getattr(response, "tool_calls", None):
        return response

    args_payload = json.dumps(
        [tc.get("args", {}) for tc in response.tool_calls],
        ensure_ascii=False,
    )
    arg_result = await guard.check(
        args_payload,
        Checkpoint.TOOL_CALL_ARG,
        history=history,
        canary_token=canary_token,
    )
    if arg_result.verdict != Verdict.INJECTION:
        return response

    redacted = AIMessage(
        id=response.id,
        content=response.content if isinstance(response.content, str) else "",
        tool_calls=[],
        additional_kwargs={
            **response.additional_kwargs,
            "security_redacted": True,
            "original_detection_layer": (
                arg_result.detection_layer.value
                if arg_result.detection_layer
                else Checkpoint.TOOL_CALL_ARG.value
            ),
        },
    )
    logger.warning(
        "tool_call_arg injection blocked",
        security_event=True,
        checkpoint=Checkpoint.TOOL_CALL_ARG.value,
        verdict=Verdict.INJECTION.value,
        metadata={
            "detection_layer": (
                arg_result.detection_layer.value if arg_result.detection_layer else None
            ),
        },
    )
    return redacted
