"""
Pydantic models for document structure planning and generation.

Based on experimental implementation from M2-01 notebook.
These models support the decomposed document generation workflow:
1. Planning structure with HITL review
2. Parallel section generation
3. Document assembly
"""

from typing import List, Literal
from pydantic import BaseModel, Field


class Subsection(BaseModel):
    """Document subsection with key theses to be covered."""

    title: str = Field(description="Subsection title")
    theses: List[str] = Field(
        default_factory=list,
        description="Key theses to be covered in this subsection",
    )
    order: int = Field(
        default=0,
        description="Sequential order of this subsection within parent section (assigned programmatically)",
    )


class Section(BaseModel):
    """Document section containing multiple subsections."""

    title: str = Field(description="Section title")
    subsections: List[Subsection] = Field(
        default_factory=list, description="List of subsections"
    )
    order: int = Field(
        default=0,
        description="Sequential order of this section in the document (assigned programmatically)",
    )


class DocumentStructure(BaseModel):
    """Hierarchical document structure for educational material generation."""

    sections: List[Section] = Field(description="List of document sections")


class NextStepDecision(BaseModel):
    """
    Decision model for two-phase HITL interaction.

    Used to determine whether user feedback requires clarification
    (regenerate structure) or signals finalization (approve and proceed).
    """

    next_step: Literal["clarify", "finalize"] = Field(
        description=(
            "Control flow decision: "
            "'clarify' - user wants refinements, continue HITL loop; "
            "'finalize' - user approves structure, exit HITL and proceed to generation"
        )
    )


class GeneratedSection(BaseModel):
    """
    Result of generating content for a single section.

    Used for accumulation during parallel section generation.
    """

    section_order: int = Field(
        description="Sequential order matching the parent Section.order for correct sorting"
    )
    content: str = Field(description="Generated markdown content for this section")
