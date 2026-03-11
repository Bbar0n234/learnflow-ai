from pathlib import Path

import yaml
from pydantic import BaseModel


class LLMConfig(BaseModel):
    model: str


class ContextConfig(BaseModel):
    max_tokens: int


class PromptConfig(BaseModel):
    system: str


class AgentConfig(BaseModel):
    llm: LLMConfig
    context: ContextConfig
    prompt: PromptConfig


def load_agent_config(path: Path | None = None) -> AgentConfig:
    if path is None:
        # configs/agent.yaml at repo root
        path = Path(__file__).resolve().parents[3] / "configs" / "agent.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return AgentConfig(**data)
