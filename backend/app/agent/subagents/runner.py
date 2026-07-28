"""SubagentRunner — the subagent-as-tool execution core.

Resolves a ``SubagentSpec`` by ``agent_type``, builds the model + prompt for
it, assembles the input (``task`` + attributed documents), compiles the
subagent graph per invocation, and runs it. The ``run_subagent`` tool (T1.3)
is a thin wrapper around this class: fetching artifacts by
``input_artifact_ids`` and mapping errors into tool-visible strings both live
there, not here — this module raises plain exceptions.

T1.6 adds ``_LifecycleEmittingTool``: when the caller (the ``run_subagent``
tool, executing inside the main graph) hands over its own stream writer and
``call_id``, every tool resolved for the subagent's ``ToolNode`` is wrapped
so its execution reports the same four events the main agent's own tool
calls report — see the class docstring and design-brief § "Вложенность
субагента".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

import structlog
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.types import StreamWriter

from app.agent.agent_events import SUBAGENT_PARENT_CALL_ID, SUBAGENT_STREAM_WRITER
from app.agent.config import (
    AgentConfig,
    PromptFragmentsConfig,
    ResolvedModelConfig,
    SubagentSpec,
)
from app.agent.security.guard import SecurityGuard
from app.agent.security.types import SecurityMessages
from app.agent.subagents.graph import build_subagent_graph, compile_subagent_graph
from app.agent.text_limits import truncate
from app.config import Settings
from app.infra.llm import create_llm_from_config
from app.infra.prompt_provider import PromptProvider

logger = structlog.get_logger()

# The tool that will call this Runner (T1.3). Excluded from the subagent tool
# pool unconditionally — recursion is prevented at this layer regardless of
# what a spec's ``tools`` list says.
RUN_SUBAGENT_TOOL_NAME: Final = "run_subagent"

# Tag stamped on every subagent ``ainvoke`` call. ``LangGraphAgentRunner``'s
# stream loop (backend/app/agent/runner.py) filters ``stream_mode="messages"``
# chunks carrying this tag before they reach full_response/canary checks —
# see design-brief § "Стриминг: изоляция токенов субагента".
SUBAGENT_TAG: Final = "subagent"


@dataclass
class SubagentDocument:
    """One input document injected into the subagent's ``HumanMessage``.

    ``id``/``title`` feed the ``document`` XML-wrapper placeholders in
    ``configs/prompt_fragments.yaml`` (attribution so a judge verdict can
    cite a specific document); ``content`` is injected byte-for-byte — the
    tool fetches it from ``ArtifactRepository``, the Runner does not touch
    persistence.
    """

    id: str
    title: str
    content: str


class UnknownSubagentTypeError(Exception):
    """``agent_type`` does not match any spec in the registry.

    Carries ``available_types`` so the calling tool (T1.3) can report the
    valid options back to the model without re-deriving them.
    """

    def __init__(self, agent_type: str, available_types: list[str]) -> None:
        self.agent_type = agent_type
        self.available_types = available_types
        types_text = ", ".join(available_types) if available_types else "(none)"
        super().__init__(
            f"Unknown subagent type '{agent_type}'. Available types: {types_text}"
        )


def _escape_attr(value: str) -> str:
    """Escape ``"`` so a value cannot break out of a quoted XML attribute."""
    return value.replace('"', "&quot;")


