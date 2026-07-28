"""Probe (T1.1): does streamed ``reasoning`` survive to the checkpointed AIMessage?

Design-brief входной факт #2 established this at the library level:
``AIMessageChunk`` merge concatenates ``additional_kwargs["reasoning"]``
(string values are summed, see ``langchain_core.utils._merge.merge_dicts``),
and ``message_chunk_to_message`` copies ``additional_kwargs`` verbatim onto the
final ``AIMessage``. What library mechanics alone don't prove is that the
project's *actual* accumulation path — the agent node's plain ``ainvoke``,
forced onto the streaming code path by ``graph.astream(...,
stream_mode=["messages"])`` (the shape the runner drives in production) —
carries the reasoning through into what a *real* checkpointer persists.

This test drives that exact path (real ``build_graph``/``compile_graph``, a
fresh ``InMemorySaver`` — the project's standard fake for checkpointer-backed
graph tests, see testing.md's checkpointer row) with a fake model that streams
per-chunk reasoning deltas the way ``ReasoningChatOpenAI`` does, then reads the
persisted message back the same way ``CheckpointHistory.raw_messages`` does:
``channel_values["messages"]`` off ``aget_tuple``.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.agent.graph import AgentContext
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from tests.agent.conftest import reasoning_streaming_fake


def _thread_config() -> RunnableConfig:
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


@pytest.mark.unit
async def test_reasoning_survives_streaming_accumulation_to_checkpoint(
    build_compiled_graph: Any,
    agent_context: AgentContext,
    checkpointer: InMemorySaver,
) -> None:
    model = reasoning_streaming_fake(
        [
            AIMessage(
                content="final answer",
                additional_kwargs={"reasoning": "step one step two"},
            )
        ]
    )
    graph = build_compiled_graph(model)
    config = _thread_config()

    async for _mode, _data in graph.astream(
        {"messages": [HumanMessage(content="hi")]},
        config,
        stream_mode=["messages"],
        context=agent_context,
    ):
        pass

    checkpoint = await checkpointer.aget_tuple(config)
    assert checkpoint is not None
    messages = checkpoint.checkpoint["channel_values"]["messages"]
    ai_messages = [m for m in messages if isinstance(m, AIMessage)]
    assert ai_messages, "no AIMessage persisted to the checkpoint"
    final = ai_messages[-1]

    assert final.content == "final answer"
    assert final.additional_kwargs.get("reasoning") == "step one step two"
