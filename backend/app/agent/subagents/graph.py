"""Subagent graph builder (subagent-as-tool engine).

Two forms, selected by whether the spec resolves any ``tools``:

- **Toolless form** (T1.2 — ``judge``, ``general-purpose``): a single LLM
  node, ``START -> llm -> END``. No internal guard checks — there is no
  untrusted-tool-result surface, and the input was already checked at the
  main graph's boundary (design-brief § "Безопасность": "toolless-субагенты
  внутренних проверок не требуют").
- **Tools form / ReAct cycle** (T1.5 — ``web-research``): ``START -> llm ->
  (tools_condition) -> tools -> llm -> ... -> END``, the same
  ``ToolNode``/``tools_condition``/``handle_tool_errors`` building blocks as
  the main graph (``app.agent.graph.build_graph``), reused rather than
  reimplemented. The loop is bounded by ``recursion_limit`` (set by the
  caller — see ``SubagentRunner.run``), not here: it is invoke-time
  ``RunnableConfig``, not a compile-time or graph-construction concern.

Both forms share the system message contract: *only* the spec's own prompt —
no KS/user-memory/skills/compaction sections, no ``compose_for_llm``
trust-boundary wrapping — context cleanliness is the whole point of a
subagent (see design-brief § "Слоистость"). Subagent tool descriptions are
never rendered into the prompt (unlike the main graph's
user-installed-MCP section) — the model sees them the ordinary way, through
``bind_tools``.
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from app.agent.security.guard import SecurityGuard
from app.agent.tool_guards import (
    guard_tool_call_args,
    guard_tool_results,
    handle_tool_error,
)


def _build_toolless_graph(
    model: BaseChatModel,
    system_prompt: str,
    max_tokens: int,
) -> StateGraph[Any, Any, Any, Any]:
    """One-shot LLM node, no tools, no guard (see module docstring)."""

    async def llm_node(state: MessagesState) -> dict[str, list[BaseMessage]]:
        # Safety net for oversized inputs (e.g. a large injected document) —
        # not a compaction step: subagents get no summarization pass, by
        # design (clean-context invariant).
        trimmed = trim_messages(
            state["messages"],
            strategy="last",
            token_counter=count_tokens_approximately,
            max_tokens=max_tokens,
            start_on="human",
            end_on="human",
        )
        system = SystemMessage(content=system_prompt)
        response = await model.ainvoke([system, *trimmed])
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("llm", llm_node)
    builder.add_edge(START, "llm")
    builder.add_edge("llm", END)
    return builder


def _build_react_graph(
    model: BaseChatModel,
    system_prompt: str,
    tools: list[BaseTool],
    max_tokens: int,
    security_guard: SecurityGuard | None,
    canary_token: str,
    tool_result_stub: str,
) -> StateGraph[Any, Any, Any, Any]:
    """ReAct cycle with the main graph's guard checks reused verbatim.

    Same fail-safe redact semantics as ``app.agent.graph.agent_node``: a
    poisoned tool result is swapped for ``tool_result_stub`` and the cycle
    continues (``guard_tool_results``); an injected tool-call arg strips
    ``tool_calls`` from the response so the next ``tools_condition`` routes
    to END instead of the tools node (``guard_tool_call_args``). Both are
    no-ops when ``security_guard`` is ``None`` — consistent with the main
    graph, which also skips both checks in that case (guard disabled
    globally).
    """
    bound_model = model.bind_tools(tools)

    async def llm_node(state: MessagesState) -> dict[str, list[BaseMessage]]:
        messages = state["messages"]
        result_prefix: list[Any] = []

        if security_guard is not None:
            tool_result_updates = await guard_tool_results(
                messages, security_guard, canary_token, tool_result_stub
            )
            if tool_result_updates:
                result_prefix.extend(tool_result_updates)
                by_id: dict[str, Any] = {
                    m.id: m for m in tool_result_updates if m.id is not None
                }
                messages = [
                    by_id.get(m.id, m) if m.id is not None else m for m in messages
                ]

        # Safety net for oversized tool results (e.g. a large scraped page) —
        # not a compaction step, same invariant as the toolless form.
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

        return {"messages": [*result_prefix, response]}

    tool_node = ToolNode(tools, handle_tool_errors=handle_tool_error)

    builder = StateGraph(MessagesState)
    builder.add_node("llm", llm_node)
    builder.add_node("tools", tool_node)
    builder.add_edge(START, "llm")
    builder.add_conditional_edges("llm", tools_condition)
    builder.add_edge("tools", "llm")
    return builder


def build_subagent_graph(
    model: BaseChatModel,
    system_prompt: str,
    tools: list[BaseTool],
    max_tokens: int,
    *,
    security_guard: SecurityGuard | None = None,
    canary_token: str = "",
    tool_result_stub: str = "",
) -> StateGraph[Any, Any, Any, Any]:
    """Build a subagent ``StateGraph``.

    Empty ``tools`` -> toolless one-node form (``judge``, ``general-purpose``).
    Non-empty ``tools`` -> ReAct cycle (``web-research``), with
    ``security_guard`` reused for in-cycle ``TOOL_RESULT``/``TOOL_CALL_ARG``
    checks. ``security_guard``/``canary_token``/``tool_result_stub`` are
    unused in the toolless branch (no guard there by design) and may be left
    at their defaults for those specs.
    """
    if not tools:
        return _build_toolless_graph(model, system_prompt, max_tokens)
    return _build_react_graph(
        model,
        system_prompt,
        tools,
        max_tokens,
        security_guard,
        canary_token,
        tool_result_stub,
    )


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
