"""
Research Classifier Node for M2-03 integration.

Binary LLM classifier that determines whether a topic requires
web research for current/accurate information.

Criteria for needs_research=True:
- Current events, recent developments
- Rapidly evolving fields (AI/ML, tech)
- Specific tools, libraries, frameworks
- Industry trends and best practices
- Documentation and API references

Criteria for needs_research=False:
- Classical theory (math, physics fundamentals)
- Historical topics
- Well-established concepts
- Pure theoretical discussions
"""

import logging
from typing import Dict, Any

from langchain_core.messages import SystemMessage
from langgraph.types import Command

from .base import BaseWorkflowNode
from ..core.state import GeneralState
from ..models.research import ResearchClassifierResult


logger = logging.getLogger(__name__)


class ResearchClassifierNode(BaseWorkflowNode):
    """
    Binary classifier node that determines if topic needs web research.

    Routes workflow to:
    - research_agent: if needs_research=True
    - planning_structure: if needs_research=False
    """

    def __init__(self):
        super().__init__(logger)
        self.model = self.create_model()

    def get_node_name(self) -> str:
        """Returns node name for configuration lookup."""
        return "research_classifier"

    def _build_context_from_state(self, state: GeneralState) -> Dict[str, Any]:
        """
        Builds context for prompt from workflow state.

        Provides:
        - input_content: User's topic/question
        - recognized_notes: Handwritten notes if available
        """
        return {
            "input_content": state.input_content,
            "recognized_notes": state.recognized_notes or "",
        }

    async def __call__(self, state: GeneralState, config) -> Command:
        """
        Classify whether topic needs research.

        Args:
            state: Current workflow state
            config: LangGraph configuration

        Returns:
            Command with goto to research_agent or planning_structure
        """
        thread_id = config["configurable"]["thread_id"]
        logger.info(f"Research classification for thread {thread_id}")

        # Get personalized prompt from Prompt Config Service
        system_prompt = await self.get_system_prompt(state, config)

        # Use structured output for classification
        llm = self.model.with_structured_output(ResearchClassifierResult)

        messages = [SystemMessage(content=system_prompt)]
        result = await llm.ainvoke(messages)

        logger.info(
            f"Classification result for thread {thread_id}: "
            f"needs_research={result.needs_research}, "
            f"reasoning={result.reasoning[:100]}..."
        )

        # Route based on classification
        if result.needs_research:
            logger.info(f"Routing to research_agent for thread {thread_id}")
            return Command(
                goto="research_agent",
                update={"needs_research": True},
            )
        else:
            logger.info(f"Routing to planning_structure for thread {thread_id}")
            return Command(
                goto="planning_structure",
                update={"needs_research": False},
            )
