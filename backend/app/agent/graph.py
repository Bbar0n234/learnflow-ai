from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    RemoveMessage,
    SystemMessage,
)
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langchain_core.runnables import RunnableConfig
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime

from app.agent.config import AgentConfig, PromptFragmentsConfig
from app.agent.prompt_builder import build_system_message, compose_for_llm
from app.agent.security.guard import SecurityGuard
from app.agent.security.types import SecurityMessages
from app.agent.tool_guards import (
    guard_tool_call_args,
    guard_tool_results,
    handle_tool_error,
)
from app.agent.tools.ks_helpers import build_namespace, format_index
from app.agent.tools.store_helpers import format_index as fmt_index
from app.infra.llm import extract_usage
from app.infra.prompt_provider import PromptProvider

logger = structlog.get_logger()


@dataclass
class AgentContext:
    project_id: str
    user_id: str
    canary_token: str = ""
    user_installed_tool_names: frozenset[str] = frozenset()


async def _reduce_context(
    messages: list[Any],
    summarization_model: BaseChatModel,
    agent_config: AgentConfig,
    prompt_provider: PromptProvider,
) -> tuple[list[Any], list[Any]]:
    """Compact old messages via summarization + return (remaining_messages, ops_prefix)."""
    total_tokens = count_tokens_approximately(messages)
    threshold = (
        agent_config.context.max_tokens
        * agent_config.context.compaction_threshold_ratio
    )

    if (
        total_tokens <= threshold
        or len(messages) <= agent_config.context.recent_messages_to_keep
    ):
        return messages, []

    keep_count = agent_config.context.recent_messages_to_keep
    old_messages = messages[:-keep_count]
    recent_messages = messages[-keep_count:]

    try:
        prompt_text = prompt_provider.get_prompt("summarization")
        prompt = SystemMessage(content=prompt_text)
        # Detach from the parent runnable's callback chain, same as the guard
        # classifier (security/classifier.py): keeps compaction generations out
        # of ``stream_mode="messages"`` so its tokens don't leak into the
        # user-facing text_chunk stream (event-map.md попутная находка №1).
        summarization_config: RunnableConfig = {
            "callbacks": [],
            "tags": ["context_summarization"],
            "run_name": "context-summarization",
        }
        response = await summarization_model.ainvoke(
            [prompt, *old_messages], config=summarization_config
        )
        summary_text = str(response.content)

        ops_prefix: list[Any] = [
            RemoveMessage(id=m.id) for m in old_messages if m.id is not None
        ]
        summary_msg = AIMessage(
            content=f"[Previous conversation summary]\n{summary_text}"
        )
        ops_prefix.append(summary_msg)

        return [summary_msg, *recent_messages], ops_prefix
    except Exception:
        logger.warning("summarization failed, falling back to trim-only", exc_info=True)
        return messages, []


async def _invoke_llm(
    bound_model: Any,
    messages: list[Any],
) -> tuple[Any, int]:
    """Invoke LLM and return (response, duration_ms)."""
    llm_start = time.monotonic()
    response = await bound_model.ainvoke(messages)
    duration_ms = int((time.monotonic() - llm_start) * 1000)

    usage = extract_usage(response)
    logger.info(
        "llm call",
        model=getattr(bound_model, "model_name", "unknown"),
        duration_ms=duration_ms,
        input_tokens=usage.get("input_tokens") if usage else None,
        output_tokens=usage.get("output_tokens") if usage else None,
    )

    return response, duration_ms


