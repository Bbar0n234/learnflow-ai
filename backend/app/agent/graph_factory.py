from __future__ import annotations

from typing import Any

import structlog
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph

from app.agent.config import AgentConfig, PromptFragmentsConfig, ResolvedModelConfig
from app.agent.graph import build_graph, compile_graph
from app.agent.security.guard import SecurityGuard
from app.agent.security.types import SecurityMessages
from app.config import Settings
from app.infra.llm import create_llm_from_config, create_summarization_llm
from app.infra.prompt_provider import PromptProvider

logger = structlog.get_logger()


class GraphFactory:
    """Builds and compiles a LangGraph per-request based on resolved model config."""

    def __init__(
        self,
        settings: Settings,
        agent_config: AgentConfig,
        prompt_fragments: PromptFragmentsConfig,
        security_messages: SecurityMessages,
        global_tools: list[BaseTool],
        skills_index: str,
        checkpointer: Any,
        store: Any,
        prompt_provider: PromptProvider,
        security_guard: SecurityGuard | None = None,
    ) -> None:
        self._settings = settings
        self._agent_config = agent_config
        self._prompt_fragments = prompt_fragments
        self._security_messages = security_messages
        self._global_tools = global_tools
        self._skills_index = skills_index
        self._checkpointer = checkpointer
        self._store = store
        self._prompt_provider = prompt_provider
        self._security_guard = security_guard

    def build(
        self,
        model_config: ResolvedModelConfig,
        extra_tools: list[BaseTool] | None = None,
    ) -> CompiledStateGraph[Any, Any, Any, Any]:
        llm = create_llm_from_config(self._settings, model_config)

        summarization_llm = None
        if self._agent_config.summarization is not None:
            summarization_llm = create_summarization_llm(
                self._settings, self._agent_config.summarization
            )

        all_tools = list(self._global_tools)
        if extra_tools:
            all_tools.extend(extra_tools)

        builder = build_graph(
            model=llm,
            tools=all_tools,
            agent_config=self._agent_config,
            prompt_fragments=self._prompt_fragments,
            security_messages=self._security_messages,
            skills_index=self._skills_index,
            summarization_model=summarization_llm,
            prompt_provider=self._prompt_provider,
            security_guard=self._security_guard,
        )

        logger.debug(
            "graph built",
            model=model_config.model,
            source=model_config.source,
            tool_count=len(all_tools),
        )

        return compile_graph(
            builder,
            checkpointer=self._checkpointer,
            store=self._store,
        )
