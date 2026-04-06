from __future__ import annotations

import contextlib
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
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
from app.infra.prompt_provider import PromptProvider

logger = structlog.get_logger()

_SUMMARIZATION_PROMPT = (
    "Summarize the following conversation concisely. "
    "Preserve: key decisions, unresolved questions, current focus, "
    "important facts and context. "
    "Discard: redundant tool outputs, intermediate reasoning, greetings."
)


@dataclass
class AgentContext:
    project_id: str
    user_id: str


async def _reduce_context(
    messages: list[Any],
    summarization_model: BaseChatModel,
    agent_config: AgentConfig,
    prompt_provider: PromptProvider | None,
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
        prompt_text = _SUMMARIZATION_PROMPT
        if prompt_provider:
            with contextlib.suppress(Exception):
                prompt_text = prompt_provider.get_prompt("summarization")

        prompt = SystemMessage(content=prompt_text)
        response = await summarization_model.ainvoke([prompt, *old_messages])
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


def _build_system_content(
    prompt_provider: PromptProvider | None,
    fallback_prompt: str,
    ks_index: str,
    skills_index: str,
    custom_instructions: str = "",
    user_memory_index: str = "",
) -> str:
    """Build system message content from prompt provider + context."""
    if prompt_provider:
        try:
            base_prompt = prompt_provider.get_prompt("system")
        except Exception:
            base_prompt = fallback_prompt
    else:
        base_prompt = fallback_prompt

    return build_system_message(
        based_prompt=base_prompt,
        ks_index=ks_index,
        skills_index=skills_index,
        custom_instructions=custom_instructions,
        user_memory_index=user_memory_index,
    )


async def _invoke_llm(
    bound_model: Any,
    messages: list[Any],
) -> tuple[Any, int]:
    """Invoke LLM and return (response, duration_ms)."""
    llm_start = time.monotonic()
    response = await bound_model.ainvoke(messages)
    duration_ms = int((time.monotonic() - llm_start) * 1000)

    usage = response.usage_metadata
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
    skills_index: str = "",
    summarization_model: BaseChatModel | None = None,
    prompt_provider: PromptProvider | None = None,
) -> StateGraph[Any, Any, Any, Any]:
    bound_model = model.bind_tools(tools)

    # File fallback for system prompt
    fallback_prompt = ""
    if prompt_provider:
        fallback_prompt = prompt_provider._load_file("system")

    async def agent_node(state: MessagesState, runtime: Runtime[AgentContext]) -> dict:
        messages = state["messages"]
        result_prefix: list[Any] = []

        # 1. Compaction
        if summarization_model is not None:
            messages, result_prefix = await _reduce_context(
                messages, summarization_model, agent_config, prompt_provider
            )

        # 2. Build system message
        if runtime.store is None:
            raise RuntimeError("Agent graph requires a Store but none was provided")
        ns = build_namespace(runtime.context.project_id)
        items = await runtime.store.asearch(ns, limit=100)
        ks_index = format_index(list(items))

        # Fetch custom instructions and user memory from store
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
            from app.agent.tools.store_helpers import format_index as fmt_index

            mem_items = await runtime.store.asearch(
                ("user", user_id, "memory"), limit=50
            )
            user_memory_index = fmt_index(list(mem_items), title="User Memory")
        except Exception:
            logger.warning("user memory fetch failed", user_id=user_id, exc_info=True)

        content = _build_system_content(
            prompt_provider=prompt_provider,
            fallback_prompt=fallback_prompt,
            ks_index=ks_index,
            skills_index=skills_index,
            custom_instructions=custom_instructions,
            user_memory_index=user_memory_index,
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

        # 4. LLM call
        response, _ = await _invoke_llm(bound_model, [system, *trimmed])
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
