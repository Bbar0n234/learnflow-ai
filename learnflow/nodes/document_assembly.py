"""
Document assembly node for combining generated sections.

Takes accumulated sections from parallel generation and assembles
them into final document with proper formatting and ordering.

Part of M2-01 decomposed document generation workflow.
"""

import logging
from typing import List
from langgraph.types import Command

from .base import BaseWorkflowNode
from ..core.state import GeneralState
from learnflow.models.document_structure import GeneratedSection, Section


logger = logging.getLogger(__name__)


def check_assembly_ready(state: GeneralState) -> Command:
    """
    Проверяет, все ли секции сгенерированы.
    Срабатывает N раз (по числу секций).
    """
    
    # Получаем общее количество ожидаемых секций из структуры
    total_sections_needed = len(state.document_structure.sections)
    
    # Получаем сколько уже готово
    current_count = len(state.generated_sections)
    
    # Проверка (>= на случай, если что-то пошло не так, но обычно ==)
    if current_count >= total_sections_needed:
        # Если это была ПОСЛЕДНЯЯ часть -> запускаем сборку
        return Command(goto="document_assembly")
    
    # Если еще не все готово -> просто гасим эту ветку.
    # Другие ветки еще работают.
    return Command(goto="__end__")


class DocumentAssemblyNode(BaseWorkflowNode):
    """
    Assembles final document from generated sections.

    Responsibilities:
    1. Sort sections by order (important for parallel generation)
    2. Format with markdown headers
    3. Combine into single document
    4. Save to state.synthesized_material
    """

    def __init__(self):
        super().__init__(logger)

    def get_node_name(self) -> str:
        """Returns node name for configuration lookup"""
        return "document_assembly"

    def _create_table_of_contents(self, state: GeneralState) -> str:
        """
        Creates markdown table of contents from document structure.

        Args:
            state: Workflow state with document_structure

        Returns:
            Formatted TOC string
        """
        if not state.document_structure:
            return ""

        lines = ["# Оглавление\n"]

        for i, section in enumerate(state.document_structure.sections, 1):
            lines.append(f"{i}. {section.title}")

            for j, subsection in enumerate(section.subsections, 1):
                lines.append(f"   {i}.{j}. {subsection.title}")

        return "\n".join(lines)

    async def __call__(self, state: GeneralState, config) -> Command:
        """
        Assembles final document from generated sections.

        Args:
            state: Current workflow state with:
                - generated_sections: List of GeneratedSection (possibly unordered)
                - document_structure: DocumentStructure for headers

            config: LangGraph configuration

        Returns:
            Command with goto="edit_material" and synthesized_material
        """
        thread_id = config["configurable"]["thread_id"]
        logger.info(f"Starting document assembly for thread {thread_id}")

        if not state.generated_sections:
            logger.error(f"No generated sections found for thread {thread_id}")
            raise ValueError("Cannot assemble document: no generated sections")

        if not state.document_structure:
            logger.error(f"No document structure found for thread {thread_id}")
            raise ValueError("Cannot assemble document: no document structure")

        # Sort sections by order (critical for parallel generation)
        sorted_sections = sorted(
            state.generated_sections, key=lambda s: s.section_order
        )

        logger.info(
            f"Assembling {len(sorted_sections)} sections for thread {thread_id}"
        )

        # Build document parts
        parts = []

        # Optional: Add table of contents
        # Uncomment to enable TOC
        # toc = self._create_table_of_contents(state)
        # if toc:
        #     parts.append(toc)
        #     parts.append("\n---\n")

        # Format each section with headers
        for gen_section in sorted_sections:
            # Get corresponding section from structure
            section = state.document_structure.sections[gen_section.section_order]

            # Add section header
            section_text = f"## {section.title}\n\n{gen_section.content}"

            parts.append(section_text)

        # Combine all parts
        synthesized_material = "\n\n".join(parts)

        logger.info(
            f"Document assembled: {len(synthesized_material)} chars for thread {thread_id}"
        )

        # Proceed to edit_material node
        return Command(
            goto="edit_material", update={"synthesized_material": synthesized_material}
        )
