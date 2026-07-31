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
the tools node via :func:`execute_tools_guarded` — see its docstring for why
that node and not the next one.

Layering: this is an *enforcement adapter* over the security engine
(``app.agent.security`` — detectors, classifier, ``SecurityGuard``), not part
of the engine itself. Living at the ``app/agent/`` level next to the graphs
it protects is deliberate — same placement as ``runtime_security.py``
(stream-checkpoint enforcement); see conventions/agent.md § Agent Runtime.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
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


async def guard_tool_results(
    messages: list[Any],
    guard: SecurityGuard,
    canary_token: str,
    tool_result_stub: str,
) -> list[ToolMessage]:
    """Scan the current batch of ToolMessages; return replace-by-id updates for injections.

    ``messages`` is the conversation with the fresh, not-yet-checked batch
    appended to it. The last ``AIMessage`` carrying ``tool_calls`` is the
    anchor that splits the two: everything up to and including it is context
    for the classifier, every ``ToolMessage`` after it is checked. When there
    is no anchor — a caller that could not read the conversation out of its
    state and handed over the bare batch — the split degenerates to "no
    context, check everything" rather than to "check nothing": the classifier
    loses history, the check itself never lapses. Skipping on a missing
    anchor would be a silent fail-open inside the very function that exists
    to prevent one.
    """
    if not messages:
        return []
    anchor = -1
    for i, m in enumerate(messages):
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            anchor = i
    batch = [
        m
        for m in messages[anchor + 1 :]
        if isinstance(m, ToolMessage)
        and not m.additional_kwargs.get("security_redacted")
    ]
    if not batch:
        return []

    updates: list[ToolMessage] = []
    for tm in batch:
        content = tm.content if isinstance(tm.content, str) else str(tm.content)
        result = await guard.check(
            content,
            Checkpoint.TOOL_RESULT,
            history=messages[: anchor + 1],
            canary_token=canary_token,
        )
        if result.verdict == Verdict.INJECTION:
            updates.append(
                ToolMessage(
                    id=tm.id,
                    tool_call_id=tm.tool_call_id,
                    name=tm.name,
                    content=tool_result_stub,
                    additional_kwargs={
                        **tm.additional_kwargs,
                        "security_redacted": True,
                        "original_detection_layer": (
                            result.detection_layer.value
                            if result.detection_layer
                            else Checkpoint.TOOL_RESULT.value
                        ),
                    },
                )
            )
            logger.warning(
                "tool_result injection blocked",
                security_event=True,
                checkpoint=Checkpoint.TOOL_RESULT.value,
                verdict=Verdict.INJECTION.value,
                metadata={
                    "detection_layer": (
                        result.detection_layer.value if result.detection_layer else None
                    ),
                    "tool": tm.name,
                },
            )
    return updates


async def execute_tools_guarded(
    tool_node: Runnable[Any, Any],
    state: Any,
    *,
    guard: SecurityGuard | None,
    canary_token: str,
    tool_result_stub: str,
    on_results: Callable[[list[ToolMessage]], None] | None = None,
) -> Any:
    """Run the tools node and let only guard-checked ``ToolMessage``s out of it.

    The TOOL_RESULT check lives *inside* the tools node rather than on
    re-entry into the calling node, because the node's own output is what
    reaches the wire: ``StreamEventMapper`` turns the ``tools`` update into
    ``tool_result`` (content included), and the subagent reports its nested
    results off the same batch. A check that ran one super-step later would
    always run *after* the poisoned text had already been shown to the user
    and written to the checkpoint — the redaction would only ever reach the
    model. Checking here costs the classifier's latency before the result
    appears in the feed; that is the price of never streaming unchecked tool
    output (streaming.md § «tool_result / artifact_created»).

    ``on_results`` receives the final, checked batch — the subagent's hook for
    reporting nested ``tool_result``s onto the parent stream, which is why the
    reporting cannot live in the tool proxy itself (``subagents/runner.py``).

    Neither way this function can end up not checking a batch in full — a
    node output that carries no ``ToolMessage`` batch, a state whose
    conversation cannot be read — passes in silence: both report through
    ``_log_guard_degraded`` before the cycle continues.
    """
    result = await tool_node.ainvoke(state, get_config())

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

    if guard is not None:
        history = _state_messages(state)
        if history is None:
            # A state the conversation cannot be read out of (a Pydantic or
            # dataclass state schema without ``messages``). The batch is still
            # checked — ``guard_tool_results`` runs anchor-less — but the
            # classifier works without context, which is a degradation and is
            # reported as one.
            _log_guard_degraded(
                "tool_result guard degraded: state history unreadable",
                reason="state_history_unreadable",
                state_type=type(state).__name__,
            )
            history = []
        updates = await guard_tool_results(
            [*history, *messages], guard, canary_token, tool_result_stub
        )
        if updates:
            # Matched by ``tool_call_id``, not by ``id``: these messages have
            # not passed through ``add_messages`` yet, so ``id`` may still be
            # unset. The redacted message *replaces* the raw one instead of
            # being appended next to it — the poisoned text never enters the
            # state at all.
            by_call_id = {u.tool_call_id: u for u in updates}
            messages = [
                by_call_id.get(m.tool_call_id, m) if isinstance(m, ToolMessage) else m
                for m in messages
            ]

    if on_results is not None:
        on_results([m for m in messages if isinstance(m, ToolMessage)])

    return {**result, "messages": messages}


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
    node) rather than blocking the thread, mirroring ``guard_tool_results``'s
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