def build_graph(
    model: BaseChatModel,
    tools: list[Any],
    agent_config: AgentConfig,
    prompt_fragments: PromptFragmentsConfig,
    security_messages: SecurityMessages,
    skills_index: str = "",
    summarization_model: BaseChatModel | None = None,
    prompt_provider: PromptProvider | None = None,
    security_guard: SecurityGuard | None = None,
) -> StateGraph[Any, Any, Any, Any]:
    bound_model = model.bind_tools(tools)
    tool_result_stub = security_messages.redacted_tool_result

    # Map tool name -> description for MCP user-installed section rendering.
    tools_by_name: dict[str, str] = {}
    for t in tools:
        name = getattr(t, "name", None)
        if not name:
            continue
        tools_by_name[name] = getattr(t, "description", "") or ""

    async def agent_node(state: MessagesState, runtime: Runtime[AgentContext]) -> dict:
        messages = state["messages"]
        result_prefix: list[Any] = []

        # 0. Pre-guard: TOOL_RESULT on any ToolMessage from the current batch
        #    (after the last HumanMessage / last AIMessage that issued tool_calls).
        if security_guard is not None:
            tool_result_updates = await guard_tool_results(
                messages,
                security_guard,
                runtime.context.canary_token,
                tool_result_stub,
            )
            if tool_result_updates:
                result_prefix.extend(tool_result_updates)
                by_id: dict[str, Any] = {
                    m.id: m for m in tool_result_updates if m.id is not None
                }
                messages = [
                    by_id.get(m.id, m) if m.id is not None else m for m in messages
                ]

        # 1. Compaction
        if summarization_model is not None and prompt_provider is not None:
            messages, result_prefix_compaction = await _reduce_context(
                messages, summarization_model, agent_config, prompt_provider
            )
            result_prefix = result_prefix + result_prefix_compaction

        # 2. Build system message
        if runtime.store is None:
            raise RuntimeError("Agent graph requires a Store but none was provided")
        ns = build_namespace(runtime.context.project_id)
        items = await runtime.store.asearch(ns, limit=100)
        ks_index = format_index(list(items))

        custom_instructions = ""
        user_memory_index = ""
        user_id = runtime.context.user_id
        try:
            instr_item = await runtime.store.aget(
                ("user", user_id, "instructions"), "default"
            )
            if instr_item:
                custom_instructions = instr_item.value.get("content", "")
        except Exception:
            logger.warning(
                "custom instructions fetch failed", user_id=user_id, exc_info=True
            )

        try:
            mem_items = await runtime.store.asearch(
                ("user", user_id, "memory"), limit=50
            )
            user_memory_index = fmt_index(list(mem_items), title="User Memory")
        except Exception:
            logger.warning("user memory fetch failed", user_id=user_id, exc_info=True)

        user_installed_mcp_tools: list[dict[str, str]] = []
        for tool_name in runtime.context.user_installed_tool_names:
            description = tools_by_name.get(tool_name, "")
            user_installed_mcp_tools.append(
                {"name": tool_name, "description": description}
            )

        content = build_system_message(
            prompt_provider,
            prompt_fragments,
            ks_index=ks_index,
            skills_index=skills_index,
            custom_instructions=custom_instructions,
            user_memory_index=user_memory_index,
            canary_token=runtime.context.canary_token,
            user_installed_mcp_tools=user_installed_mcp_tools,
        )
        system = SystemMessage(content=content)

        logger.debug(
            "agent state",
            message_count=len(messages),
            total_tokens=count_tokens_approximately(messages),
        )

        # 3. Trim messages
        trimmed = trim_messages(
            messages,
            strategy="last",
            token_counter=count_tokens_approximately,
            max_tokens=agent_config.context.max_tokens,
            start_on="human",
            end_on=("human", "tool"),
        )

        # 4. Compose for LLM (trust-boundary wrapping) and invoke
        llm_messages = compose_for_llm(trimmed, prompt_fragments)
        response, _ = await _invoke_llm(bound_model, [system, *llm_messages])
        response.additional_kwargs["created_at"] = datetime.now(UTC).isoformat()

        # 5. Post-guard: TOOL_CALL_ARG — check serialized tool_call args.
        if security_guard is not None:
            response = await guard_tool_call_args(
                response, security_guard, runtime.context.canary_token, list(messages)
            )

        return {"messages": [*result_prefix, response]}

    tool_node = ToolNode(tools, handle_tool_errors=handle_tool_error)

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
