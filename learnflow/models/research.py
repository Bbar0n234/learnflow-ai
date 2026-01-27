"""
Research Agent models for M2-03 integration.

Contains:
- SourceData: Citation source information
- ResearchClassifierResult: Binary classifier output
- ResearchState: Internal agent state
- Tool schemas with discriminated union pattern
"""

import operator
from functools import reduce
from typing import Any, Dict, List, Literal, Optional, Type, TypeVar, Annotated

from pydantic import BaseModel, Field, create_model


# ============================================================================
# SOURCE DATA MODEL
# ============================================================================


class SourceData(BaseModel):
    """Citation source information for research agent."""

    number: int = Field(description="Citation number [1], [2], [3]")
    title: str = Field(description="Source title")
    url: str = Field(description="Source URL")
    snippet: str = Field(default="", description="Short snippet from search")
    full_content: str = Field(
        default="", description="Full page content (optional)"
    )
    char_count: int = Field(default=0, description="Character count in full_content")


# ============================================================================
# CLASSIFIER RESULT
# ============================================================================


class ResearchClassifierResult(BaseModel):
    """Binary classifier result for determining if research is needed."""

    reasoning: str = Field(
        description="Step-by-step reasoning about whether the topic needs web research"
    )
    needs_research: bool = Field(
        description="Whether the topic requires web research for current information"
    )


# ============================================================================
# RESEARCH STATE (Internal agent state, not in GeneralState)
# ============================================================================


class ResearchState(BaseModel):
    """LangGraph state for research agent's internal iterations."""

    # Input
    input_content: str = Field(description="User's topic or question")

    # Execution state
    iteration: int = Field(default=0, description="Current iteration number")
    agent_state: Literal[
        "planning", "searching", "extracting", "synthesizing", "completed"
    ] = Field(default="planning", description="Current agent state")

    # Accumulated knowledge (dict for deduplication by URL)
    sources: Dict[str, SourceData] = Field(
        default_factory=dict, description="URL → SourceData mapping"
    )

    # History for LLM context (agent's decision-making memory)
    decision_history: List[Any] = Field(
        default_factory=list,
        description="Agent's decision history for context between iterations",
    )

    # Resource counters
    searches_used: int = Field(default=0, description="Number of searches performed")
    extractions_used: int = Field(
        default=0, description="Number of content extractions performed"
    )

    # Results
    research_goal: str = Field(default="", description="Current research goal")
    final_report: Optional[str] = Field(
        default=None, description="Final report with citations"
    )


# ============================================================================
# DISCRIMINATED UNION PATTERN
# ============================================================================

T = TypeVar("T", bound=BaseModel)


class DiscriminatorMixin(BaseModel):
    """Adds discriminator field and excludes it from serialization."""

    tool_type: str = Field(..., description="Tool type identifier")

    def model_dump(self, *args, **kwargs):
        # Exclude tool_type from serialization (technical field for LLM only)
        exclude = kwargs.pop("exclude", set())
        exclude = exclude.union({"tool_type"})
        return super().model_dump(*args, exclude=exclude, **kwargs)


def wrap_with_discriminator(
    tool_class: Type[T], discriminator_value: str
) -> Type[BaseModel]:
    """
    Creates a version of the tool with discriminator field.

    Args:
        tool_class: Original tool class
        discriminator_value: Value for discriminator field

    Returns:
        New class with DiscriminatorMixin
    """
    return create_model(
        f"D_{tool_class.__name__}",
        __base__=(tool_class, DiscriminatorMixin),  # Order matters!
        tool_type=(
            Literal[discriminator_value],
            Field(default=discriminator_value, description="Tool type"),
        ),
    )


# ============================================================================
# TOOL SCHEMAS
# ============================================================================


class ReasoningTool(BaseModel):
    """Structured reasoning for decision transparency."""

    reasoning_steps: list[str] = Field(
        min_length=2,
        max_length=3,
        description="Key reasoning steps (2-3 concise points)",
    )
    current_situation: str = Field(
        max_length=300, description="Current research situation summary"
    )
    enough_data: bool = Field(
        description=(
            "Sufficient data to support comprehensive EDUCATIONAL content generation. "
            "Consider: multiple authoritative sources, mix of theory and practice, "
            "enough material for thorough explanations."
        )
    )
    next_steps: list[str] = Field(
        min_length=1, max_length=3, description="Planned next actions (1-3)"
    )
    task_completed: bool = Field(description="Research task finished")


class WebSearchTool(BaseModel):
    """Web search via Tavily."""

    query: str = Field(description="Search query to find relevant information")
    max_results: int = Field(
        default=3, ge=1, le=5, description="Number of results to return (1-5)"
    )


class ExtractPageContentTool(BaseModel):
    """Extract full page content from a source."""

    source_number: int = Field(
        ge=1,
        description="Source citation number [1], [2], [3] to extract full content from",
    )
    reasoning: str = Field(description="Why this source is worth extracting")


