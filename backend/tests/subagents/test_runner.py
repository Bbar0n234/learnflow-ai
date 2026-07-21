"""Behavior tests for ``SubagentRunner.run`` — the subagent-as-tool core.

The Runner resolves a spec, builds the model + prompt, assembles the input
(``task`` + attributed documents), compiles the graph per invocation and runs
it. We drive it against the real ``configs/`` registry with the model seam
faked (``create_llm_from_config`` monkeypatched to a ``CapturingModel``) — no
network, key or non-determinism. Two assertion styles:

- through the *real* graph + a capturing model whose answers carry no tool
  calls (the run ends after one super-step), to observe the assembled
  ``[system, human]`` the subagent LLM actually sees (context cleanliness:
  system = spec prompt only, human = task + wrapped docs, no session
  history);
- through a *spy* compiled graph, to observe the ``ainvoke`` config the Runner
  builds (subagent tag, recursion limit) and the ``checkpointer`` it compiles
  with — invariants that live in the Runner, not the graph.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from app.agent.config import (
    AgentConfig,
    ContextConfig,
    ImageConfig,
    LLMConfig,
    ResolvedModelConfig,
    SubagentsConfig,
    SubagentSpec,
)
from app.agent.subagents.runner import (
    SUBAGENT_TAG,
    SubagentDocument,
    SubagentRunner,
    UnknownSubagentTypeError,
)
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool

from tests.subagents.conftest import CapturingModel, RecordingPromptProvider

pytestmark = pytest.mark.unit


@tool
def firecrawl_search(query: str) -> str:
    """Fake firecrawl_search standing in for the built-in MCP tool."""
    return f"results for {query}"


@tool
def firecrawl_scrape(url: str) -> str:
    """Fake firecrawl_scrape standing in for the built-in MCP tool."""
    return f"page at {url}"


@tool
def firecrawl_extract(url: str) -> str:
    """Fake firecrawl_extract standing in for the built-in MCP tool."""
    return f"data from {url}"


def _fake_firecrawl_pool() -> dict[str, Any]:
    """A pool resolving the real registry's tool names (all specs use these)."""
    return {t.name: t for t in (firecrawl_search, firecrawl_scrape, firecrawl_extract)}


def _make_runner(
    monkeypatch: pytest.MonkeyPatch,
    agent_config: AgentConfig,
    prompt_fragments: Any,
    prompt_provider: RecordingPromptProvider,
    model: Any,
    *,
    tool_pool: dict[str, Any] | None = None,
    captured: dict[str, Any] | None = None,
) -> SubagentRunner:
    """Build a Runner with the model seam faked.

    ``create_llm_from_config`` is replaced so ``run`` gets ``model`` instead of
    a live client; ``captured["model_config"]`` records the resolved config the
    Runner passed, so the default-vs-override cascade is observable. The tool
    pool defaults to fake firecrawl tools so the real registry's specs (all of
    which declare the firecrawl trio) resolve.
    """

    def _fake_create_llm(_settings: Any, model_config: ResolvedModelConfig) -> Any:
        if captured is not None:
            captured["model_config"] = model_config
        return model

    monkeypatch.setattr(
        "app.agent.subagents.runner.create_llm_from_config", _fake_create_llm
    )
    return SubagentRunner(
        agent_config=agent_config,
        prompt_fragments=prompt_fragments,
        prompt_provider=prompt_provider,
        settings=cast(Any, object()),  # only forwarded to the (faked) model factory
        tool_pool=tool_pool if tool_pool is not None else _fake_firecrawl_pool(),
    )


# --- input assembly / context cleanliness -----------------------------------


async def test_judge_run_assembles_system_prompt_and_wrapped_document(
    monkeypatch: pytest.MonkeyPatch,
    agent_config: AgentConfig,
    prompt_fragments: Any,
    prompt_provider: RecordingPromptProvider,
) -> None:
    model = CapturingModel([AIMessage(content="VERDICT: 2 issues")])
    runner = _make_runner(
        monkeypatch, agent_config, prompt_fragments, prompt_provider, model
    )

    result = await runner.run(
        "judge",
        "Review for anti-slop violations.",
        [SubagentDocument(id="doc-1", title="Draft", content="Body text.")],
    )

    # Runner returns the subagent graph's final text verbatim.
    assert result == "VERDICT: 2 issues"

    # The subagent LLM saw exactly [system, human] — no session history.
    (sent,) = model.invocations
    assert [type(m).__name__ for m in sent] == ["SystemMessage", "HumanMessage"]
    system, human = sent
    assert isinstance(system, SystemMessage)
    # System is the spec prompt alone (recorded marker), no KS/memory/skills.
    assert system.content == "PROMPT[subagent-judge]"
    assert prompt_provider.calls == ["subagent-judge"]
    # Human = task + the document in the ``document`` wrapper with id/title.
    assert isinstance(human, HumanMessage)
    assert human.content == (
        "Review for anti-slop violations.\n\n"
        '<document id="doc-1" title="Draft">\nBody text.\n</document>'
    )


