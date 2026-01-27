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
from typing_extensions import TypedDict

from .base import BaseWorkflowNode
from ..core.state import GeneralState
from learnflow.models.document_structure import GeneratedSection, Section

class SectionWorkerState(TypedDict):
    # Поля, которые мы передаем через Send
    research_report: str
    recognized_notes: str
    document_structure: Any
    input_content: str
    section: dict 
    section_index: int
    previous_section: dict | None
    next_section: dict | None


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

    def _build_context_from_state(self, state: SectionWorkerState) -> Dict[str, Any]:
        """
        Builds extended context for section generation.

        Note: current_section, previous_section, next_section are passed
        via Send payload and accessed through config in __call__

        External sources include both research report and handwritten notes.
        """
        # Combine external sources: web research + user notes
        external_sources_parts = []

        if state["research_report"]:
            external_sources_parts.append(f"## Web Research Results\n{state['research_report']}")

        if state["recognized_notes"]:
            external_sources_parts.append(f"## User Notes\n{state['recognized_notes']}")

        return {
            "input_content": state["input_content"],
            "document_structure": (
                state["document_structure"].model_dump_json()
                if state["document_structure"]
                else "{}"
            ),
            "external_sources": "\n\n".join(external_sources_parts),
            # Keep handwritten_notes for backward compatibility
            "handwritten_notes": state["recognized_notes"] or "",
        }

    async def __call__(self, state: SectionWorkerState, config) -> Command:
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
        section_data = state.get("section")
        section_index = state.get("section_index")
        previous_section = state.get("previous_section")
        next_section = state.get("next_section")

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
                    else ""
                ),
                "next_section": (
                    Section(**next_section).model_dump_json() if next_section else ""
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
        return Command(
            update={"generated_sections": [generated_section]},
            goto="check_assembly_ready" 
        )
