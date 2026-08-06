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

from app.agent.agent_events import emit_agent_event
from app.agent.config import AgentConfig, PromptFragmentsConfig
from app.agent.prompt_builder import build_system_message, compose_for_llm
from app.agent.security.guard import SecurityGuard
from app.agent.security.types import SecurityMessages
from app.agent.stream_events import make_tool_result_reporter
from app.agent.tool_guards import (
    execute_tools_guarded,
    guard_tool_call_args,
    handle_tool_error,
)
from app.agent.tools.ks_helpers import build_namespace, format_index
from app.agent.tools.store_helpers import format_index as fmt_index
from app.agent.tracing import observe_compaction
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
        summarization_cfg = agent_config.summarization
        # Detaching the callbacks also detaches Langfuse (tracing rides the
        # LangChain handler), so the generation is recorded by hand — the same
        # compensation the guard classifier makes. Pricing is matched by model
        # name, so it is taken from the model object that answers the call.
        model_name = getattr(summarization_model, "model_name", None) or (
            summarization_cfg.model if summarization_cfg else None
        )
        with observe_compaction(
            input_payload=[
                {"role": m.type, "content": str(m.content)}
                for m in (prompt, *old_messages)
            ],
            model=model_name,
            model_parameters=(
                {"max_tokens": summarization_cfg.max_summary_tokens}
                if summarization_cfg
                else {}
            ),
            metadata={
                "messages_compacted": len(old_messages),
                "messages_kept": keep_count,
                "context_tokens_before": total_tokens,
            },
        ) as generation:
            response = await summarization_model.ainvoke(
                [prompt, *old_messages], config=summarization_config
            )
            summary_text = str(response.content)
            generation.record_summary(
                summary=summary_text, token_usage=extract_usage(response)
            )

        ops_prefix: list[Any] = [
            RemoveMessage(id=m.id) for m in old_messages if m.id is not None
        ]
        summary_msg = AIMessage(
            content=f"[Previous conversation summary]\n{summary_text}",
            # Marks the message as a context digest, not a turn of the
            # conversation: it feeds the model but must never reach the user —
            # ``CheckpointHistory.history`` drops it out of the API history by
            # this flag. Position can't be used instead: the message carries no
            # ``id``, so ``add_messages`` appends it to the *end* of the state
            # (next to the real answer), not in front of the thread.
            additional_kwargs={"context_summary": True},
        )
        ops_prefix.append(summary_msg)

        emit_agent_event("compaction", {})
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
        # No TOOL_RESULT pre-guard here: that check belongs to the ``tools``
        # node, whose output is what both the wire and the checkpoint see
        # (``execute_tools_guarded``). By the time a batch reaches this node it
        # is already checked.
        messages = state["messages"]
        result_prefix: list[Any] = []

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

    async def tools_node(state: MessagesState, runtime: Runtime[AgentContext]) -> Any:
        """``ToolNode`` + the TOOL_RESULT guard + the report, as one node named ``tools``.

        The node keeps its name because ``tools_condition`` (routing) and
        ``StreamEventMapper``'s pending-call ledger (``"tools" in data``)
        address it by that name.

        It also *reports* every result it checks, on this run's own writer —
        the same mechanism the subagent uses for its nested calls. That is not
        a detour around the updates channel but the only way to be timely: a
        node update reaches the runner when the node returns, i.e. when the
        slowest call of the turn is done, whereas the writer carries each
        result the instant its own call clears the guard.
        """
        return await execute_tools_guarded(
            tool_node,
            state,
            guard=security_guard,
            canary_token=runtime.context.canary_token,
            tool_result_stub=tool_result_stub,
            on_result=make_tool_result_reporter(runtime.stream_writer),
        )

    builder = StateGraph(MessagesState, context_schema=AgentContext)
    builder.add_node("agent", agent_node)
    builder.add_node("tools", tools_node)
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
