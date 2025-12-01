"""
Section generation node for parallel content generation.

Generates content for a single section using LLM with context from:
- Document structure
- Current section details
- Adjacent sections (for smooth transitions)
- Handwritten notes (external sources)

Part of M2-01 decomposed document generation workflow.
"""

import logging
from typing import Dict, Any
from langchain_core.messages import SystemMessage
from langgraph.types import Command

from .base import BaseWorkflowNode
from ..core.state import GeneralState
from learnflow.models.document_structure import GeneratedSection, Section


logger = logging.getLogger(__name__)


class SectionGenerationNode(BaseWorkflowNode):
    """
    Worker node for generating content of a single section.

    Designed to be called multiple times in parallel via LangGraph Send.
    Each invocation processes one section and returns GeneratedSection
    which gets accumulated in state.generated_sections.
    """

    def __init__(self):
        super().__init__(logger)
        self.model = self.create_model()

    def get_node_name(self) -> str:
        """Returns node name for configuration lookup"""
        return "generate_section"

    def _build_context_from_state(self, state: GeneralState) -> Dict[str, Any]:
        """
        Builds extended context for section generation.

        Note: current_section, previous_section, next_section are passed
        via Send payload and accessed through config in __call__
        """
        return {
            "input_content": state.input_content,
            "document_structure": (
                state.document_structure.model_dump_json()
                if state.document_structure
                else "{}"
            ),
            "handwritten_notes": state.recognized_notes or "",
        }

    async def __call__(self, state: GeneralState, config) -> Command:
        """
        Generates content for a single section.

        Args:
            state: Current workflow state with document_structure
            config: LangGraph configuration with Send payload containing:
                - section: Current section to generate (dict)
                - section_index: Index in sections list
                - previous_section: Previous section dict (or None)
                - next_section: Next section dict (or None)

        Returns:
            Command with GeneratedSection added to state.generated_sections
        """
        thread_id = config["configurable"]["thread_id"]

        # Extract section data from Send payload
        # In LangGraph Send, payload is passed via config
        section_data = config.get("section")
        section_index = config.get("section_index", 0)
        previous_section = config.get("previous_section")
        next_section = config.get("next_section")

        if not section_data:
            logger.error(f"No section data in config for thread {thread_id}")
            raise ValueError("Section data missing from Send payload")

        # Reconstruct Section object from dict
        section = Section(**section_data)

        logger.info(
            f"Generating content for section {section_index}: '{section.title}' (thread {thread_id})"
        )

        # Build base context from state
        context = self._build_context_from_state(state)

        # Add section-specific context
        context.update(
            {
                "current_section": section.model_dump_json(),
                "previous_section": (
                    Section(**previous_section).model_dump_json()
                    if previous_section
                    else None
                ),
                "next_section": (
                    Section(**next_section).model_dump_json() if next_section else None
                ),
            }
        )

        # Get personalized prompt from Prompt Config Service
        system_prompt = await self.get_system_prompt(state, config, extra_context=context)

        # Generate section content
        messages = [SystemMessage(content=system_prompt)]
        response = await self.model.ainvoke(messages)

        content = response.content

        logger.info(
            f"Generated {len(content)} chars for section {section_index} (thread {thread_id})"
        )

        # Create GeneratedSection with order matching section.order
        generated_section = GeneratedSection(
            section_order=section.order, content=content
        )

        # Return Command with accumulated section
        # operator.add will append this to state.generated_sections
        return Command(update={"generated_sections": [generated_section]})
