"""SubagentRunner — the subagent-as-tool execution core.

Resolves a ``SubagentSpec`` by ``agent_type``, builds the model + prompt for
it, assembles the input (``task`` + attributed documents), compiles the
subagent graph per invocation, and runs it. The ``run_subagent`` tool (T1.3)
is a thin wrapper around this class: fetching artifacts by
``input_artifact_ids`` and mapping errors into tool-visible strings both live
there, not here — this module raises plain exceptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import structlog
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool

from app.agent.config import (
    AgentConfig,
    PromptFragmentsConfig,
    ResolvedModelConfig,
    SubagentSpec,
)
from app.agent.security.guard import SecurityGuard
from app.agent.security.types import SecurityMessages
from app.agent.subagents.graph import build_subagent_graph, compile_subagent_graph
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

# Bounds the subagent ReAct tool-calling cycle (design-brief § "Tools
# субагента: ... Ограничение цикла"). A delegated subtask is a single bounded
# piece of work, not an open-ended agent loop — 10 super-steps (~5 tool
# round-trips: llm -> tools -> llm -> ...) is generous for the v1 tool pool
# (3 firecrawl tools) while still failing fast on a runaway loop, well under
# LangGraph's own default of 25.
SUBAGENT_RECURSION_LIMIT: Final = 10


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
    ) -> str:
        spec = self._resolve_spec(agent_type)
        model_config = self._resolve_model_config(spec)
        llm = create_llm_from_config(self._settings, model_config)
        system_prompt = self._prompt_provider.get_prompt(spec.prompt)

        resolved_tools = [self._tool_pool[name] for name in spec.tools]

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
        run_config: RunnableConfig = {
            **(config or {}),
            "tags": tags,
            "recursion_limit": SUBAGENT_RECURSION_LIMIT,
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
