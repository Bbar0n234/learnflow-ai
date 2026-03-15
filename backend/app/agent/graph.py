from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, RemoveMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime

from app.agent.config import AgentConfig
from app.agent.prompt_builder import build_system_message
from app.agent.tools.ks_helpers import build_namespace, format_index

logger = logging.getLogger(__name__)


@dataclass
class AgentContext:
    project_id: str
    user_id: str


async def _summarize(model: BaseChatModel, messages: list[Any]) -> str:
    prompt = SystemMessage(
        content=(
            "Summarize the following conversation concisely. "
            "Preserve: key decisions, unresolved questions, current focus, "
            "important facts and context. "
            "Discard: redundant tool outputs, intermediate reasoning, greetings."
        )
    )
    response = await model.ainvoke([prompt, *messages])
    return str(response.content)


def build_graph(
    model: BaseChatModel,
    tools: list[Any],
    agent_config: AgentConfig,
    skills_index: str = "",
    summarization_model: BaseChatModel | None = None,
) -> StateGraph[Any, Any, Any, Any]:
    bound_model = model.bind_tools(tools)

    async def agent_node(state: MessagesState, runtime: Runtime[AgentContext]) -> dict:
        messages = state["messages"]
        result_prefix: list[Any] = []

        # 1. Compaction: summarize old messages if threshold exceeded
        total_tokens = count_tokens_approximately(messages)
        threshold = (
            agent_config.context.max_tokens
            * agent_config.context.compaction_threshold_ratio
        )

        if (
            summarization_model is not None
            and total_tokens > threshold
            and len(messages) > agent_config.context.recent_messages_to_keep
        ):
            keep_count = agent_config.context.recent_messages_to_keep
            old_messages = messages[:-keep_count]
            recent_messages = messages[-keep_count:]

            try:
                summary_text = await _summarize(summarization_model, old_messages)

                result_prefix = [
                    RemoveMessage(id=m.id) for m in old_messages if m.id is not None
                ]
                summary_msg = AIMessage(
                    content=f"[Previous conversation summary]\n{summary_text}"
                )
                result_prefix.append(summary_msg)

                messages = [summary_msg, *recent_messages]
            except Exception:
                logger.warning(
                    "Summarization failed, falling back to trim-only", exc_info=True
                )

        # 2. Build system message
        if runtime.store is None:
            raise RuntimeError("Agent graph requires a Store but none was provided")
        ns = build_namespace(runtime.context.project_id)
        items = await runtime.store.asearch(ns, limit=100)
        ks_index = format_index(list(items))

        content = build_system_message(
            based_prompt=agent_config.prompt.system_text,
            ks_index=ks_index,
            skills_index=skills_index,
        )
        system = SystemMessage(content=content)

        # 3. Trim messages
        trimmed = trim_messages(
            messages,
            strategy="last",
            token_counter=count_tokens_approximately,
            max_tokens=agent_config.context.max_tokens,
            start_on="human",
            end_on=("human", "tool"),
        )

        # 4. LLM call
        response = await bound_model.ainvoke([system, *trimmed])
        response.additional_kwargs["created_at"] = datetime.now(
            timezone.utc
        ).isoformat()
        return {"messages": [*result_prefix, response]}

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
