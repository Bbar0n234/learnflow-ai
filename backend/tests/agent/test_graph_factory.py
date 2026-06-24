"""Unit: ``GraphFactory`` — the injectable model-factory seam.

The factory builds a per-request compiled graph. The seam under test is
``model_factory``: tests override it to return a fake chat model, and the default
must remain the production ``create_llm_from_config`` (so prod behavior is
unchanged). We verify through the public ``build()`` — the returned graph is run
on the fake — never by reading private attributes.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from app.agent import graph_factory as gf_module
from app.agent.config import (
    AgentConfig,
    PromptFragmentsConfig,
    ResolvedModelConfig,
    load_agent_config,
)
from app.agent.graph import AgentContext
from app.agent.graph_factory import GraphFactory
from app.agent.security.types import SecurityMessages
from app.config import Settings
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from tests.agent.conftest import RecordingPromptProvider, tool_binding_fake


@tool
def ping(text: str) -> str:
    """Return pong for the given text."""
    return "pong"


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def model_config() -> ResolvedModelConfig:
    return ResolvedModelConfig(model="fake-model", extra_body=None, source="config")


def _make_factory(
    settings: Settings,
    agent_config: AgentConfig,
    prompt_fragments: PromptFragmentsConfig,
    security_messages: SecurityMessages,
    checkpointer: Any,
    store: Any,
    *,
    global_tools: list[Any] | None = None,
    model_factory: Any = None,
) -> GraphFactory:
    return GraphFactory(
        settings=settings,
        agent_config=agent_config,
        prompt_fragments=prompt_fragments,
        security_messages=security_messages,
        global_tools=global_tools or [],
        skills_index="",
        checkpointer=checkpointer,
        store=store,
        prompt_provider=RecordingPromptProvider(),
        security_guard=None,
        model_factory=model_factory,
    )


@pytest.mark.unit
async def test_build_uses_injected_model_factory(
    settings: Settings,
    agent_config_no_summarization: AgentConfig,
    prompt_fragments: PromptFragmentsConfig,
    security_messages: SecurityMessages,
    checkpointer: Any,
    store: Any,
    model_config: ResolvedModelConfig,
    agent_context: AgentContext,
) -> None:
    fake = tool_binding_fake([AIMessage(content="from injected fake")])

    factory = _make_factory(
        settings,
        agent_config_no_summarization,
        prompt_fragments,
        security_messages,
        checkpointer,
        store,
        model_factory=lambda s, mc: fake,
    )
    graph = factory.build(model_config)
    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="hi")]},
        {"configurable": {"thread_id": str(uuid.uuid4())}},
        context=agent_context,
    )

    assert out["messages"][-1].content == "from injected fake"


@pytest.mark.unit
async def test_default_model_factory_is_production_create_llm(
    monkeypatch: pytest.MonkeyPatch,
    settings: Settings,
    agent_config_no_summarization: AgentConfig,
    prompt_fragments: PromptFragmentsConfig,
    security_messages: SecurityMessages,
    checkpointer: Any,
    store: Any,
    model_config: ResolvedModelConfig,
    agent_context: AgentContext,
) -> None:
    # With no override, build() must route model creation through the module's
    # ``create_llm_from_config`` (the production factory). Patch it to a fake and
    # prove the graph runs that fake.
    sentinel = tool_binding_fake([AIMessage(content="prod-default-path")])

    def _fake_create(s: Settings, mc: ResolvedModelConfig) -> BaseChatModel:
        return sentinel

    monkeypatch.setattr(gf_module, "create_llm_from_config", _fake_create)

    factory = _make_factory(
        settings,
        agent_config_no_summarization,
        prompt_fragments,
        security_messages,
        checkpointer,
        store,
        model_factory=None,  # use the default
    )
    graph = factory.build(model_config)
    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="hi")]},
        {"configurable": {"thread_id": str(uuid.uuid4())}},
        context=agent_context,
    )

    assert out["messages"][-1].content == "prod-default-path"


@pytest.mark.unit
async def test_extra_tools_are_added_on_top_of_global_tools(
    settings: Settings,
    agent_config_no_summarization: AgentConfig,
    prompt_fragments: PromptFragmentsConfig,
    security_messages: SecurityMessages,
    checkpointer: Any,
    store: Any,
    model_config: ResolvedModelConfig,
    agent_context: AgentContext,
) -> None:
    model = tool_binding_fake(
        [
            AIMessage(
                content="",
                tool_calls=[{"name": "ping", "args": {"text": "x"}, "id": "c1"}],
            ),
            AIMessage(content="done"),
        ]
    )
    factory = _make_factory(
        settings,
        agent_config_no_summarization,
        prompt_fragments,
        security_messages,
        checkpointer,
        store,
        global_tools=[],
        model_factory=lambda s, mc: model,
    )

    graph = factory.build(model_config, extra_tools=[ping])
    out = await graph.ainvoke(
        {"messages": [HumanMessage(content="call ping")]},
        {"configurable": {"thread_id": str(uuid.uuid4())}},
        context=agent_context,
    )

    # The per-request extra tool resolved and executed -> proves it was wired in.
    assert any(
        isinstance(m, ToolMessage) and m.content == "pong" for m in out["messages"]
    )


@pytest.mark.unit
def test_build_without_summarization_does_not_need_a_real_client(
    settings: Settings,
    prompt_fragments: PromptFragmentsConfig,
    security_messages: SecurityMessages,
    checkpointer: Any,
    store: Any,
    model_config: ResolvedModelConfig,
) -> None:
    config_no_sum = load_agent_config().model_copy(update={"summarization": None})
    factory = _make_factory(
        settings,
        config_no_sum,
        prompt_fragments,
        security_messages,
        checkpointer,
        store,
        model_factory=lambda s, mc: tool_binding_fake([AIMessage(content="ok")]),
    )

    graph = factory.build(model_config)  # must not construct a summarization LLM

    assert {"agent", "tools"} <= set(graph.nodes)
