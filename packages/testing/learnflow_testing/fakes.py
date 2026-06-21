"""Deterministic fakes for the LLM seam and the security guard.

These let graph/guard logic run without network, API key, or non-determinism.
The agent code is programmed against ``BaseChatModel`` / a guard protocol, so any
fake with the same surface drops into the seam (duck typing + ``Protocol``).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from app.agent.security.types import (
    Checkpoint,
    Direction,
    GuardResult,
    Verdict,
    direction_of,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage


def ai_message(
    content: str = "", tool_calls: list[dict[str, Any]] | None = None
) -> AIMessage:
    """Build a programmable assistant turn for the fake model.

    ``tool_calls`` drives the ReAct loop (model -> tool -> model -> answer); each
    entry is a LangChain ToolCall dict ``{"name", "args", "id"}``.
    """
    return AIMessage(content=content, tool_calls=tool_calls or [])


def fake_chat_model(responses: Iterable[BaseMessage | str]) -> BaseChatModel:
    """A ``GenericFakeChatModel`` that replays ``responses`` in order.

    Accepts ready ``BaseMessage`` objects (use :func:`ai_message` for tool_calls)
    or plain strings (coerced to ``AIMessage``). Supports streaming and
    ``tool_calls`` — the right fake for agent-node / graph / routing tests.
    """
    messages = [
        m if isinstance(m, BaseMessage) else AIMessage(content=m) for m in responses
    ]
    return GenericFakeChatModel(messages=iter(messages))


def model_factory(model: BaseChatModel) -> Any:
    """Adapt a ready model into a ``GraphFactory`` model-factory callable.

    ``GraphFactory(model_factory=model_factory(fake))`` makes ``build()`` use the
    fake instead of ``create_llm_from_config`` — no production change, no
    module-level state.
    """

    def _factory(settings: Any, model_config: Any) -> BaseChatModel:
        return model

    return _factory


def guard_classifier_model(verdict: Verdict) -> BaseChatModel:
    """Fake LLM for the guard classifier: returns the verdict as flat text.

    The classifier reads ``str(response.content).strip().upper()`` against
    ``{CLEAN, SUSPICIOUS, INJECTION}`` — no structured output. So the fake is a
    plain ``AIMessage(content="INJECTION")``.
    """
    return fake_chat_model([AIMessage(content=verdict.value)])


def garbage_classifier_model(raw: str = "GARBAGE") -> BaseChatModel:
    """Fake classifier LLM returning an unparseable verdict.

    Exercises the retry-then-degrade-to-CLEAN branch (``degraded=True``).
    """
    return fake_chat_model([AIMessage(content=raw)] * 16)


class _RaisingModel(GenericFakeChatModel):
    """Fake LLM whose ``ainvoke`` raises — models the model-failure branch."""

    async def ainvoke(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("simulated LLM failure")


def raising_classifier_model() -> BaseChatModel:
    """Fake classifier LLM that fails — guard degrades to CLEAN."""
    return _RaisingModel(messages=iter([AIMessage(content="")]))


class StubGuard:
    """Stub security guard returning a fixed ``GuardResult`` per ``check``.

    Tests the *reaction* of our code to a verdict (block/redact on INJECTION,
    observability on SUSPICIOUS, pass on CLEAN) — not the quality of the verdict,
    which is an eval concern. Matches ``SecurityGuard.check`` by duck typing.
    """

    def __init__(self, verdict: Verdict = Verdict.CLEAN) -> None:
        self.verdict = verdict
        self.calls: list[tuple[str, Checkpoint]] = []

    async def check(
        self,
        content: str,
        checkpoint: Checkpoint,
        *,
        history: Sequence[BaseMessage] | None = None,
        canary_token: str | None = None,
        skip_classifier: bool = False,
        observe: bool = True,
        trace_ctx: dict[str, Any] | None = None,
    ) -> GuardResult:
        self.calls.append((content, checkpoint))
        return GuardResult(
            verdict=self.verdict,
            checkpoint=checkpoint,
            direction=_safe_direction(checkpoint),
        )


def _safe_direction(checkpoint: Checkpoint) -> Direction:
    try:
        return direction_of(checkpoint)
    except KeyError:
        return Direction.INBOUND
