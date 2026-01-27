"""
Research Agent Node for M2-03 integration.

Iterative agent that performs web research to gather information
for educational content generation.

Capabilities:
- Adaptive research planning
- Web search via Tavily
- Full page content extraction
- Citation management with [1], [2], [3] format
- Structured reasoning for decision transparency

Output:
- research_report: Information-dense report with inline citations
- research_sources: URL -> SourceData mapping
"""

import logging
from typing import Any, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.types import Command

from .base import BaseWorkflowNode
from ..core.state import GeneralState
from ..config.settings import get_settings
from ..models.research import (
    ResearchState,
    SourceData,
    get_available_tools,
    WebSearchTool,
    ExtractPageContentTool,
    GeneratePlanTool,
    AdaptPlanTool,
    ReasoningTool,
    CreateReportTool,
    FinalAnswerTool,
)
from ..services.tavily_client import TavilyClient


logger = logging.getLogger(__name__)


class ResearchAgentNode(BaseWorkflowNode):
    """
    Iterative research agent that gathers information via web search.

    Implements the agentic loop from M2-03 notebook:
    1. Planning phase (iteration 0)
    2. Iterative: reason → select action → execute
    3. Adaptive planning as needed
    4. Report creation with citations
    """

    def __init__(self):
        super().__init__(logger)
        self.model = self.create_model()
        self.settings = get_settings()

        # Initialize Tavily client (lazy)
        self._tavily_client = None

        # Cached system prompt for current session (to avoid repeated service calls)
        self._cached_system_prompt = None

    def get_node_name(self) -> str:
        """Returns node name for configuration lookup."""
        return "research_agent"

    @property
    def tavily_client(self) -> TavilyClient:
        """Lazy initialization of Tavily client."""
        if self._tavily_client is None:
            self._tavily_client = TavilyClient()
        return self._tavily_client

    def _build_context_from_state(self, state: GeneralState) -> Dict[str, Any]:
        """Builds context for prompt from workflow state."""
        return {
            "input_content": state.input_content,
            "recognized_notes": state.recognized_notes or "",
        }

    def _build_messages(self, research_state: ResearchState) -> List:
        """
        Build messages for LLM context.

        All state is conveyed through conversation history, not system prompt.
        System prompt contains only static guidelines (fetched from Prompt Config Service).
        """
        if not self._cached_system_prompt:
            raise RuntimeError("System prompt not initialized. Call _init_system_prompt first.")

        messages = [SystemMessage(content=self._cached_system_prompt)]

        # Add initial user query if this is first message
        if not research_state.decision_history:
            messages.append(
                HumanMessage(content=f"Research topic: {research_state.input_content}")
            )

        # Add conversation history (AIMessage with tool_calls, ToolMessage with results)
        messages.extend(research_state.decision_history)

        return messages

    async def _init_system_prompt(self, state: GeneralState, config) -> None:
        """
        Initialize and cache system prompt from Prompt Config Service.

        Called once at the start of research session to avoid repeated service calls
        during iterative agent loop.
        """
        self._cached_system_prompt = await self.get_system_prompt(state, config)
        logger.debug("System prompt cached for research session")

    async def _select_action(self, research_state: ResearchState):
        """
        Select next action using structured output.

        Returns:
            tuple: (action, ai_message_with_tool_call) for emulating function calling
        """
        logger.debug(f"Selecting action (iteration {research_state.iteration})...")

        messages = self._build_messages(research_state)

        # Get available tools based on current state
        available_tools_model = get_available_tools(
            research_state,
            max_iterations=self.settings.research_max_iterations,
            max_searches=self.settings.research_max_searches,
            max_extractions=self.settings.research_max_extractions,
        )

        llm = self.model.with_structured_output(available_tools_model)

        # Model returns wrapper with .action field (structured output)
        response = await llm.ainvoke(messages)
        action = response.action

        # Get tool type for logging
        tool_type = action.model_dump().get("tool_type", type(action).__name__)
        logger.info(f"Selected action: {tool_type}")

        # Emulate tool_calls for OpenAI conversation history
        ai_message_with_tool_call = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": type(action).__name__,
                    "args": action.model_dump(exclude={"tool_type"}),
                    "id": f"call_{research_state.iteration}",
                }
            ],
        )

        return action, ai_message_with_tool_call

    def _format_tool_result(self, action, execution_result: dict) -> str:
        """Format tool execution result for ToolMessage."""
        if isinstance(action, WebSearchTool):
            sources_count = len(execution_result.get("sources", {}))
            return f"Found {sources_count} new sources for query: '{action.query}'"

        elif isinstance(action, ExtractPageContentTool):
            sources = execution_result.get("sources", {})
            if sources:
                source = list(sources.values())[0]
                return (
                    f"Extracted {source.char_count} chars "
                    f"from source [{action.source_number}]"
                )
            return f"Failed to extract from source [{action.source_number}]"

        elif isinstance(action, GeneratePlanTool):
            return f"Research plan created: {action.research_goal}"

        elif isinstance(action, AdaptPlanTool):
            return f"Plan adapted: {action.new_goal}"

        elif isinstance(action, ReasoningTool):
            steps = "\n".join([f"  - {s}" for s in action.reasoning_steps])
            return f"Reasoning:\n{steps}\nEnough data: {action.enough_data}"

        elif isinstance(action, CreateReportTool):
            return f"Report created ({len(action.content)} chars)"

        elif isinstance(action, FinalAnswerTool):
            return f"Research completed: {action.message}"

        return "Action executed"

    async def _execute_action(
        self,
        action,
        ai_message_with_tool_call: AIMessage,
        research_state: ResearchState,
    ) -> dict:
        """
        Execute selected action and return state updates.

        Args:
            action: Selected tool instance
            ai_message_with_tool_call: AIMessage with tool_calls (for history)
            research_state: Current state

        Returns:
            dict: State updates including decision_history
        """
        updates = {}
        execution_result = {}

        # Execute based on action type
        if isinstance(action, WebSearchTool):
            new_sources = self.tavily_client.search_and_create_sources(
                query=action.query,
                existing_sources=research_state.sources,
                max_results=action.max_results,
            )
            updates["sources"] = {**research_state.sources, **new_sources}
            updates["searches_used"] = research_state.searches_used + 1
            execution_result["sources"] = new_sources

        elif isinstance(action, ExtractPageContentTool):
            updated_source = self.tavily_client.extract_source_content(
                source_number=action.source_number,
                sources=research_state.sources,
            )
            if updated_source:
                # Update the source in the dict
                for url, source in research_state.sources.items():
                    if source.number == action.source_number:
                        updates["sources"] = {
                            **research_state.sources,
                            url: updated_source,
                        }
                        execution_result["sources"] = {url: updated_source}
                        break
            updates["extractions_used"] = research_state.extractions_used + 1

        elif isinstance(action, GeneratePlanTool):
            updates["research_goal"] = action.research_goal
            logger.info(f"Research goal set: {action.research_goal}")

        elif isinstance(action, AdaptPlanTool):
            updates["research_goal"] = action.new_goal
            logger.info(f"Plan adapted: {action.new_goal}")

        elif isinstance(action, CreateReportTool):
            updates["final_report"] = action.content
            updates["agent_state"] = "completed"
            logger.info(f"Report created: {len(action.content)} chars")

        elif isinstance(action, ReasoningTool):
            logger.debug(f"Reasoning: {action.reasoning_steps}")
            logger.debug(f"Enough data: {action.enough_data}")

        elif isinstance(action, FinalAnswerTool):
            updates["agent_state"] = "completed"
            # Create minimal report with the message
            updates["final_report"] = action.message
            logger.info(f"Final answer: {action.message}")

        # Build conversation history with emulated tool_calls
        tool_call_id = ai_message_with_tool_call.tool_calls[0]["id"]

        tool_message = ToolMessage(
            content=self._format_tool_result(action, execution_result),
            tool_call_id=tool_call_id,
        )

        updates["decision_history"] = research_state.decision_history + [
            ai_message_with_tool_call,
            tool_message,
        ]

        return updates

    def _should_continue(self, research_state: ResearchState) -> bool:
        """Check if agent should continue iterations."""
        if research_state.agent_state == "completed":
            return False
        if research_state.iteration >= self.settings.research_max_iterations:
            return False
        return True

    async def _run_iteration(self, research_state: ResearchState) -> ResearchState:
        """
        Run single iteration of research agent.

        Args:
            research_state: Current internal state

        Returns:
            Updated ResearchState
        """
        # Get action and ai_message with tool_calls
        action, ai_message = await self._select_action(research_state)

        # Execute action
        updates = await self._execute_action(action, ai_message, research_state)

        # Create new state with updates
        new_state_data = research_state.model_dump()
        new_state_data.update(updates)
        new_state_data["iteration"] = research_state.iteration + 1

        return ResearchState(**new_state_data)

    async def _force_report(self, research_state: ResearchState) -> ResearchState:
        """Force report creation when max iterations reached."""
        logger.warning("Max iterations reached, forcing report creation...")

        messages = self._build_messages(research_state)
        llm = self.model.with_structured_output(CreateReportTool)
        report_action = await llm.ainvoke(messages)

        # Emulate tool_calls for forced report
        ai_message = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "CreateReportTool",
                    "args": report_action.model_dump(),
                    "id": f"call_{research_state.iteration}_forced",
                }
            ],
        )

        tool_message = ToolMessage(
            content=f"Report created ({len(report_action.content)} chars)",
            tool_call_id=f"call_{research_state.iteration}_forced",
        )

        new_state_data = research_state.model_dump()
        new_state_data.update(
            {
                "final_report": report_action.content,
                "agent_state": "completed",
                "decision_history": research_state.decision_history
                + [ai_message, tool_message],
            }
        )

        return ResearchState(**new_state_data)

    async def __call__(self, state: GeneralState, config) -> Command:
        """
        Main entry point for research agent.

        Runs the complete research loop and returns results to workflow.

        Args:
            state: Current workflow state
            config: LangGraph configuration

        Returns:
            Command with goto to planning_structure and research results
        """
        thread_id = config["configurable"]["thread_id"]
        logger.info(f"Starting research agent for thread {thread_id}")

        # Initialize system prompt from Prompt Config Service (cached for session)
        await self._init_system_prompt(state, config)

        # Initialize internal research state
        research_state = ResearchState(input_content=state.input_content)

        # Run iteration loop
        while self._should_continue(research_state):
            research_state = await self._run_iteration(research_state)

            logger.info(
                f"Research iteration {research_state.iteration}: "
                f"searches={research_state.searches_used}, "
                f"extractions={research_state.extractions_used}, "
                f"sources={len(research_state.sources)}"
            )

        # Force report if not completed
        if not research_state.final_report:
            research_state = await self._force_report(research_state)

        logger.info(
            f"Research completed for thread {thread_id}: "
            f"iterations={research_state.iteration}, "
            f"sources={len(research_state.sources)}, "
            f"report_length={len(research_state.final_report or '')}"
        )

        # Convert sources to dict for state storage
        sources_dict = {
            url: source.model_dump() for url, source in research_state.sources.items()
        }

        # Return to workflow with results
        return Command(
            goto="planning_structure",
            update={
                "research_report": research_state.final_report,
                "research_sources": sources_dict,
            },
        )
