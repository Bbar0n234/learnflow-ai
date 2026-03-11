from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime

from app.agent.config import AgentConfig


@dataclass
class AgentContext:
    project_id: str
    user_id: str


def build_graph(
    model: BaseChatModel,
    tools: list[Any],
    agent_config: AgentConfig,
) -> StateGraph[Any, Any, Any, Any]:
    bound_model = model.bind_tools(tools)

    async def agent_node(state: MessagesState, runtime: Runtime[AgentContext]) -> dict:
        system = SystemMessage(content=agent_config.prompt.system)

        trimmed = trim_messages(
            state["messages"],
            strategy="last",
            token_counter=count_tokens_approximately,
            max_tokens=agent_config.context.max_tokens,
            start_on="human",
            end_on=("human", "tool"),
        )

        response = await bound_model.ainvoke([system, *trimmed])
        return {"messages": [response]}

    tool_node = ToolNode(tools)

    builder = StateGraph(MessagesState, context_schema=AgentContext)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tool_node)
    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", tools_condition)
    builder.add_edge("tools", "agent")
    return builder


def compile_graph(
    builder: StateGraph[Any, Any, Any, Any],
    *,
    checkpointer: Any,
    store: Any,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    return builder.compile(checkpointer=checkpointer, store=store)
