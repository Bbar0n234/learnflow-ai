"""feat-005: LLM factory dedup + unconditional ReasoningChatOpenAI (A1a/A2/B).

Locks the convention "every model in the project is ReasoningChatOpenAI by
default" and the removal of the two dead factories.
"""

from types import SimpleNamespace

import app.infra.llm as llm_mod
from app.agent.config import ResolvedModelConfig, SummarizationConfig
from app.agent.security.types import (
    LLMClassifierConfig,
    LLMExtraBody,
    ReasoningOptions,
    SecurityConfig,
)
from app.infra.llm import (
    ReasoningChatOpenAI,
    create_guard_llm,
    create_llm_from_config,
)

_SETTINGS = SimpleNamespace(llm_api_key="test-key", llm_base_url="http://llm.local")


def test_create_llm_from_config_is_reasoning_with_flag() -> None:
    cfg = ResolvedModelConfig(
        model="z-ai/glm-5",
        extra_body={"include_reasoning": True},
        source="config",
    )
    llm = create_llm_from_config(_SETTINGS, cfg)
    assert isinstance(llm, ReasoningChatOpenAI)
    assert llm.model_name == "z-ai/glm-5"
    assert llm.extra_body == {"include_reasoning": True}


def test_create_llm_from_config_is_reasoning_without_flag() -> None:
    # Unconditional: ReasoningChatOpenAI even when include_reasoning is false.
    cfg = ResolvedModelConfig(
        model="z-ai/glm-5",
        extra_body={"include_reasoning": False},
        source="config",
    )
    llm = create_llm_from_config(_SETTINGS, cfg)
    assert isinstance(llm, ReasoningChatOpenAI)


def test_create_llm_from_config_is_reasoning_without_extra_body() -> None:
    cfg = ResolvedModelConfig(model="z-ai/glm-5", extra_body=None, source="config")
    llm = create_llm_from_config(_SETTINGS, cfg)
    assert isinstance(llm, ReasoningChatOpenAI)


def test_create_summarization_llm_sets_max_tokens() -> None:
    cfg = SummarizationConfig(
        model="z-ai/glm-4.7-flash",
        max_summary_tokens=321,
        extra_body={"include_reasoning": True},
    )
    llm = llm_mod.create_summarization_llm(_SETTINGS, cfg)
    assert isinstance(llm, ReasoningChatOpenAI)
    assert llm.model_name == "z-ai/glm-4.7-flash"
    assert llm.max_tokens == 321


def test_create_guard_llm_sets_temperature_and_reasoning() -> None:
    sec = SecurityConfig(
        llm_classifier=LLMClassifierConfig(
            model="z-ai/glm-4.7-flash",
            extra_body=LLMExtraBody(
                include_reasoning=True, reasoning=ReasoningOptions(effort="low")
            ),
            temperature=0.0,
        )
    )
    llm = create_guard_llm(_SETTINGS, sec)
    assert isinstance(llm, ReasoningChatOpenAI)
    assert llm.temperature == 0.0
    assert llm.extra_body == {"include_reasoning": True, "reasoning": {"effort": "low"}}


def test_dead_factories_removed() -> None:
    # B: the two unused factories must be gone.
    assert not hasattr(llm_mod, "create_llm")
    assert not hasattr(llm_mod, "create_summarization_llm_from_prompt_config")


def test_settings_wired_into_client() -> None:
    cfg = ResolvedModelConfig(model="m", extra_body=None, source="config")
    llm = create_llm_from_config(_SETTINGS, cfg)
    assert llm.openai_api_key.get_secret_value() == "test-key"
    assert str(llm.openai_api_base) == "http://llm.local"
