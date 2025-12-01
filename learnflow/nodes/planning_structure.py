"""
Document structure planning node with HITL review.

Implements two-phase HITL interaction:
1. Decision Phase: Analyzes user feedback to determine next_step (clarify/finalize)
2. Content Phase: Generates updated structure if clarification needed

Based on experimental implementation from M2-01 notebook.
"""

import logging
from typing import Dict, Any
from langchain_core.messages import SystemMessage, AIMessage, HumanMessage
from langgraph.types import Command, interrupt
from langgraph.constants import Send

from .base import BaseWorkflowNode
from ..core.state import GeneralState
from learnflow.models.document_structure import (
    DocumentStructure,
    NextStepDecision,
    Section,
)


logger = logging.getLogger(__name__)


class PlanningStructureNode(BaseWorkflowNode):
    """
    Document structure planning node with two-phase HITL interaction.

    Workflow:
    1. Initial generation: Creates hierarchical document structure
    2. HITL loop:
       - Phase 1 (Decision): Analyzes user feedback intent
       - Phase 2 (Content): Generates refined structure if needed
    3. Finalization: Proceeds to section generation when approved
    """

    def __init__(self):
        super().__init__(logger)
        self.model = self.create_model()

    def get_node_name(self) -> str:
        """Returns node name for configuration lookup"""
        return "planning_structure"

    def _build_context_from_state(self, state: GeneralState) -> Dict[str, Any]:
        """
        Builds context for prompt from workflow state.

        Maps state fields to prompt placeholders:
        - input_content -> input_content (user's topic/question)
        - recognized_notes -> external_sources (handwritten notes)
        """
        return {
            "input_content": state.input_content,
            "external_sources": state.recognized_notes or "",
        }

    def is_initial(self, state: GeneralState) -> bool:
        """Checks if this is the first generation (no feedback history)"""
        return len(state.feedback_messages) == 0

    def _assign_order(self, structure: DocumentStructure) -> DocumentStructure:
        """
        Programmatically assigns sequential order to sections and subsections.

        Args:
            structure: DocumentStructure with sections

        Returns:
            DocumentStructure with order fields populated
        """
        for section_idx, section in enumerate(structure.sections):
            section.order = section_idx
            for subsection_idx, subsection in enumerate(section.subsections):
                subsection.order = subsection_idx

        return structure

    def _format_structure_for_telegram(self, structure: DocumentStructure) -> str:
        """
        Formats document structure for Telegram display with emojis and indentation.

        Args:
            structure: DocumentStructure to format

        Returns:
            Formatted string with tree-like visualization
        """
        lines = []

        for i, section in enumerate(structure.sections, 1):
            lines.append(f"\n{i}. 📚 **{section.title}**")

            for j, subsection in enumerate(section.subsections, 1):
                is_last_subsection = j == len(section.subsections)
                prefix = "└─" if is_last_subsection else "├─"
                lines.append(f"  {prefix} 📖 {subsection.title}")

                if subsection.theses:
                    for thesis in subsection.theses:
                        thesis_prefix = "     " if is_last_subsection else "  │  "
                        lines.append(f"{thesis_prefix}• {thesis}")

        return "\n".join(lines)

    async def __call__(self, state: GeneralState, config) -> Command:
        """
        Main node logic implementing two-phase HITL interaction.

        Phase 1 (Initial): Generate structure
        Phase 2 (HITL Loop):
            - Decision: Analyze feedback intent
            - Content: Generate refined structure if needed
        Phase 3 (Finalize): Proceed to section generation

        Args:
            state: Current workflow state
            config: LangGraph configuration

        Returns:
            Command with goto and state updates
        """
        thread_id = config["configurable"]["thread_id"]
        logger.info(f"Starting planning_structure for thread {thread_id}")

        # ===== INITIAL GENERATION =====
        if self.is_initial(state):
            logger.info(f"Initial structure generation for thread {thread_id}")

            # Get personalized prompt from Prompt Config Service
            # Uses template_variant="initial" by default
            system_prompt = await self.get_system_prompt(
                state, config, extra_context={"template_variant": "initial"}
            )

            # Generate structure with LLM
            llm = self.model.with_structured_output(DocumentStructure)
            messages = [SystemMessage(content=system_prompt)]
            structure = await llm.ainvoke(messages)

            # Assign order programmatically
            structure = self._assign_order(structure)

            logger.info(
                f"Generated structure with {len(structure.sections)} sections for thread {thread_id}"
            )

            # Initialize feedback history with structure
            feedback_messages = [AIMessage(content=structure.model_dump_json())]

            # Format for display
            formatted = self._format_structure_for_telegram(structure)

            # Send to user and wait for feedback
            interrupt_json = {
                "message": [
                    formatted,
                    "\n💭 Всё устраивает?\n\n"
                    "• Напишите 'да', 'отлично', 'подходит' для утверждения\n"
                    "• Или опишите, что нужно изменить",
                ]
            }
            user_feedback = interrupt(interrupt_json)

            # Validate user feedback
            if user_feedback and self.security_guard:
                user_feedback = await self.validate_input(user_feedback)

            # Save structure and feedback in state
            return Command(
                goto="planning_structure",
                update={
                    "document_structure": structure,
                    "feedback_messages": feedback_messages
                    + [HumanMessage(content=user_feedback)],
                },
            )

        # ===== HITL LOOP: TWO-PHASE GENERATION =====
        logger.info(f"HITL iteration for thread {thread_id}")

        # Extract user feedback from history (last message)
        user_feedback = state.feedback_messages[-1].content

        # ===== PHASE 1: DECISION ANALYSIS =====
        logger.info(f"Phase 1: Decision analysis for thread {thread_id}")

        # Get further variant prompt
        system_prompt = await self.get_system_prompt(
            state, config, extra_context={"template_variant": "further"}
        )

        # Decision LLM with NextStepDecision schema
        llm_decision = self.model.with_structured_output(NextStepDecision)

        # Build messages: system + feedback history
        messages = [SystemMessage(content=system_prompt)] + state.feedback_messages

        decision = await llm_decision.ainvoke(messages)

        logger.info(f"Phase 1 decision: {decision.next_step} for thread {thread_id}")

        # Add decision to history
        updated_messages = state.feedback_messages + [
            AIMessage(content=decision.model_dump_json())
        ]

        # ===== PHASE 2: CONTENT GENERATION (conditional) =====
        if decision.next_step == "finalize":
            # User approved - create Send commands for parallel section generation
            logger.info(
                f"Structure approved, creating {len(state.document_structure.sections)} Send commands for thread {thread_id}"
            )

            sections = state.document_structure.sections

            # Create Send commands for each section
            send_commands = []
            for i, section in enumerate(sections):
                send_commands.append(
                    Send(
                        "generate_section",
                        {
                            "section": section.model_dump(),
                            "section_index": i,
                            "previous_section": (
                                sections[i - 1].model_dump() if i > 0 else None
                            ),
                            "next_section": (
                                sections[i + 1].model_dump()
                                if i < len(sections) - 1
                                else None
                            ),
                        },
                    )
                )

            logger.info(
                f"Created {len(send_commands)} parallel generation tasks for thread {thread_id}"
            )

            # Return Command with goto to document_assembly and Send commands
            return Command(
                goto="document_assembly",
                update={
                    "structure_approved": True,
                    "feedback_messages": [],  # Clear history for next HITL node
                    "generated_sections": [],  # Initialize for accumulation
                },
                graph=send_commands,
            )

        # User wants changes - generate refined structure
        logger.info(f"Phase 2: Content regeneration for thread {thread_id}")

        # Content LLM with DocumentStructure schema
        llm_content = self.model.with_structured_output(DocumentStructure)

        # Use same message history
        updated_structure = await llm_content.ainvoke(messages)

        # Assign order to updated structure
        updated_structure = self._assign_order(updated_structure)

        logger.info(
            f"Regenerated structure with {len(updated_structure.sections)} sections for thread {thread_id}"
        )

        # Add updated structure to history
        updated_messages = updated_messages + [
            AIMessage(content=updated_structure.model_dump_json())
        ]

        # Format for display
        formatted = self._format_structure_for_telegram(updated_structure)

        # Send updated structure to user
        interrupt_json = {
            "message": [
                formatted,
                "\n💭 Теперь устраивает?\n\n"
                "• Напишите 'да', 'отлично', 'подходит' для утверждения\n"
                "• Или опишите, что еще нужно изменить",
            ]
        }
        user_feedback = interrupt(interrupt_json)

        # Validate user feedback
        if user_feedback and self.security_guard:
            user_feedback = await self.validate_input(user_feedback)

        # Continue HITL loop
        return Command(
            goto="planning_structure",
            update={
                "document_structure": updated_structure,
                "feedback_messages": updated_messages
                + [HumanMessage(content=user_feedback)],
            },
        )
