"""Shared builders for the S2 agent-guard / prompt-injection scope.

Everything here is in-memory and deterministic — no Postgres, no network, no
Langfuse. The guard reads the LLM verdict as flat text, so a fake chat model in
the classifier seam plus a disabled observer is enough to drive the whole
verdict -> action pipeline. Heavier integration plumbing (real checkpointer,
real DB) is deliberately faked: these tests probe the code's *reaction* to a
verdict, not the infrastructure underneath.
"""

from __future__ import annotations

from typing import Any

import pytest
from app.agent.security.classifier import LLMClassifier
from app.agent.security.config import checkpoint_configs
from app.agent.security.detectors.base import DeterministicDetector
from app.agent.security.guard import SecurityGuard
from app.agent.security.observer import GuardObserver
from app.agent.security.types import (
    LLMClassifierConfig,
    SecurityConfig,
)
from langchain_core.language_models import BaseChatModel


class StubPromptProvider:
    """Minimal stand-in for ``PromptProvider`` — returns a fixed system prompt.

    The classifier only needs ``get_prompt`` to produce *some* system text; the
    actual prompt content is irrelevant to the parsing/retry logic under test
    (prompt quality is an eval concern, not a unit one).
    """

    def __init__(self, text: str = "classify the input") -> None:
        self._text = text

    def get_prompt(self, name: str, **variables: str) -> str:
        return self._text


def make_security_config(*, max_retries: int = 3) -> SecurityConfig:
    return SecurityConfig(
        llm_classifier=LLMClassifierConfig(model="fake-model", max_retries=max_retries)
    )


def make_classifier(
    llm: BaseChatModel,
    *,
    config: SecurityConfig | None = None,
) -> LLMClassifier:
    cfg = config or make_security_config()
    return LLMClassifier(
        llm=llm,
        prompt_provider=StubPromptProvider(),  # type: ignore[arg-type]
        security_config=cfg,
        checkpoint_configs=checkpoint_configs(cfg),
    )


def make_guard(
    llm: BaseChatModel,
    *,
    detectors: list[DeterministicDetector] | None = None,
    config: SecurityConfig | None = None,
) -> SecurityGuard:
    cfg = config or make_security_config()
    return SecurityGuard(
        detectors=detectors or [],
        classifier=make_classifier(llm, config=cfg),
        observer=GuardObserver(enabled=False),
        config=cfg,
    )


class RecordingGraph:
    """Spy graph capturing ``aupdate_state`` calls (checkpointer write side)."""

    def __init__(self) -> None:
        self.updates: list[dict[str, Any]] = []

    async def aupdate_state(
        self, config: Any, values: Any, *, as_node: str | None = None
    ) -> None:
        self.updates.append({"config": config, "values": values, "as_node": as_node})


class FakeCheckpointer:
    """Fake LangGraph checkpointer returning a fixed message list (or miss)."""

    def __init__(self, messages: list[Any] | None = None) -> None:
        self._messages = messages

    async def aget_tuple(self, config: Any) -> Any:
        if self._messages is None:
            return None
        return _CheckpointTuple({"channel_values": {"messages": self._messages}})


class _CheckpointTuple:
    def __init__(self, checkpoint: dict[str, Any]) -> None:
        self.checkpoint = checkpoint


@pytest.fixture
def recording_graph() -> RecordingGraph:
    return RecordingGraph()
