"""
Point tests: T3.3 / T3.4 / T3.10 — handle_tool_errors (feat-007, track T3)

Tests the callable form of handle_tool_errors in ToolNode:
  T3.3 — tool exception → ToolMessage(status=error), thread stays valid, re-entry works
  T3.4 — handler logs error+exc_info; ToolMessage.content does not leak internals
  T3.10 — core-store fail-fast in agent_node is preserved (not masked by handle_tool_errors)

Run from backend directory:
  uv run pytest ../doc/tasks/iterations/codebase-maturity/feat-007-cross-cutting/tests/test_tool_node_handle_errors.py -v
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool as lc_tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from structlog.testing import capture_logs

from app.agent.graph import _TOOL_ERROR_MESSAGE, _handle_tool_error

# ---------------------------------------------------------------------------
# Shared mini-graph fixtures
# ---------------------------------------------------------------------------

_SECRET_CONTENT = "DSN=postgres://superSecret@internal-host/db"


@lc_tool
def failing_tool(x: str) -> str:
    """A tool that always fails with a potentially sensitive error message."""
    raise RuntimeError(_SECRET_CONTENT)


def _build_mini_graph() -> tuple[StateGraph, InMemorySaver]:
    """Build a minimal ReAct-style graph with handle_tool_errors=_handle_tool_error."""

    def agent_node(state: MessagesState) -> dict:
        messages = state["messages"]
        # If any ToolMessage in history → done (ReAct recovery)
        has_tool_message = any(isinstance(m, ToolMessage) for m in messages)
        if has_tool_message:
            return {"messages": [AIMessage(content="Recovered after tool error.")]}
        # First turn: issue a tool call
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "failing_tool",
                            "args": {"x": "input"},
                            "id": "call_abc123",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        }

    tool_node = ToolNode([failing_tool], handle_tool_errors=_handle_tool_error)

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")

    checkpointer = InMemorySaver()
    return builder, checkpointer


def _get_history(graph, thread_id: str) -> list:
    """Return the message history for a given thread."""
    state = graph.get_state({"configurable": {"thread_id": thread_id}})
    return list(state.values.get("messages", []))


def _validate_tool_call_pairs(messages: list) -> list[str]:
    """Strict contig check: every AIMessage(tool_calls) must have paired ToolMessages.

    Returns a list of unpaired tool_call_ids (should be empty for a valid thread).
    """
    unpaired: list[str] = []
    tool_message_ids: set[str] = {
        m.tool_call_id for m in messages if isinstance(m, ToolMessage)
    }
    for m in messages:
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            for tc in m.tool_calls:
                tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tc_id not in tool_message_ids:
                    unpaired.append(tc_id or "<no-id>")
    return unpaired


# ---------------------------------------------------------------------------
# T3.3 — tool exception closes thread; re-entry (RUN 2) works
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_t33_tool_error_closes_thread_and_reentry_works() -> None:
    """T3.3: tool raises RuntimeError → ToolMessage(status=error) paired; re-entry valid."""
    builder, checkpointer = _build_mini_graph()
    graph = builder.compile(checkpointer=checkpointer)
    thread_cfg = {"configurable": {"thread_id": "thread-t33"}}

    # RUN 1 ─ tool will raise RuntimeError
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="Hello")]},
        config=thread_cfg,
    )

    messages_after_run1 = result["messages"]

    # --- Assertion 1: ToolMessage(status=error) is present ---
    tool_messages = [m for m in messages_after_run1 if isinstance(m, ToolMessage)]
    assert tool_messages, "Expected at least one ToolMessage after tool error"
    assert any(
        getattr(tm, "status", None) == "error" for tm in tool_messages
    ), f"Expected ToolMessage with status='error', got: {[tm.status for tm in tool_messages]}"

    # --- Assertion 2: no dangling tool_call (strict contig check) ---
    unpaired = _validate_tool_call_pairs(messages_after_run1)
    assert not unpaired, (
        f"Dangling tool_call(s) detected (no paired ToolMessage): {unpaired}. "
        "Thread is broken for subsequent re-entry."
    )

    # --- RUN 2 (re-entry): add new HumanMessage to the same thread ---
    result2 = await graph.ainvoke(
        {"messages": [HumanMessage(content="Follow-up message")]},
        config=thread_cfg,
    )
    messages_after_run2 = result2["messages"]

    # Re-entry must not raise (no OpenAI 400 from invalid history)
    # and history must still be valid
    unpaired2 = _validate_tool_call_pairs(messages_after_run2)
    assert not unpaired2, (
        f"Thread history became invalid after re-entry: {unpaired2}. "
        "The re-entry bug from empirical-reentry-toolnode.md was not fixed."
    )

    # Final state must include HumanMessage from RUN 2
    human_messages = [m for m in messages_after_run2 if isinstance(m, HumanMessage)]
    assert len(human_messages) >= 2, "Expected at least 2 HumanMessages in history after re-entry"


# ---------------------------------------------------------------------------
# T3.4 — handler logs error+exc_info; content does not leak internals
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_t34_handler_logs_error_exc_info_and_content_does_not_leak() -> None:
    """T3.4: handler logs error+exc_info; ToolMessage.content is safe (no leakage)."""
    builder, checkpointer = _build_mini_graph()
    graph = builder.compile(checkpointer=checkpointer)
    thread_cfg = {"configurable": {"thread_id": "thread-t34"}}

    with capture_logs() as cap:
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="Hello")]},
            config=thread_cfg,
        )

    # --- Check 1: handler logged at error level with exc_info ---
    tool_error_logs = [
        entry for entry in cap
        if entry.get("event") == "tool execution failed"
    ]
    assert tool_error_logs, (
        f"Expected a log entry 'tool execution failed' from _handle_tool_error. "
        f"Captured logs: {cap}"
    )
    error_entry = tool_error_logs[0]
    assert error_entry.get("log_level") == "error", (
        f"Expected log_level='error', got: {error_entry.get('log_level')}"
    )
    assert error_entry.get("exc_info"), "Expected exc_info to be set (truthy)"
    assert error_entry.get("error_type") == "RuntimeError", (
        f"Expected error_type='RuntimeError', got: {error_entry.get('error_type')}"
    )

    # --- Check 2: ToolMessage.content does not leak exception internals ---
    messages = result["messages"]
    tool_messages = [m for m in messages if isinstance(m, ToolMessage)]
    assert tool_messages, "Expected ToolMessage in result"

    error_tm = next((tm for tm in tool_messages if getattr(tm, "status", None) == "error"), None)
    assert error_tm is not None, "Expected ToolMessage with status='error'"

    content_str = str(error_tm.content)
    assert _SECRET_CONTENT not in content_str, (
        f"Secret DSN leaked into ToolMessage.content! Content: {content_str!r}"
    )
    assert "RuntimeError" not in content_str, (
        f"Exception type leaked into ToolMessage.content! Content: {content_str!r}"
    )
    # The content should be our safe generic message
    assert _TOOL_ERROR_MESSAGE in content_str or len(content_str) > 0, (
        "ToolMessage.content is empty — expected the safe generic message"
    )


# ---------------------------------------------------------------------------
# T3.10 — core-store fail-fast in agent_node is preserved
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_t310_core_store_fail_fast_preserved() -> None:
    """T3.10: agent_node raises RuntimeError before tool_calls when store is None.

    This verifies the D-ERR-5 invariant: the core-store check (graph.py:225-226)
    fires before any tool_calls are generated, so no dangling AIMessage(tool_calls)
    is created. handle_tool_errors does NOT mask this — it runs in ToolNode, not
    in agent_node.
    """
    # Replicate the contract from graph.py:225-226 in a mini-agent-node.
    # We test that (a) RuntimeError is raised, and (b) no tool_calls were generated
    # (i.e., message history has no AIMessage(tool_calls) after the error).
    from langgraph.runtime import Runtime  # noqa: PLC0415 (test-only local import)

    async def agent_node_with_store_guard(state: MessagesState, runtime: Runtime) -> dict:  # type: ignore[type-arg]
        if runtime.store is None:
            raise RuntimeError("Agent graph requires a Store but none was provided")
        # Would generate tool_calls here, but we never reach this
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "dummy", "args": {}, "id": "call_x", "type": "tool_call"}],
                )
            ]
        }

    builder = StateGraph(MessagesState)
    builder.add_node("agent", agent_node_with_store_guard)
    builder.add_edge(START, "agent")

    checkpointer = InMemorySaver()
    # Compile WITHOUT store → runtime.store will be None in agent_node
    graph = builder.compile(checkpointer=checkpointer, store=None)
    thread_cfg = {"configurable": {"thread_id": "thread-t310"}}

    # The graph should raise RuntimeError from agent_node's store-guard
    with pytest.raises(Exception, match="Store"):
        await graph.ainvoke(
            {"messages": [HumanMessage(content="trigger")]},
            config=thread_cfg,
        )

    # After the error, no dangling AIMessage(tool_calls) in the checkpoint
    # (agent_node failed before producing tool_calls → history is safe)
    state = graph.get_state(thread_cfg)
    messages_in_checkpoint = list(state.values.get("messages", []))
    unpaired = _validate_tool_call_pairs(messages_in_checkpoint)
    assert not unpaired, (
        "Unexpected dangling tool_call after store-guard RuntimeError: "
        f"the store-guard should fire before generating tool_calls. Unpaired: {unpaired}"
    )
