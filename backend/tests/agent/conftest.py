"""Local fixtures/helpers for the agent-runtime scope (S3).

Shared building blocks for graph / runner tests: a tool-binding fake model, the
real agent/prompt config loaded from ``configs/``, an in-memory checkpointer +
store, and small recording stubs for the prompt provider.

NOTE (harness gap, see runlog § "Баги для Ф5"): the frozen harness
``fake_chat_model`` returns a bare ``GenericFakeChatModel`` whose ``bind_tools``
is unimplemented (raises ``NotImplementedError``). ``build_graph`` /
``GraphFactory.build`` call ``model.bind_tools(tools)`` on the injected model, so
the advertised seam ``GraphFactory(model_factory=model_factory(fake))`` cannot
drive the graph as-is. ``tool_binding_fake`` below is the local adapter that
unblocks graph tests without touching the frozen package.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import pytest
from app.agent.config import (
    AgentConfig,
    PromptFragmentsConfig,
    load_agent_config,
    load_prompt_fragments,
)
from app.agent.graph import AgentContext, build_graph, compile_graph
from app.agent.security.types import SecurityMessages
from app.infra.prompt_provider import PromptProvider
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.memory import InMemoryStore


class ToolBindingFakeChatModel(GenericFakeChatModel):
    """``GenericFakeChatModel`` that answers ``bind_tools`` (returns itself).

    Tool schemas are irrelevant to a replay fake, so binding is a no-op; the
    programmed message iterator still drives the ReAct loop deterministically.
    """

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        return self


class RaisingFakeChatModel(ToolBindingFakeChatModel):
    """Tool-binding fake whose ``ainvoke`` raises — the model-failure branch."""

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("simulated upstream connection failure")


def tool_binding_fake(
    responses: Iterable[AIMessage | str],
) -> ToolBindingFakeChatModel:
    """Replay fake usable through ``build_graph`` (``bind_tools`` works)."""
    messages: list[AIMessage] = [
        m if isinstance(m, AIMessage) else AIMessage(content=m) for m in responses
    ]
    return ToolBindingFakeChatModel(messages=iter(messages))


class RecordingPromptProvider(PromptProvider):
    """Recording stub ``PromptProvider``: records ``get_prompt`` calls + marker.

    Subclasses the concrete ``PromptProvider`` (which is not a Protocol) so it
    types cleanly where one is expected, but overrides ``__init__`` to skip the
    Langfuse/file wiring. The returned string embeds the section slot values so
    composition can be asserted without reaching into private state.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get_prompt(self, name: str, **variables: str) -> str:
        self.calls.append((name, dict(variables)))
        joined = "|".join(f"{k}={v}" for k, v in variables.items())
        return f"PROMPT[{name}]{joined}"

    def get_config(self, name: str) -> dict[str, Any] | None:
        return None


@pytest.fixture
def agent_config() -> AgentConfig:
    return load_agent_config()


@pytest.fixture
def agent_config_no_summarization() -> AgentConfig:
    """Agent config with summarization disabled.

    ``GraphFactory.build`` constructs the summarization client via the real
    ``create_summarization_llm`` (it is not routed through the injectable
    ``model_factory`` seam), which needs live ``Settings``. Disabling it keeps
    factory/runner tests free of a real model client.
    """
    return load_agent_config().model_copy(update={"summarization": None})


@pytest.fixture
def prompt_fragments() -> PromptFragmentsConfig:
    return load_prompt_fragments()


@pytest.fixture
def security_messages() -> SecurityMessages:
    return SecurityMessages()


@pytest.fixture
def stub_prompt_provider() -> RecordingPromptProvider:
    return RecordingPromptProvider()


@pytest.fixture
def checkpointer() -> InMemorySaver:
    """Fresh in-memory checkpointer per test (official LangGraph test pattern)."""
    return InMemorySaver()


@pytest.fixture
def store() -> InMemoryStore:
    """Fresh in-memory store per test (the agent node requires a Store)."""
    return InMemoryStore()


@pytest.fixture
def agent_context() -> AgentContext:
    return AgentContext(project_id="proj-1", user_id="user-1", canary_token="")


GraphBuilderFn = Any


@pytest.fixture
def build_compiled_graph(
    agent_config_no_summarization: AgentConfig,
    prompt_fragments: PromptFragmentsConfig,
    security_messages: SecurityMessages,
    checkpointer: InMemorySaver,
    store: InMemoryStore,
) -> GraphBuilderFn:
    """Fixture-factory: build + compile a graph driven by an injected fake model.

    Wraps the real ``build_graph``/``compile_graph`` with the in-memory
    checkpointer + store so each test supplies only the programmed model, tools,
    and optional guard. ``interrupt_after`` exposes the HITL pause point.
    """

    def _build(
        model: Any,
        *,
        tools: list[Any] | None = None,
        security_guard: Any | None = None,
        interrupt_after: list[str] | None = None,
    ) -> CompiledStateGraph[Any, Any, Any, Any]:
        builder = build_graph(
            model=model,
            tools=tools or [],
            agent_config=agent_config_no_summarization,
            prompt_fragments=prompt_fragments,
            security_messages=security_messages,
            security_guard=security_guard,
        )
        if interrupt_after is not None:
            return builder.compile(
                checkpointer=checkpointer,
                store=store,
                interrupt_after=interrupt_after,
            )
        return compile_graph(builder, checkpointer=checkpointer, store=store)

    return _build
