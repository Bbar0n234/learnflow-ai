"""Local fixtures/helpers for the subagents scope (feat-011, T1).

Building blocks shared across the subagent runner / graph / tool tests:

- the real ``configs/`` agent + prompt-fragment config (``agent_config`` /
  ``prompt_fragments``) so specs, the ``subagents.llm`` default and the
  ``document`` wrapper are exercised as shipped, not re-declared;
- a recording ``PromptProvider`` stub whose output embeds the requested name,
  so "the spec's prompt (and only it) reached the system message" is
  assertable without a live Langfuse/file lookup;
- duck-typed fakes for the two seams the runner/graph program against — the
  chat model (``CapturingModel`` / ``ScriptedToolModel`` /
  ``InfiniteToolCallModel``) and the security guard (``SelectiveGuard``).

T1.5: the real-Postgres transactional harness the ``run_subagent`` tool used
to need for its old UUID-keyed artifact fetch (``tool_session_factory`` /
``seed_session`` / ``outer_conn``) is gone along with that mechanism — the
tool now resolves ``input_artifact_paths`` through the workspace file layer
(``Workspace``), not a DB session.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

import pytest
from app.agent.config import (
    AgentConfig,
    PromptFragmentsConfig,
    load_agent_config,
    load_prompt_fragments,
)
from app.agent.security.types import (
    Checkpoint,
    Direction,
    GuardResult,
    Verdict,
    direction_of,
)
from app.agent.subagents.graph import build_subagent_graph, compile_subagent_graph
from app.infra.prompt_provider import PromptProvider
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool

# --- config fixtures --------------------------------------------------------


@pytest.fixture
def agent_config() -> AgentConfig:
    """Real ``configs/agent.yaml`` — includes the ``subagents`` section."""
    return load_agent_config()


@pytest.fixture
def prompt_fragments() -> PromptFragmentsConfig:
    """Real ``configs/prompt_fragments.yaml`` — includes the ``document`` wrapper."""
    return load_prompt_fragments()


# --- prompt provider stub ---------------------------------------------------


class RecordingPromptProvider(PromptProvider):
    """Recording stub: records ``get_prompt`` names, returns a marker string.

    Subclasses the concrete ``PromptProvider`` (not a Protocol) so it types
    cleanly where one is expected, but skips the Langfuse/file wiring. The
    returned ``PROMPT[<name>]`` marker lets a test assert *which* prompt the
    Runner fetched and that exactly that text became the subagent's system
    message — without reaching into private state.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_prompt(self, name: str, **variables: str) -> str:
        self.calls.append(name)
        return f"PROMPT[{name}]"

    def get_config(self, name: str) -> dict[str, Any] | None:
        return None


@pytest.fixture
def prompt_provider() -> RecordingPromptProvider:
    return RecordingPromptProvider()


# --- chat-model fakes (duck-typed against BaseChatModel's used surface) ------


class CapturingModel:
    """Replays scripted responses and records every ``ainvoke`` message list.

    Duck-types the two methods the subagent graph calls on a model:
    ``bind_tools`` (ReAct form) and ``ainvoke``. ``invocations`` captures the
    exact ``[system, *messages]`` list each turn, so a test can assert the
    system message is the spec prompt alone and the human message is the
    assembled ``task`` + wrapped documents.
    """

    def __init__(self, responses: Iterable[AIMessage | str]) -> None:
        self._responses = iter(
            m if isinstance(m, AIMessage) else AIMessage(content=m) for m in responses
        )
        self.invocations: list[list[BaseMessage]] = []
        self.bound_tools: Any = None

    def bind_tools(self, tools: Any, **_kwargs: Any) -> CapturingModel:
        self.bound_tools = tools
        return self

    async def ainvoke(self, messages: list[BaseMessage], **_kwargs: Any) -> AIMessage:
        self.invocations.append(list(messages))
        return next(self._responses)


class ScriptedToolModel(CapturingModel):
    """``CapturingModel`` whose responses drive a ReAct loop (tool_calls)."""


class InfiniteToolCallModel:
    """Always answers with the same tool call — never terminates on its own.

    Used to prove ``recursion_limit`` bounds a runaway subagent tool loop
    (the graph must raise ``GraphRecursionError``, not spin forever).
    """

    def __init__(self, tool_name: str) -> None:
        self._tool_name = tool_name
        self.bound_tools: Any = None

    def bind_tools(self, tools: Any, **_kwargs: Any) -> InfiniteToolCallModel:
        self.bound_tools = tools
        return self

    async def ainvoke(self, _messages: list[BaseMessage], **_kwargs: Any) -> AIMessage:
        return AIMessage(
            content="",
            tool_calls=[{"name": self._tool_name, "args": {}, "id": "loop"}],
        )


# --- security guard stub ----------------------------------------------------


class SelectiveGuard:
    """Stub guard returning a per-checkpoint verdict; records checkpoints seen.

    Lets a test pass tool-call args through (CLEAN) while flagging the tool
    result (INJECTION) — isolating the ``TOOL_RESULT`` redact branch from the
    ``TOOL_CALL_ARG`` strip branch. Matches ``SecurityGuard.check`` by duck
    typing (tests the code's *reaction* to a verdict, never the verdict's
    quality — that is an eval concern).
    """

    def __init__(self, verdicts: dict[Checkpoint, Verdict] | None = None) -> None:
        self._verdicts = verdicts or {}
        self.checkpoints: list[Checkpoint] = []

    async def check(
        self, content: str, checkpoint: Checkpoint, **_kwargs: Any
    ) -> GuardResult:
        self.checkpoints.append(checkpoint)
        try:
            direction = direction_of(checkpoint)
        except KeyError:
            direction = Direction.INBOUND
        return GuardResult(
            verdict=self._verdicts.get(checkpoint, Verdict.CLEAN),
            checkpoint=checkpoint,
            direction=direction,
        )


@pytest.fixture
def subagent_react_graph() -> Callable[..., Any]:
    """Fixture-factory: build + compile a ReAct subagent graph.

    Wraps ``build_subagent_graph`` (non-empty tools) + ``compile_subagent_graph``
    (checkpointer=False) so a test supplies only the model, tools, guard and
    stub. The guard/canary/stub are the seam the in-cycle checks run through.
    """

    def _build(
        *,
        model: Any,
        tools: list[BaseTool],
        guard: Any,
        stub: str = "[REDACTED]",
        system_prompt: str = "sys",
        max_tokens: int = 8000,
    ) -> Any:
        builder = build_subagent_graph(
            model=model,
            system_prompt=system_prompt,
            tools=tools,
            max_tokens=max_tokens,
            security_guard=guard,
            canary_token="canary-x",
            tool_result_stub=stub,
        )
        return compile_subagent_graph(builder, checkpointer=False)

    return _build