async def test_run_preserves_document_order_and_escapes_attribute_quotes(
    monkeypatch: pytest.MonkeyPatch,
    agent_config: AgentConfig,
    prompt_fragments: Any,
    prompt_provider: RecordingPromptProvider,
) -> None:
    model = CapturingModel([AIMessage(content="ok")])
    runner = _make_runner(
        monkeypatch, agent_config, prompt_fragments, prompt_provider, model
    )

    await runner.run(
        "general-purpose",
        "Compare the two.",
        [
            SubagentDocument(id="a", title='Draft "v1"', content="first"),
            SubagentDocument(id="b", title="Outline", content="second"),
        ],
    )

    (_, human) = model.invocations[0]
    # Order follows the list; the quote in the title is escaped so it cannot
    # break out of the attribute.
    assert human.content == (
        "Compare the two.\n\n"
        '<document id="a" title="Draft &quot;v1&quot;">\nfirst\n</document>\n\n'
        '<document id="b" title="Outline">\nsecond\n</document>'
    )


async def test_run_without_documents_sends_task_only(
    monkeypatch: pytest.MonkeyPatch,
    agent_config: AgentConfig,
    prompt_fragments: Any,
    prompt_provider: RecordingPromptProvider,
) -> None:
    model = CapturingModel([AIMessage(content="ok")])
    runner = _make_runner(
        monkeypatch, agent_config, prompt_fragments, prompt_provider, model
    )

    await runner.run("general-purpose", "Just a short instruction.")

    (_, human) = model.invocations[0]
    assert human.content == "Just a short instruction."


# --- spec resolution --------------------------------------------------------


async def test_unknown_agent_type_raises_with_sorted_available_types(
    monkeypatch: pytest.MonkeyPatch,
    agent_config: AgentConfig,
    prompt_fragments: Any,
    prompt_provider: RecordingPromptProvider,
) -> None:
    runner = _make_runner(
        monkeypatch,
        agent_config,
        prompt_fragments,
        prompt_provider,
        CapturingModel([AIMessage(content="never")]),
    )

    with pytest.raises(UnknownSubagentTypeError) as exc_info:
        await runner.run("nope", "task")

    # Carries the valid options (sorted) so the calling tool can report them.
    assert exc_info.value.available_types == [
        "general-purpose",
        "judge",
        "web-research",
    ]
    assert "nope" in str(exc_info.value)


# --- model cascade ----------------------------------------------------------


async def test_run_uses_subagents_llm_default_when_spec_has_no_override(
    monkeypatch: pytest.MonkeyPatch,
    agent_config: AgentConfig,
    prompt_fragments: Any,
    prompt_provider: RecordingPromptProvider,
) -> None:
    captured: dict[str, Any] = {}
    runner = _make_runner(
        monkeypatch,
        agent_config,
        prompt_fragments,
        prompt_provider,
        CapturingModel([AIMessage(content="ok")]),
        captured=captured,
    )

    await runner.run("judge", "task")

    # judge declares no ``model`` — falls back to the global subagents default.
    assert agent_config.subagents is not None
    assert captured["model_config"].model == agent_config.subagents.llm.model


async def test_run_uses_per_spec_model_override_when_present(
    monkeypatch: pytest.MonkeyPatch,
    prompt_fragments: Any,
    prompt_provider: RecordingPromptProvider,
) -> None:
    # A synthetic registry with a per-spec ``model`` override.
    config = AgentConfig(
        llm=LLMConfig(model="main-model"),
        context=_min_context(),
        image=_min_image(),
        subagents=SubagentsConfig(
            llm=LLMConfig(model="default-subagent-model"),
            registry=[
                SubagentSpec(
                    name="custom",
                    description="d",
                    prompt="subagent-judge",
                    model="override-model",
                    tools=["firecrawl_search"],
                ),
            ],
        ),
    )
    captured: dict[str, Any] = {}
    runner = _make_runner(
        monkeypatch,
        config,
        prompt_fragments,
        prompt_provider,
        CapturingModel([AIMessage(content="ok")]),
        captured=captured,
    )

    await runner.run("custom", "task")

    assert captured["model_config"].model == "override-model"


# --- ainvoke config: subagent tag + recursion limit + checkpointer ----------


class _SpyCompiled:
    """Spy compiled graph: records ``ainvoke`` input/config, returns canned."""

    def __init__(self) -> None:
        self.config: Any = None
        self.input: Any = None

    async def ainvoke(self, input: Any, config: Any = None) -> dict[str, Any]:
        self.input = input
        self.config = config
        return {"messages": [AIMessage(content="spy-result")]}


