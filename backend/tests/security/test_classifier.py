"""LLMClassifier: verdict parsing, retry loop, graceful degradation to CLEAN.

The classifier reads the model's *flat text* content (no structured output) and
matches it against {CLEAN, SUSPICIOUS, INJECTION}. We feed deterministic fake
models into the seam and assert how the parsing/retry code reacts — not the
quality of any real verdict (that is eval).
"""

from __future__ import annotations

import pytest
from app.agent.security.classifier import LLMClassifier
from app.agent.security.config import checkpoint_configs
from app.agent.security.types import Checkpoint, Verdict
from langchain_core.messages import AIMessage, HumanMessage
from learnflow_testing.fakes import (
    fake_chat_model,
    garbage_classifier_model,
    guard_classifier_model,
)
from tests.security.conftest import make_classifier, make_security_config


class _CapturingPromptProvider:
    """Records the variables the classifier passes into the prompt template."""

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def get_prompt(self, name: str, **variables: str) -> str:
        self.calls.append(variables)
        return "classify the input"


@pytest.mark.unit
@pytest.mark.parametrize(
    "verdict", [Verdict.CLEAN, Verdict.SUSPICIOUS, Verdict.INJECTION]
)
async def test_classify_parses_each_valid_verdict(verdict: Verdict) -> None:
    classifier = make_classifier(guard_classifier_model(verdict))

    result = await classifier.classify("some content", Checkpoint.USER_INPUT)

    assert result.verdict is verdict
    assert result.retries == 0
    assert result.degraded is False


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["injection", "  Injection \n", "INJECTION"])
async def test_classify_normalizes_case_and_whitespace(raw: str) -> None:
    classifier = make_classifier(fake_chat_model([AIMessage(content=raw)]))

    result = await classifier.classify("content", Checkpoint.USER_INPUT)

    assert result.verdict is Verdict.INJECTION


@pytest.mark.unit
async def test_classify_retries_then_succeeds_counts_retries() -> None:
    # First response unparseable, second is a valid verdict.
    model = fake_chat_model([AIMessage(content="GARBAGE"), AIMessage(content="CLEAN")])
    classifier = make_classifier(model)

    result = await classifier.classify("content", Checkpoint.USER_INPUT)

    assert result.verdict is Verdict.CLEAN
    assert result.retries == 1
    assert result.degraded is False


@pytest.mark.unit
async def test_classify_exhausts_retries_degrades_to_clean() -> None:
    classifier = make_classifier(garbage_classifier_model())

    result = await classifier.classify("content", Checkpoint.USER_INPUT)

    assert result.verdict is Verdict.CLEAN
    assert result.degraded is True
    assert result.retries == 3  # default max_retries


@pytest.mark.unit
async def test_classify_respects_configured_max_retries() -> None:
    cfg = make_security_config(max_retries=2)
    classifier = make_classifier(garbage_classifier_model(), config=cfg)

    result = await classifier.classify("content", Checkpoint.USER_INPUT)

    assert result.degraded is True
    assert result.retries == 2


@pytest.mark.unit
async def test_classify_passes_formatted_history_into_prompt() -> None:
    provider = _CapturingPromptProvider()
    cfg = make_security_config()
    classifier = LLMClassifier(
        llm=guard_classifier_model(Verdict.CLEAN),
        prompt_provider=provider,  # type: ignore[arg-type]
        security_config=cfg,
        checkpoint_configs=checkpoint_configs(cfg),
    )

    await classifier.classify(
        "current",
        Checkpoint.USER_INPUT,
        history=[HumanMessage(content="earlier turn")],
    )

    # History is rendered through the XML formatter and handed to the prompt.
    history_section = provider.calls[0]["history_section"]
    assert "<conversation_history>" in history_section
    assert "[USER] earlier turn" in history_section


@pytest.mark.unit
async def test_classify_propagates_model_reasoning_into_result() -> None:
    model = fake_chat_model(
        [AIMessage(content="CLEAN", additional_kwargs={"reasoning": "looks benign"})]
    )
    classifier = make_classifier(model)

    result = await classifier.classify("content", Checkpoint.USER_INPUT)

    assert result.verdict is Verdict.CLEAN
    assert result.reasoning == "looks benign"
