from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.utils import count_tokens_approximately, trim_messages
from langgraph.graph import START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.runtime import Runtime

from app.agent.config import AgentConfig, PromptFragmentsConfig
from app.agent.prompt_builder import build_system_message, compose_for_llm
from app.agent.security.guard import SecurityGuard
from app.agent.security.types import Checkpoint, SecurityMessages, Verdict
from app.agent.tools.ks_helpers import build_namespace, format_index
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


async def _guard_tool_results(
    messages: list[Any],
    guard: SecurityGuard,
    canary_token: str,
    tool_result_stub: str,
) -> list[ToolMessage]:
    """Scan the current batch of ToolMessages; return replace-by-id updates for injections."""
    if not messages:
        return []
    anchor = -1
    for i, m in enumerate(messages):
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            anchor = i
    if anchor < 0:
        return []
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
            tool_result_updates = await _guard_tool_results(
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
            from app.agent.tools.store_helpers import format_index as fmt_index

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
        response.additional_kwargs["created_at"] = datetime.now(
            timezone.utc
        ).isoformat()

        # 5. Post-guard: TOOL_CALL_ARG — check serialized tool_call args.
        if security_guard is not None and getattr(response, "tool_calls", None):
            args_payload = json.dumps(
                [tc.get("args", {}) for tc in response.tool_calls],
                ensure_ascii=False,
            )
            arg_result = await security_guard.check(
                args_payload,
                Checkpoint.TOOL_CALL_ARG,
                history=list(messages),
                canary_token=runtime.context.canary_token,
            )
            if arg_result.verdict == Verdict.INJECTION:
                redacted = AIMessage(
                    id=response.id,
                    content=response.content
                    if isinstance(response.content, str)
                    else "",
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
                            arg_result.detection_layer.value
                            if arg_result.detection_layer
                            else None
                        ),
                    },
                )
                return {"messages": [*result_prefix, redacted]}

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
