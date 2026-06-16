"""feat-005: ModelConfigResolver.default() public accessor (finding D)."""

from app.agent.config import AgentConfig, ContextConfig, LLMConfig
from app.services.model_config_resolver import ModelConfigResolver


def _resolver(extra_body: dict) -> ModelConfigResolver:
    agent_config = AgentConfig(
        llm=LLMConfig(model="z-ai/glm-5", extra_body=extra_body),
        context=ContextConfig(max_tokens=100000),
    )
    return ModelConfigResolver(prompt_provider=None, agent_config=agent_config)


def test_default_returns_agent_yaml_config() -> None:
    resolved = _resolver({"include_reasoning": True}).default()
    assert resolved.model == "z-ai/glm-5"
    assert resolved.extra_body == {"include_reasoning": True}
    assert resolved.source == "config"


def test_default_empty_extra_body_is_none() -> None:
    resolved = _resolver({}).default()
    assert resolved.extra_body is None
