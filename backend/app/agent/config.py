from pathlib import Path

import yaml
from pydantic import BaseModel


class LLMConfig(BaseModel):
    model: str


class ContextConfig(BaseModel):
    max_tokens: int


class PromptConfig(BaseModel):
    system: str


class MCPServerConfig(BaseModel):
    transport: str  # "http", "sse", "stdio"
    url: str | None = None
    api_key_env: str | None = None
    command: str | None = None
    args: list[str] | None = None


class AgentConfig(BaseModel):
    llm: LLMConfig
    context: ContextConfig
    prompt: PromptConfig
    mcp_servers: dict[str, MCPServerConfig] = {}


def load_agent_config(path: Path | None = None) -> AgentConfig:
    if path is None:
        # configs/agent.yaml at repo root
        path = Path(__file__).resolve().parents[3] / "configs" / "agent.yaml"
    with open(path) as f:
        data = yaml.safe_load(f)
    return AgentConfig(**data)
