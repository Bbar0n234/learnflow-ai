"""Unit: the agent graph on a fake model — nodes, edges, routing, ReAct, guard.

The graph is driven deterministically by a programmed ``GenericFakeChatModel``
(``tool_binding_fake``) plus an in-memory checkpointer + store (official LangGraph
test pattern: fresh checkpointer per test). We assert observable behavior — the
message list a turn produces, the routing taken, the redaction applied — through
the public ``ainvoke``/``astream``/``aget_state`` surface, never private nodes.

Guard branches use stub guards returning a chosen ``Verdict`` per checkpoint:
the test proves *our code reacts* to the verdict (redaction, pass-through), not
the quality of the verdict (that is eval, see testing.md § Граница unit / eval).
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.agent.graph import AgentContext
from app.agent.security.types import (
    Checkpoint,
    Direction,
    GuardResult,
    SecurityMessages,
    Verdict,
)
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from tests.agent.conftest import RaisingFakeChatModel, tool_binding_fake


def _thread_config() -> dict[str, Any]:
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


@tool
def echo(text: str) -> str:
    """Echo the given text back."""
    return f"echoed: {text}"


@tool
def boom(text: str) -> str:
    """A tool that always fails (used to exercise error handling)."""
    raise RuntimeError("upstream failure with /var/secrets/key.pem path")


class _SelectiveGuard:
    """Stub guard returning a per-checkpoint verdict; records the checkpoints seen.

    Lets a test allow tool-call args through (CLEAN) while flagging the tool
    result (INJECTION), isolating the TOOL_RESULT redaction branch.
    """

    def __init__(self, verdicts: dict[Checkpoint, Verdict]) -> None:
        self._verdicts = verdicts
        self.checkpoints: list[Checkpoint] = []

    async def check(
        self, content: str, checkpoint: Checkpoint, **kwargs: Any
    ) -> GuardResult:
        self.checkpoints.append(checkpoint)
        return GuardResult(
            verdict=self._verdicts.get(checkpoint, Verdict.CLEAN),
            checkpoint=checkpoint,
            direction=Direction.INBOUND,
        )


# --- structure / wiring -----------------------------------------------------


@pytest.mark.unit
def test_graph_exposes_agent_and_tools_nodes(build_compiled_graph: Any) -> None:
    graph = build_compiled_graph(tool_binding_fake([AIMessage(content="hi")]))

    assert {"agent", "tools"} <= set(graph.nodes)


# --- happy path / routing ---------------------------------------------------


@pytest.mark.unit
async def test_agent_reply_without_tool_calls_routes_to_end(
    build_compiled_graph: Any, agent_context: AgentContext
) -> None:
    graph = build_compiled_graph(tool_binding_fake([AIMessage(content="final answer")]))

    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="hello")]},
        _thread_config(),
        context=agent_context,
    )

    assert [type(m).__name__ for m in out["messages"]] == [
        "HumanMessage",
        "AIMessage",
    ]
    assert out["messages"][-1].content == "final answer"


@pytest.mark.unit
async def test_tool_call_routes_through_tools_then_back_to_agent(
    build_compiled_graph: Any, agent_context: AgentContext
) -> None:
    model = tool_binding_fake(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "c1"}],
            ),
            AIMessage(content="done"),
        ]
    )
    graph = build_compiled_graph(model, tools=[echo])

    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="use the tool")]},
        _thread_config(),
        context=agent_context,
    )

    # Full ReAct accumulation: human -> ai(tool_call) -> tool -> ai(final).
    assert [type(m).__name__ for m in out["messages"]] == [
        "HumanMessage",
        "AIMessage",
        "ToolMessage",
        "AIMessage",
    ]
    tool_msg = out["messages"][2]
    assert tool_msg.content == "echoed: hi"
    assert out["messages"][-1].content == "done"


@pytest.mark.unit
async def test_response_is_stamped_with_created_at(
    build_compiled_graph: Any, agent_context: AgentContext
) -> None:
    graph = build_compiled_graph(tool_binding_fake([AIMessage(content="hi")]))

    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="hello")]},
        _thread_config(),
        context=agent_context,
    )

    assert "created_at" in out["messages"][-1].additional_kwargs


# --- tool error handling ----------------------------------------------------


@pytest.mark.unit
async def test_tool_failure_yields_safe_message_without_leaking_internals(
    build_compiled_graph: Any, agent_context: AgentContext
) -> None:
    model = tool_binding_fake(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "boom", "args": {"text": "x"}, "id": "c1"}],
            ),
            AIMessage(content="recovered"),
        ]
    )
    graph = build_compiled_graph(model, tools=[boom])

    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")]},
        _thread_config(),
        context=agent_context,
    )

    tool_msg = next(m for m in out["messages"] if isinstance(m, ToolMessage))
    assert tool_msg.status == "error"
    assert "/var/secrets" not in tool_msg.content
    assert "Tool execution failed" in tool_msg.content


# --- security guard branches ------------------------------------------------


@pytest.mark.unit
async def test_guard_injection_on_tool_call_args_strips_tool_calls(
    build_compiled_graph: Any, agent_context: AgentContext
) -> None:
    model = tool_binding_fake(
        [
            AIMessage(
                content="answer",
                tool_calls=[{"name": "echo", "args": {"text": "bad"}, "id": "c1"}],
            )
        ]
    )
    guard = _SelectiveGuard({Checkpoint.TOOL_CALL_ARG: Verdict.INJECTION})
    graph = build_compiled_graph(model, tools=[echo], security_guard=guard)

    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")]},
        _thread_config(),
        context=agent_context,
    )

    last = out["messages"][-1]
    assert isinstance(last, AIMessage)
    assert last.tool_calls == []  # stripped -> routes to END, tools never run
    assert last.additional_kwargs.get("security_redacted") is True
    assert Checkpoint.TOOL_CALL_ARG in guard.checkpoints


@pytest.mark.unit
async def test_guard_clean_lets_tool_calls_execute(
    build_compiled_graph: Any, agent_context: AgentContext
) -> None:
    model = tool_binding_fake(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "echo", "args": {"text": "ok"}, "id": "c1"}],
            ),
            AIMessage(content="done"),
        ]
    )
    guard = _SelectiveGuard({})  # everything CLEAN
    graph = build_compiled_graph(model, tools=[echo], security_guard=guard)

    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")]},
        _thread_config(),
        context=agent_context,
    )

    assert any(isinstance(m, ToolMessage) for m in out["messages"])
    assert out["messages"][-1].content == "done"


@pytest.mark.unit
async def test_guard_injection_on_tool_result_redacts_tool_message(
    build_compiled_graph: Any, agent_context: AgentContext
) -> None:
    # Args pass (CLEAN) so the tool runs; the returned result is flagged INJECTION
    # on re-entry and redacted to the safe stub.
    model = tool_binding_fake(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "echo", "args": {"text": "ok"}, "id": "c1"}],
            ),
            AIMessage(content="final"),
        ]
    )
    guard = _SelectiveGuard({Checkpoint.TOOL_RESULT: Verdict.INJECTION})
    graph = build_compiled_graph(model, tools=[echo], security_guard=guard)

    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")]},
        _thread_config(),
        context=agent_context,
    )

    tool_msg = next(m for m in out["messages"] if isinstance(m, ToolMessage))
    assert tool_msg.content == SecurityMessages().redacted_tool_result
    assert tool_msg.additional_kwargs.get("security_redacted") is True
    assert Checkpoint.TOOL_RESULT in guard.checkpoints


# --- HITL: interrupt + resume + partial run ---------------------------------


@pytest.mark.unit
async def test_interrupt_after_agent_pauses_before_tools(
    build_compiled_graph: Any, agent_context: AgentContext
) -> None:
    model = tool_binding_fake(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "c1"}],
            ),
            AIMessage(content="final"),
        ]
    )
    graph = build_compiled_graph(model, tools=[echo], interrupt_after=["agent"])
    config = _thread_config()

    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="go")]}, config, context=agent_context
    )
    snapshot = await graph.aget_state(config)

    # Paused: tool_call emitted but the tools node has not run yet.
    assert snapshot.next == ("tools",)
    assert not any(isinstance(m, ToolMessage) for m in out["messages"])


@pytest.mark.unit
async def test_resume_after_interrupt_completes_react_loop(
    build_compiled_graph: Any, agent_context: AgentContext
) -> None:
    model = tool_binding_fake(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "echo", "args": {"text": "hi"}, "id": "c1"}],
            ),
            AIMessage(content="final"),
        ]
    )
    graph = build_compiled_graph(model, tools=[echo], interrupt_after=["agent"])
    config = _thread_config()
    await graph.ainvoke(
        {"messages": [HumanMessage(content="go")]}, config, context=agent_context
    )

    resumed = await graph.ainvoke(None, config, context=agent_context)

    assert [type(m).__name__ for m in resumed["messages"]] == [
        "HumanMessage",
        "AIMessage",
        "ToolMessage",
        "AIMessage",
    ]
    assert resumed["messages"][-1].content == "final"


@pytest.mark.unit
async def test_update_state_as_node_seeds_messages_then_runs_tools(
    build_compiled_graph: Any, agent_context: AgentContext
) -> None:
    # Inject an assistant tool_call "as if" the agent node produced it, then let
    # the graph continue from the tools node (partial-run pattern).
    model = tool_binding_fake([AIMessage(content="after tool")])
    graph = build_compiled_graph(model, tools=[echo], interrupt_after=["agent"])
    config = _thread_config()

    await graph.aupdate_state(
        config,
        {
            "messages": [
                HumanMessage(content="seed"),
                AIMessage(
                    content="",
                    tool_calls=[{"name": "echo", "args": {"text": "z"}, "id": "c1"}],
                ),
            ]
        },
        as_node="agent",
    )
    out = await graph.ainvoke(None, config, context=agent_context)

    assert any(
        isinstance(m, ToolMessage) and m.content == "echoed: z" for m in out["messages"]
    )
    assert out["messages"][-1].content == "after tool"


# --- negative: model failure ------------------------------------------------


@pytest.mark.unit
async def test_model_failure_propagates_out_of_graph(
    build_compiled_graph: Any, agent_context: AgentContext
) -> None:
    model = RaisingFakeChatModel(messages=iter([AIMessage(content="never")]))
    graph = build_compiled_graph(model)

    with pytest.raises(RuntimeError, match="simulated upstream connection failure"):
        await graph.ainvoke(
            {"messages": [HumanMessage(content="hi")]},
            _thread_config(),
            context=agent_context,
        )
