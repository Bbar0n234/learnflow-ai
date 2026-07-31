"""Subagent graph builder (subagent-as-tool engine).

Every subagent is a ReAct agent: ``START -> llm -> (tools_condition) ->
tools -> llm -> ... -> END``, built from the same ``ToolNode``/
``tools_condition``/``handle_tool_errors`` building blocks as the main graph
(``app.agent.graph.build_graph``), reused rather than reimplemented. There is
no separate "toolless" form — a run in which the model never emits a tool
call simply ends after one super-step (``tools_condition`` routes to END);
that is a degenerate case of the same graph, not a distinct graph shape.
Every spec resolves a non-empty ``tools`` list — enforced at boot by
``app.main._validate_subagent_tool_pool``, so ``bind_tools`` never sees an
empty list (which OpenAI-compatible APIs reject).

The loop is bounded by ``recursion_limit`` (set by the caller — see
``SubagentRunner.run``), not here: it is invoke-time ``RunnableConfig``, not
a compile-time or graph-construction concern.

System message contract: *only* the spec's own prompt — no
KS/user-memory/skills/compaction sections, no ``compose_for_llm``
trust-boundary wrapping — context cleanliness is the whole point of a
subagent (see design-brief § "Слоистость"). Subagent tool descriptions are
never rendered into the prompt (unlike the main graph's
user-installed-MCP section) — the model sees them the ordinary way, through
``bind_tools``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langchain_core.tools import BaseTool
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.security.guard import SecurityGuard
from app.agent.tool_guards import (
    execute_tools_guarded,
    guard_tool_call_args,
    handle_tool_error,
)


def build_subagent_graph(
    model: BaseChatModel,
    system_prompt: str,
    tools: list[BaseTool],
    max_tokens: int,
    *,
    security_guard: SecurityGuard | None = None,
    canary_token: str = "",
    tool_result_stub: str = "",
    report_tool_results: Callable[[list[ToolMessage]], None] | None = None,
) -> StateGraph[Any, Any, Any, Any]:
    """Build the subagent ReAct ``StateGraph``.

    In-cycle guard checks reuse the main graph's fail-safe redact semantics
    (``app.agent.tool_guards``): a poisoned tool result is swapped for
    ``tool_result_stub`` and the cycle continues (``execute_tools_guarded``,
    inside the tools node); an injected tool-call arg strips ``tool_calls``
    from the response so the next ``tools_condition`` routes to END instead of
    the tools node (``guard_tool_call_args``). Both checks are skipped when
    ``security_guard`` is ``None`` — consistent with the main graph, which
    also skips both in that case (guard disabled globally).

    ``report_tool_results`` is called with the checked batch every time the
    tools node runs — the hook ``SubagentRunner`` uses to put nested
    ``tool_result`` events on the parent stream. It hangs off this node rather
    than off the tool proxy so that what reaches the user is the same text the
    guard cleared, never the raw one (streaming.md § «Вложенность субагента»).
    """
    bound_model = model.bind_tools(tools)

    async def llm_node(state: MessagesState) -> dict[str, list[BaseMessage]]:
        messages = state["messages"]

        # Safety net for oversized inputs (a large injected document, a large
        # scraped page) — not a compaction step: subagents get no
        # summarization pass, by design (clean-context invariant).
        trimmed = trim_messages(
            messages,
            strategy="last",
            token_counter=count_tokens_approximately,
            max_tokens=max_tokens,
            start_on="human",
            end_on=("human", "tool"),
        )
        system = SystemMessage(content=system_prompt)
        response = await bound_model.ainvoke([system, *trimmed])

        if security_guard is not None:
            response = await guard_tool_call_args(
                response, security_guard, canary_token, list(messages)
            )

        return {"messages": [response]}

    tool_node = ToolNode(tools, handle_tool_errors=handle_tool_error)

    async def tools_node(state: MessagesState) -> Any:
        return await execute_tools_guarded(
            tool_node,
            state,
            guard=security_guard,
            canary_token=canary_token,
            tool_result_stub=tool_result_stub,
            on_results=report_tool_results,
        )

    builder = StateGraph(MessagesState)
    builder.add_node("llm", llm_node)
    builder.add_node("tools", tools_node)
    builder.add_edge(START, "llm")
    builder.add_conditional_edges("llm", tools_condition)
    builder.add_edge("tools", "llm")
    return builder


def compile_subagent_graph(
    builder: StateGraph[Any, Any, Any, Any],
    *,
    checkpointer: Any,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Compile per-invoke.

    ``checkpointer=False`` (``persistence: none``, v1 default for all specs)
    disables checkpoint inheritance — zero writes to PG. ``checkpointer=None``
    (``persistence: inherit``) makes the subgraph inherit the parent's PG
    checkpointer instead (checkpoints land in the same thread under a
    separate ``checkpoint_ns``); not exercised by any v1 spec.
    """
    return builder.compile(checkpointer=checkpointer)