class GeneratePlanTool(BaseModel):
    """Create initial research plan."""

    reasoning: str = Field(description="Rationale for the research plan")
    research_goal: str = Field(description="Clear, specific research objective")
    planned_steps: list[str] = Field(
        min_length=2, max_length=5, description="Planned research steps (2-5)"
    )
    search_strategies: list[str] = Field(
        min_length=1, max_length=3, description="Search strategies to employ (1-3)"
    )


class AdaptPlanTool(BaseModel):
    """Adapt research plan based on findings."""

    reasoning: str = Field(description="Why plan adaptation is needed")
    original_goal: str = Field(description="Original research goal")
    new_goal: str = Field(description="Updated research goal")
    plan_changes: list[str] = Field(
        min_length=1, max_length=3, description="Specific changes to the plan (1-3)"
    )
    next_steps: list[str] = Field(
        min_length=1, max_length=3, description="Next actions under new plan (1-3)"
    )


class CreateReportTool(BaseModel):
    """
    Create research summary for educational content generation.

    The report should provide information-dense material that helps the downstream
    system generate comprehensive learning content. Focus on facts, explanations,
    examples, and best practices - not narrative polish.
    """

    content: str = Field(
        description=(
            "Information-dense research summary with inline citations [1], [2], [3]. "
            "Include: key concepts, practical examples, current best practices, "
            "technical details for teaching. Focus on educational value."
        )
    )


class FinalAnswerTool(BaseModel):
    """
    Complete research without creating a report.

    Use when:
    - Topic doesn't require web search (classical theory, math)
    - Search failed to find relevant results
    - Request is outside capabilities
    """

    message: str = Field(description="Final message explaining completion reason")


# ============================================================================
# WRAPPER MODEL (STUB)
# ============================================================================


class NextStepToolStub(BaseModel):
    """Stub for IDE autocomplete. Real model created via build_next_step_tools()."""

    action: T  # Generic placeholder for the selected tool


# ============================================================================
# DYNAMIC UNION BUILDER
# ============================================================================


def build_next_step_tools(tools: list[tuple[Type[T], str]]) -> Type[NextStepToolStub]:
    """
    Creates Pydantic model with discriminated union of available tools.

    Pattern from DISCRIMINATED_UNION_PATTERN.md.
    Pydantic automatically recognizes discriminated union through Literal fields.

    Args:
        tools: List of (tool_class, discriminator_id) tuples

    Returns:
        Pydantic model with 'action' field containing discriminated union
    """
    if len(tools) == 1:
        # Single tool - wrap and return in stub
        wrapped = wrap_with_discriminator(tools[0][0], tools[0][1])
        return create_model(
            "NextStepTools",
            __base__=(NextStepToolStub,),
            action=(wrapped, Field(description="Selected tool action")),
        )

    # Wrap all tools with discriminator
    wrapped = [wrap_with_discriminator(cls, disc_id) for cls, disc_id in tools]

    # Create Union: A | B | C | D
    union = reduce(operator.or_, wrapped)

    # Pydantic automatically recognizes discriminated union through Literal fields
    # NO explicit discriminator= needed (causes OpenAI oneOf error)
    union_annotated = Annotated[union, Field()]

    # Create wrapper model with union as 'action' field
    return create_model(
        "NextStepTools",
        __base__=(NextStepToolStub,),
        action=(union_annotated, Field(description="Selected tool action")),
    )


def get_available_tools(
    state: ResearchState,
    max_iterations: int = 8,
    max_searches: int = 6,
    max_extractions: int = 5,
) -> Type[NextStepToolStub]:
    """
    Returns dynamic Pydantic model with available tools based on current state.

    Resource management via constrained decoding.

    Args:
        state: Current research state
        max_iterations: Maximum allowed iterations
        max_searches: Maximum allowed searches
        max_extractions: Maximum allowed extractions

    Returns:
        Pydantic model for structured output with available tools
    """
    # Forced completion at MAX_ITERATIONS
    if state.iteration >= max_iterations:
        return build_next_step_tools(
            [
                (CreateReportTool, "create_report"),
                (FinalAnswerTool, "final_answer"),
            ]
        )

    # Planning phase (iteration 0)
    if state.iteration == 0:
        return build_next_step_tools(
            [
                (GeneratePlanTool, "generate_plan"),
                (ReasoningTool, "reasoning"),
            ]
        )

    # Build list of available tools
    available = [
        (ReasoningTool, "reasoning"),
        (CreateReportTool, "create_report"),
        (FinalAnswerTool, "final_answer"),
        (AdaptPlanTool, "adapt_plan"),
    ]

    # Add conditional tools
    if state.searches_used < max_searches:
        available.append((WebSearchTool, "web_search"))

    if state.extractions_used < max_extractions and len(state.sources) > 0:
        available.append((ExtractPageContentTool, "extract_content"))

    return build_next_step_tools(available)