def _install_spy_compile(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[_SpyCompiled, dict[str, Any]]:
    spy = _SpyCompiled()
    captured: dict[str, Any] = {}

    def _fake_compile(_builder: Any, *, checkpointer: Any) -> _SpyCompiled:
        captured["checkpointer"] = checkpointer
        return spy

    monkeypatch.setattr(
        "app.agent.subagents.runner.compile_subagent_graph", _fake_compile
    )
    return spy, captured


async def test_run_stamps_subagent_tag_and_recursion_limit_on_config(
    monkeypatch: pytest.MonkeyPatch,
    agent_config: AgentConfig,
    prompt_fragments: Any,
    prompt_provider: RecordingPromptProvider,
) -> None:
    spy, _ = _install_spy_compile(monkeypatch)
    runner = _make_runner(
        monkeypatch,
        agent_config,
        prompt_fragments,
        prompt_provider,
        CapturingModel([AIMessage(content="unused")]),
    )

    result = await runner.run(
        "judge", "task", config={"tags": ["main-graph"], "metadata": {"k": "v"}}
    )

    assert result == "spy-result"
    # The subagent tag is appended without dropping caller tags/metadata — the
    # stream loop filters on this tag to keep subagent tokens out of the chat.
    assert spy.config["tags"] == ["main-graph", SUBAGENT_TAG]
    assert spy.config["metadata"] == {"k": "v"}
    # The ReAct loop is bounded so a subagent with tools cannot spin forever;
    # the bound is the operational knob from agent.yaml § subagents.
    assert agent_config.subagents is not None
    assert spy.config["recursion_limit"] == agent_config.subagents.recursion_limit


async def test_run_recursion_limit_comes_from_config(
    monkeypatch: pytest.MonkeyPatch,
    agent_config: AgentConfig,
    prompt_fragments: Any,
    prompt_provider: RecordingPromptProvider,
) -> None:
    """A non-default ``subagents.recursion_limit`` reaches the invoke config."""
    spy, _ = _install_spy_compile(monkeypatch)
    custom_config = agent_config.model_copy(deep=True)
    assert custom_config.subagents is not None
    custom_config.subagents.recursion_limit = 7
    runner = _make_runner(
        monkeypatch,
        custom_config,
        prompt_fragments,
        prompt_provider,
        CapturingModel([AIMessage(content="unused")]),
    )

    await runner.run("judge", "task")

    assert spy.config["recursion_limit"] == 7


async def test_run_compiles_with_checkpointer_false_for_persistence_none(
    monkeypatch: pytest.MonkeyPatch,
    agent_config: AgentConfig,
    prompt_fragments: Any,
    prompt_provider: RecordingPromptProvider,
) -> None:
    _, captured = _install_spy_compile(monkeypatch)
    runner = _make_runner(
        monkeypatch,
        agent_config,
        prompt_fragments,
        prompt_provider,
        CapturingModel([AIMessage(content="unused")]),
    )

    await runner.run("judge", "task")

    # persistence: none -> checkpointer=False -> zero writes to PG.
    assert captured["checkpointer"] is False


# --- anti-recursion invariant -----------------------------------------------


async def test_run_subagent_is_excluded_from_the_tool_pool(
    monkeypatch: pytest.MonkeyPatch,
    prompt_fragments: Any,
    prompt_provider: RecordingPromptProvider,
) -> None:
    """``run_subagent`` never resolves into a subagent's toolset.

    The Runner pops it from the pool in ``__init__`` regardless of config, so a
    spec that lists it cannot wire recursion. Observable consequence: resolving
    that spec's tools misses ``run_subagent`` (``KeyError``) instead of handing
    the subagent a delegation tool.
    """
    fake_run_subagent = _NamedTool("run_subagent")
    config = AgentConfig(
        llm=LLMConfig(model="m"),
        context=_min_context(),
        image=_min_image(),
        subagents=SubagentsConfig(
            llm=LLMConfig(model="sub"),
            registry=[
                SubagentSpec(
                    name="recursive",
                    description="d",
                    prompt="subagent-judge",
                    tools=["run_subagent"],
                ),
            ],
        ),
    )
    runner = _make_runner(
        monkeypatch,
        config,
        prompt_fragments,
        prompt_provider,
        CapturingModel([AIMessage(content="never")]),
        tool_pool={"run_subagent": fake_run_subagent},
    )

    with pytest.raises(KeyError, match="run_subagent"):
        await runner.run("recursive", "task")


# --- tiny helpers -----------------------------------------------------------


class _NamedTool:
    def __init__(self, name: str) -> None:
        self.name = name


def _min_context() -> ContextConfig:
    return ContextConfig(max_tokens=8000)


def _min_image() -> ImageConfig:
    return ImageConfig(model="img")
