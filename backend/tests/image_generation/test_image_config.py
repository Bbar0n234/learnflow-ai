"""Unit: ``image`` config section is required and fail-fast (T1.4).

The iteration makes ``AgentConfig.image`` a required field (architect decision:
a missing ``image`` section in ``agent.yaml`` is a start-up configuration error,
not a silent default). These pin that contract plus the ``params`` passthrough.
"""

from __future__ import annotations

import pytest
from app.agent.config import AgentConfig, ImageConfig, load_agent_config
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_agent_config_without_image_section_raises() -> None:
    with pytest.raises(ValidationError) as exc:
        AgentConfig.model_validate(
            {"llm": {"model": "m"}, "context": {"max_tokens": 100}}
        )

    # The missing field is named -> fail-fast points at the config gap.
    assert any(err["loc"] == ("image",) for err in exc.value.errors())


def test_image_config_params_defaults_to_empty_dict() -> None:
    config = ImageConfig(model="google/gemini-3.1-flash-image")

    assert config.params == {}


def test_image_config_preserves_arbitrary_params() -> None:
    # ``params`` is an opaque passthrough (the ``extra_body`` pattern) so a model
    # swap needing new params does not require code changes.
    config = ImageConfig(model="m", params={"guidance": 7, "safety": "off"})

    assert config.params == {"guidance": 7, "safety": "off"}


def test_real_agent_config_loads_image_section() -> None:
    agent = load_agent_config()

    assert isinstance(agent.image, ImageConfig)
    assert agent.image.model == "google/gemini-3.1-flash-image"