class _LifecycleEmittingTool(BaseTool):
    """Proxies a subagent tool, reporting its execution as four wire events.

    A thin ``BaseTool`` proxy, not a reimplementation: ``name``/
    ``description``/``args_schema`` are copied from ``wrapped_tool`` so
    ``bind_tools`` (schema shown to the subagent's LLM) and the subagent's
    ``ToolNode`` (name-based lookup) see the same tool the spec declared.
    Execution itself is delegated verbatim to ``wrapped_tool.ainvoke`` — this
    class never touches ``_run``/``_arun``, so whatever the real tool does
    with ``response_format``/``return_direct``/artifacts keeps working
    unchanged; abstract ``_run`` is stubbed only to satisfy ``BaseTool``.

    ``tool_call_started``/``tool_call_args`` fire before the call: unlike the
    main agent (whose args are assembled fragment-by-fragment from
    ``tool_call_chunks``), the subagent's ``ToolNode`` hands over the already
    fully-parsed args dict up front, so both are known immediately.
    ``tool_result`` fires after, success or failure — ``status``/``content``
    reflect whichever happened. All three go straight to ``stream_writer``
    tagged with ``parent_call_id``, wire-shaped exactly like the runner's
    ``custom``-channel passthrough expects (``app.agent.runner``, "Lifecycle
    types ... passed through unchanged").

    Around the call, ``SUBAGENT_STREAM_WRITER``/``SUBAGENT_PARENT_CALL_ID``
    are set so a nested domain tool (``sphere_write``/``memory_write``/
    ``skill_context_write``) calling ``emit_agent_event`` from *inside* the
    wrapped tool still reaches the main stream, carrying the same
    ``parent_call_id`` — reset in ``finally`` (design-brief § "Вложенность
    субагента": without the reset, the tag would leak onto whatever tool call
    the subagent's ``ToolNode`` runs next).
    """

    wrapped_tool: BaseTool
    stream_writer: StreamWriter
    parent_call_id: str

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(
            "_LifecycleEmittingTool only supports async execution via ainvoke"
        )

    async def ainvoke(
        self,
        input: str | dict[str, Any] | Any,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> Any:
        call_id = ""
        call_args: dict[str, Any] = {}
        if isinstance(input, dict):
            call_id = str(input.get("id") or "")
            raw_args = input.get("args")
            if isinstance(raw_args, dict):
                call_args = raw_args

        args_text, args_truncated = truncate(json.dumps(call_args, ensure_ascii=False))
        self.stream_writer(
            {
                "type": "tool_call_started",
                "data": {
                    "call_id": call_id,
                    "tool": self.wrapped_tool.name,
                    "parent_call_id": self.parent_call_id,
                },
            }
        )
        self.stream_writer(
            {
                "type": "tool_call_args",
                "data": {
                    "call_id": call_id,
                    "args": args_text,
                    "truncated": args_truncated,
                    "parent_call_id": self.parent_call_id,
                },
            }
        )

        status = "error"
        content = ""
        writer_token = SUBAGENT_STREAM_WRITER.set(self.stream_writer)
        parent_token = SUBAGENT_PARENT_CALL_ID.set(self.parent_call_id)
        try:
            result = await self.wrapped_tool.ainvoke(input, config, **kwargs)
            if isinstance(result, ToolMessage):
                status = result.status
                content = (
                    result.content
                    if isinstance(result.content, str)
                    else str(result.content)
                )
            else:
                status = "success"
                content = "" if result is None else str(result)
            return result
        except Exception as exc:
            content = str(exc)
            raise
        finally:
            SUBAGENT_STREAM_WRITER.reset(writer_token)
            SUBAGENT_PARENT_CALL_ID.reset(parent_token)
            content_text, content_truncated = truncate(content)
            self.stream_writer(
                {
                    "type": "tool_result",
                    "data": {
                        "call_id": call_id,
                        "tool": self.wrapped_tool.name,
                        "status": status,
                        "content": content_text,
                        "truncated": content_truncated,
                        "parent_call_id": self.parent_call_id,
                    },
                }
            )


def _wrap_tools_for_lifecycle_events(
    tools: list[BaseTool], stream_writer: StreamWriter, parent_call_id: str
) -> list[BaseTool]:
    """Wrap every subagent tool in ``_LifecycleEmittingTool`` (T1.6)."""
    return [
        _LifecycleEmittingTool(
            wrapped_tool=tool,
            stream_writer=stream_writer,
            parent_call_id=parent_call_id,
            name=tool.name,
            description=tool.description,
            args_schema=tool.args_schema,
        )
        for tool in tools
    ]


class SubagentRunner:
    """Compiles and runs a subagent graph per invocation.

    Holds the spec registry (``agent.yaml`` § ``subagents``) and the built-in
    tool pool subagent specs may draw ``tools`` names from. The pool is
    injected empty by default — ``main.py`` populates it from
    ``internal_tools`` + built-in MCP tools (T1.3). ``security_guard`` is the
    same instance the main graph uses; passing ``None`` disables the in-cycle
    checks, mirroring the main graph's fail-open behavior when the guard is
    disabled globally (T1.5).
    """

    def __init__(
        self,
        agent_config: AgentConfig,
        prompt_fragments: PromptFragmentsConfig,
        prompt_provider: PromptProvider,
        settings: Settings,
        tool_pool: dict[str, BaseTool] | None = None,
        security_guard: SecurityGuard | None = None,
        security_messages: SecurityMessages | None = None,
    ) -> None:
        if agent_config.subagents is None:
            raise RuntimeError(
                "SubagentRunner requires agent_config.subagents to be configured"
            )
        self._subagents_config = agent_config.subagents
        self._agent_config = agent_config
        self._prompt_fragments = prompt_fragments
        self._prompt_provider = prompt_provider
        self._settings = settings
        # ``None`` means the guard is globally disabled — the ReAct-cycle
        # node then skips both in-cycle checks, consistent with how the main
        # graph's ``agent_node`` treats ``security_guard=None`` (design-brief
        # is silent on a disabled guard; matching the main graph's fail-open
        # behavior here, not inventing a stricter policy for subagents).
        self._security_guard = security_guard
        self._security_messages = security_messages or SecurityMessages()

        pool = dict(tool_pool or {})
        pool.pop(RUN_SUBAGENT_TOOL_NAME, None)
        self._tool_pool = pool

        self._registry: dict[str, SubagentSpec] = {
            spec.name: spec for spec in self._subagents_config.registry
        }

    @property
    def available_types(self) -> list[str]:
        return sorted(self._registry)

    def _resolve_spec(self, agent_type: str) -> SubagentSpec:
        spec = self._registry.get(agent_type)
        if spec is None:
            raise UnknownSubagentTypeError(agent_type, self.available_types)
        return spec

    def _resolve_model_config(self, spec: SubagentSpec) -> ResolvedModelConfig:
        default_llm = self._subagents_config.llm
        return ResolvedModelConfig(
            model=spec.model or default_llm.model,
            extra_body=dict(default_llm.extra_body) or None,
            source="config",
        )

    def _build_input_message(
        self, task: str, documents: list[SubagentDocument]
    ) -> HumanMessage:
        parts: list[str] = [task] if task else []
        open_close = self._prompt_fragments.open_close("document")
        for doc in documents:
            if open_close is None:
                # No wrapper configured — fall back to bare content so a
                # missing config entry degrades instead of dropping input.
                parts.append(doc.content)
                continue
            open_tag, close_tag = open_close
            rendered_open = open_tag.format(
                id=_escape_attr(doc.id), title=_escape_attr(doc.title)
            )
            parts.append(f"{rendered_open}\n{doc.content}\n{close_tag}")
        return HumanMessage(content="\n\n".join(parts))

    async def run(
        self,
        agent_type: str,
        task: str,
        documents: list[SubagentDocument] | None = None,
        *,
        config: RunnableConfig | None = None,
        canary_token: str = "",
        stream_writer: StreamWriter | None = None,
        parent_call_id: str | None = None,
    ) -> str:
        spec = self._resolve_spec(agent_type)
        model_config = self._resolve_model_config(spec)
        llm = create_llm_from_config(self._settings, model_config)
        system_prompt = self._prompt_provider.get_prompt(spec.prompt)

        resolved_tools = [self._tool_pool[name] for name in spec.tools]
        # Wrap so every subagent tool call reports the same four events the
        # main agent's own tool calls do, tagged with `parent_call_id` (T1.6:
        # design-brief § "Вложенность субагента"). Both `stream_writer` and
        # `parent_call_id` are only known in the `run_subagent` tool's own
        # scope (the main graph's), passed down explicitly by the caller —
        # skipped when either is absent (e.g. `SubagentRunner.run` exercised
        # directly in a test, with no stream to report to).
        if stream_writer is not None and parent_call_id is not None:
            resolved_tools = _wrap_tools_for_lifecycle_events(
                resolved_tools, stream_writer, parent_call_id
            )

        builder = build_subagent_graph(
            model=llm,
            system_prompt=system_prompt,
            tools=resolved_tools,
            max_tokens=self._agent_config.context.max_tokens,
            security_guard=self._security_guard,
            canary_token=canary_token,
            tool_result_stub=self._security_messages.redacted_tool_result,
        )
        checkpointer = False if spec.persistence == "none" else None
        graph = compile_subagent_graph(builder, checkpointer=checkpointer)

        human_message = self._build_input_message(task, documents or [])

        tags = list((config or {}).get("tags") or [])
        if SUBAGENT_TAG not in tags:
            tags.append(SUBAGENT_TAG)
        # Bounds the ReAct tool-calling cycle (design-brief § "Tools субагента:
        # ... Ограничение цикла"): a delegated subtask is a single bounded
        # piece of work, not an open-ended agent loop. Operational knob —
        # ``subagents.recursion_limit`` in ``configs/agent.yaml`` (default 10,
        # ~5 tool round-trips, well under LangGraph's own default of 25).
        run_config: RunnableConfig = {
            **(config or {}),
            "tags": tags,
            "recursion_limit": self._subagents_config.recursion_limit,
        }

        logger.info(
            "subagent run started",
            agent_type=agent_type,
            model=model_config.model,
            persistence=spec.persistence,
            document_count=len(documents or []),
            tool_count=len(resolved_tools),
        )

        result = await graph.ainvoke({"messages": [human_message]}, config=run_config)

        final_message = result["messages"][-1]
        content = final_message.content
        output = content if isinstance(content, str) else str(content)

        logger.info(
            "subagent run finished",
            agent_type=agent_type,
            output_length=len(output),
        )
        return output
